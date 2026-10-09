import gzip
import json

from conftest import ADMIN


def test_registry_and_unknown_lookup(client):
    official = client.get('/api/lookup', params={'type': 'phone', 'value': '1800 1234'}).json()
    assert official['verdict'] == 'Verified Official'
    assert official['registry_source']['source_url'].startswith('https://sbi.bank.in')
    unknown = client.post('/api/lookup/text', json={'text': 'Visit never-observed.example or call 1800 1234'}).json()
    assert {i['verdict'] for i in unknown['items']} == {'Verified Official', 'No data'}
    assert client.get('/api/lookup',params={'type':'domain','value':'hdfc.bank.in'}).json()['verdict'] == 'Unverified'


def test_lookup_privacy_no_retention(client,db):
    marker='unique-lookup-content-73194'
    before=db.one('SELECT COUNT(*) n FROM run')['n']
    client.post('/api/lookup/text',json={'text':marker+' https://never.example'})
    assert db.one('SELECT COUNT(*) n FROM run')['n'] == before
    assert marker not in json.dumps(db.rows('SELECT * FROM audit_log'))


def test_publication_gate_dispute_and_export(client,db,pipeline,risky_payload):
    result=pipeline.ingest(risky_payload,'sbi-en-1','google','Delhi','New Delhi, Delhi, India','en')
    assert result['status']=='success'
    assert client.get('/api/lookup',params={'type':'domain','value':'sbi-care.example'}).json()['verdict']=='No data'
    assert client.get('/api/map').json()['summary']['n_runs']==0
    campaign=db.one('SELECT * FROM campaign')
    private=client.get('/api/admin/campaigns/'+campaign['id'],headers=ADMIN).json()
    assert private['findings'][0]['verdict']=='Likely Fraud'
    assert client.post('/api/admin/campaigns/'+campaign['id']+'/review',headers=ADMIN,json={'decision':'approved','reviewer':'Test reviewer','evidence_hash':campaign['evidence_hash']}).status_code==200
    lookup=client.get('/api/lookup',params={'type':'domain','value':'sbi-care.example'}).json()
    assert lookup['verdict']=='Likely Fraud'
    oid=lookup['evidence'][0]['id']
    exported=client.get('/api/export').json()
    assert 'sbi-care.example' not in json.dumps(exported)
    assert '18000000000' not in json.dumps(exported)
    assert client.post('/api/disputes',json={'target_id':oid,'message':'Official correction evidence for review'}).status_code==201
    assert client.get('/api/report/'+oid).status_code==404
    assert client.get('/api/lookup',params={'type':'domain','value':'sbi-care.example'}).json()['verdict']=='No data'
    assert client.get('/api/map').json()['withheld_runs']==1


def test_empty_and_failed_runs_are_gaps(client,db,pipeline):
    pipeline.ingest({'organic_results':[]},'sbi-en-1','google','Delhi','Delhi','en')
    pipeline.ingest({'error':'Provider unavailable'},'sbi-en-1','google','Delhi','Delhi','en')
    assert {r['status'] for r in db.rows('SELECT status FROM run')}=={'empty','failed'}
    assert client.get('/api/map').json()['summary']['exposure'] is None


def test_raw_compressed_and_key_redacted(client,db,pipeline,risky_payload):
    risky_payload['search_parameters']={'api_key':'super-secret'}
    result=pipeline.ingest(risky_payload,'sbi-en-1','google','Delhi','Delhi','en')
    row=db.one('SELECT * FROM run WHERE id=?',(result['run_id'],))
    with gzip.open(db.settings.data_dir / row['raw_ref'],'rt',encoding='utf-8') as f:
        raw=f.read()
    assert 'super-secret' not in raw and '[redacted]' in raw
    assert client.get('/api/admin/raw/'+row['id']).status_code==401
    assert client.get('/api/admin/raw/'+row['id'],headers=ADMIN).status_code==200


def test_suggestion_never_auto_accepted(client,db):
    body={'entity_id':'sbi','kind':'domain','value':'new-sbi.example','display':'new-sbi.example','source_url':'https://sbi.bank.in/contact','verifier':'public','status':'verified'}
    assert client.post('/api/registry/suggestions',json=body).status_code==201
    assert not db.one('SELECT * FROM registry WHERE value=?',('new-sbi.example',))


def test_registry_edit_auth_history_and_rescore(client,db,pipeline,risky_payload):
    pipeline.ingest(risky_payload,'sbi-en-1','google','Delhi','Delhi','en')
    body={'entity_id':'sbi','kind':'domain','value':'sbi-care.example','display':'fixture domain','source_url':'https://sbi.bank.in/contact','verifier':'Test reviewer','status':'verified','verified_at':'2026-01-01T00:00:00+00:00','expires_at':'2099-01-01T00:00:00+00:00'}
    assert client.post('/api/admin/registry',json=body).status_code==401
    assert client.post('/api/admin/registry',json=body,headers=ADMIN).status_code==200
    assert db.one('SELECT COUNT(*) n FROM registry_history')['n']==1
    assert db.one('SELECT COUNT(*) n FROM score')['n']==4
    body['value']='google.com'
    assert client.post('/api/admin/registry',json=body,headers=ADMIN).status_code==422


def test_input_limits_and_security_headers(client):
    assert client.post('/api/lookup/text',json={'text':'x'*4001}).status_code==422
    assert client.post('/api/lookup/text',content=b'x'*17000,headers={'Content-Type':'application/json'}).status_code==413
    assert client.get('/api/lookup',params={'type':'phone','value':'invalid'}).status_code==422
    assert "object-src 'none'" in client.get('/').headers['content-security-policy']
    assert client.get('/api/meta').headers['cache-control']=='no-store'


def test_unmeasured_evaluation_and_empty_exports(client):
    result=client.get('/api/evaluation').json()
    assert result['real']['precision'] is None and result['real']['n']==0
    assert 'observation_id' in client.get('/api/export?format=csv').text
    assert client.get('/api/digest?format=html').status_code==200


def test_metadata_entity_and_expanded_intent_coverage(client):
    data=client.get('/api/meta').json()
    assert len(data['entities'])==40 and data['queries']==1393
    assert data['registry_current']==4


def test_repeat_disputes_do_not_restore_early(client,db,pipeline,risky_payload):
    pipeline.ingest(risky_payload,'sbi-en-1','google','Delhi','Delhi','en')
    oid=db.one('SELECT id FROM observation')['id']
    ids=[client.post('/api/disputes',json={'target_id':oid,'message':'Correction request with evidence'}).json()['id'] for _ in range(2)]
    client.post('/api/admin/disputes/'+ids[0]+'/review',headers=ADMIN,json={'decision':'rejected','reviewer':'Review staff'})
    assert db.one('SELECT hidden FROM observation WHERE id=?',(oid,))['hidden']==1


def test_query_candidate_review(client,db,pipeline):
    pipeline.ingest({'suggestions':[{'value':'sbi helpline extra'}]},'sbi-en-1','google_autocomplete','Delhi','Delhi','en')
    q=db.one("SELECT * FROM query WHERE origin='autocomplete'")
    assert not q['active']
    client.post('/api/admin/queries/'+q['id']+'/review',headers=ADMIN,json={'decision':'approved','reviewer':'Native speaker'})
    assert db.one('SELECT active FROM query WHERE id=?',(q['id'],))['active']==1
