import json

import httpx

from conftest import ADMIN
from scamserp.collector import Collector


def test_ads_transparency_evidence_is_joined_and_unknown_age_is_not_a_signal(client,db,pipeline):
    def handler(request):
        if request.url.params['engine']=='google_ads_transparency_center':
            return httpx.Response(200,json={'search_metadata':{'id':'transparency','status':'Success'},'advertiser':{'id':'AR123','legal_name':'Fixture advertiser','verification_status':'unverified'},'ad_creatives':[{'first_shown':1780000000}]})
        return httpx.Response(200,json={'ads':[{'title':'SBI support','link':'https://sbi-help.example','advertiser_id':'AR123'}]})
    Collector(db,pipeline,transport=httpx.MockTransport(handler)).collect('sbi-en-1','Delhi')
    scored=db.one('SELECT * FROM score ORDER BY id DESC LIMIT 1')
    signals=json.loads(scored['signals_json'])
    assert any(s['code']=='ad_unlinked' for s in signals)
    assert not any(s['code']=='ad_new' for s in signals)
    assert scored['verdict']=='Likely Fraud'
    campaign=db.one('SELECT * FROM campaign')
    private=client.get('/api/admin/campaigns/'+campaign['id'],headers=ADMIN).json()
    assert private['findings'][0]['advertiser_evidence']['search_id']=='transparency'
    assert private['findings'][0]['advertiser_evidence']['account_created_at'] is None


def test_domain_discovery_keeps_ambiguous_candidates_unattributed(client,db,pipeline):
    def handler(request):
        params=request.url.params
        if params['engine']=='google':
            return httpx.Response(200,json={'ads':[{'title':'SBI support','link':'https://sbi-help.example'}]})
        if 'text' in params:
            return httpx.Response(200,json={'search_metadata':{'id':'domain-discovery','status':'Success'},'ad_creatives':[{'advertiser_id':'AR123','advertiser':'Candidate A','target_domain':'sbi-help.example'},{'advertiser_id':'AR456','advertiser':'Candidate B','target_domain':'sbi-help.example'},{'advertiser_id':'AR789','target_domain':'other.example'}]})
        return httpx.Response(200,json={'search_metadata':{'id':'details','status':'Success'},'advertiser':{'legal_name':'Candidate A'},'ad_creatives':[]})
    Collector(db,pipeline,transport=httpx.MockTransport(handler)).collect('sbi-en-1','Delhi')
    observation=db.one("SELECT * FROM observation WHERE kind='ad'")
    assert observation['advertiser_id'] is None
    assert {c['id'] for c in json.loads(observation['facts_json'])['advertiser_candidates']}=={'AR123','AR456'}
    assert db.one('SELECT verdict FROM score ORDER BY id DESC LIMIT 1')['verdict']=='Suspicious'
    assert db.one('SELECT COUNT(*) n FROM budget')['n']==3
    # Explicit human attribution can supply an evidence-backed relationship.
    body={'observation_id':observation['id'],'advertiser_id':'AR123','relationship':'unlinked','source_url':'https://sbi.bank.in/contact','reviewer':'Fixture reviewer','verified_at':'2026-01-01T00:00:00+00:00','expires_at':'2099-01-01T00:00:00+00:00'}
    assert client.post('/api/admin/advertisers/review',headers=ADMIN,json=body).status_code==200
    assert db.one('SELECT verdict FROM score ORDER BY id DESC LIMIT 1')['verdict']=='Likely Fraud'
    db.execute("UPDATE advertiser_review SET expires_at='2000-01-01T00:00:00+00:00'")
    assert client.get('/api/lookup',params={'type':'domain','value':'sbi-help.example'}).json()['verdict']=='Suspicious'


def test_map_search_invokes_advertiser_enrichment(client,app,db):
    calls=[]
    def handler(request):
        engine=request.url.params['engine'];calls.append(engine)
        if engine=='google':
            return httpx.Response(200,json={'ads':[{'title':'SBI ad','link':'https://sbi-help.example','advertiser_id':'AR123'}]})
        if engine=='google_ads_transparency_center':
            return httpx.Response(200,json={'search_metadata':{'status':'Success'},'advertiser':{'legal_name':'Fixture advertiser'}})
        return httpx.Response(200,json={'local_results':[{'title':'SBI branch','website':'https://sbi.bank.in'}]})
    app.state.collector.transport=httpx.MockTransport(handler)
    response=client.post('/api/map/search',json={'query':'SBI support','state':'Delhi'})
    assert response.status_code==200,response.text
    assert calls==['google','google_ads_transparency_center','google_maps']
    ad=next(r for r in response.json()['results'] if r['kind']=='ad')
    assert ad['advertiser_evidence']['verification_status']=='unknown'
