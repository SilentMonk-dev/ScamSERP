import json
from datetime import datetime, timedelta, timezone

import httpx

from conftest import ADMIN
from scamserp.collector import Collector
from scamserp.db import now
from scamserp.seed import seed_registry


def test_registry_expiry_refreshes_lookup_export_and_map(client, db, pipeline):
    pipeline.ingest({'organic_results':[{'title':'SBI official','link':'https://sbi.bank.in','snippet':'1800 1234'}]}, 'sbi-en-1','google','Delhi','Delhi','en')
    assert client.get('/api/lookup',params={'type':'domain','value':'sbi.bank.in'}).json()['verdict']=='Verified Official'
    db.execute("UPDATE registry SET expires_at='2000-01-01T00:00:00+00:00' WHERE entity_id='sbi'")
    result=client.get('/api/lookup',params={'type':'domain','value':'sbi.bank.in'}).json()
    assert result['verdict']=='Unverified' and not result['registry_match']
    assert result['evidence'][0]['verdict']=='Unverified'
    assert all(o['verdict']!='Verified Official' for o in client.get('/api/export').json()['observations'])


def test_changed_evidence_invalidates_review_and_stale_submission(client,db,pipeline):
    pipeline.ingest({'organic_results':[{'title':'SBI support','link':'https://sbi-help.example','snippet':'Fixture without contact'}]},'sbi-en-1','google','Delhi','Delhi','en')
    campaign=db.one('SELECT * FROM campaign')
    review={'decision':'approved','reviewer':'Test reviewer','evidence_hash':campaign['evidence_hash']}
    assert client.post('/api/admin/campaigns/'+campaign['id']+'/review',headers=ADMIN,json=review).status_code==200
    pipeline.rebuild()
    assert db.one('SELECT review_state FROM campaign')['review_state']=='approved'
    db.execute('UPDATE observation SET facts_json=?',(json.dumps({'registered_at':now()}),))
    pipeline.rebuild()
    assert db.one('SELECT review_state FROM campaign')['review_state']=='pending'
    assert client.get('/api/lookup',params={'type':'domain','value':'sbi-help.example'}).json()['verdict']=='No data'
    assert client.post('/api/admin/campaigns/'+campaign['id']+'/review',headers=ADMIN,json=review).status_code==409


def test_withheld_counts_obey_category_language_and_window(client,db,pipeline,risky_payload):
    pipeline.ingest(risky_payload,'sbi-en-1','google','Delhi','Delhi','en',fetched_at=(datetime.now(timezone.utc)-timedelta(days=10)).isoformat())
    assert client.get('/api/map?category=banking&language=en&window=30').json()['withheld_runs']==1
    for query in ['category=logistics','language=hi','window=7']:
        assert client.get('/api/map?'+query).json()['withheld_runs']==0


def test_language_equity_requires_identical_intent_and_engine(client,db,pipeline):
    langs=['en','hi','ta','te','bn','mr']
    payload={'organic_results':[{'title':'Official','link':'https://sbi.bank.in'}]}
    for i,lang in enumerate(langs):
        pipeline.ingest(payload,f'sbi-{lang}-{1 if i==0 else 2}','google','Delhi','Delhi',lang)
    assert client.get('/api/equity').json()['matched_cells']==0
    for lang in langs[1:]:
        pipeline.ingest(payload,f'sbi-{lang}-1','google','Delhi','Delhi',lang)
    assert client.get('/api/equity').json()['matched_cells']==1


def test_new_query_intents_are_idempotent_and_translated(client,db):
    for intent,eid in [('refund','amazon'),('tracking','indiapost'),('appointment','passport')]:
        rows=db.rows('SELECT * FROM query WHERE entity_id=? AND intent_id=?',(eid,intent))
        assert {q['language'] for q in rows}=={'en','hi','ta','te','bn','mr','hinglish'}
    before=db.one('SELECT COUNT(*) n FROM query')['n']
    seed_registry(db)
    assert db.one('SELECT COUNT(*) n FROM query')['n']==before


def test_scheduler_collects_missing_surface_without_recollecting_fresh_search(client,db,pipeline):
    db.execute("UPDATE query SET active=0 WHERE id!='sbi-en-1'")
    for state in ['Maharashtra','Uttar Pradesh','Tamil Nadu','Telangana','West Bengal','Delhi']:
        pipeline.ingest({'organic_results':[{'title':'SBI','link':'https://sbi.bank.in'}]},'sbi-en-1','google',state,state,'en')
    calls=[]
    def handler(req):
        calls.append(req.url.params['engine'])
        return httpx.Response(200,json={'suggestions':[{'value':'SBI refund phone'}]})
    result=Collector(db,pipeline,transport=httpx.MockTransport(handler)).scheduled(1)
    assert calls==['google_autocomplete']
    assert result[0]['state']=='India'
    assert len(Collector(db,pipeline).schedule_plan())==7
    assert client.get('/api/coverage').json()['scheduler']['recent_heartbeat']


def test_risk_matrix_reports_uncollected_and_withheld_cells(client,db,pipeline,risky_payload):
    pipeline.ingest(risky_payload,'sbi-en-1','google','Delhi','Delhi','en')
    data=client.get('/api/risk/matrix?query_id=sbi-en-1').json()
    assert data['total']==6
    assert next(r for r in data['items'] if r['state']=='Delhi')['collection_status']=='withheld'
    assert next(r for r in data['items'] if r['state']=='Maharashtra')['collection_status']=='not collected'
    assert all(r['exposure'] is None for r in data['items'])


def test_map_and_matrix_apply_same_query_state_language_filters(client,db,pipeline):
    payload={'organic_results':[{'title':'Official','link':'https://sbi.bank.in'}]}
    pipeline.ingest(payload,'sbi-en-1','google','Delhi','Delhi','en')
    pipeline.ingest(payload,'sbi-en-2','google','Maharashtra','Mumbai','en')
    result=client.get('/api/map?state=Delhi&language=en&search=customer%20care').json()
    assert result['summary']['n_runs']==1
    assert [s['state'] for s in result['states']]==['Delhi']
    data=client.get('/api/risk/matrix?state=Delhi&language=en&search=customer%20care').json()
    assert all(c['state']=='Delhi' and c['language']=='en' for c in data['items'])
    assert sum(c['n_runs'] for c in data['items'])==1
