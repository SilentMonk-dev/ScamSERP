from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

from scamserp.collector import BudgetExceeded, Collector
from scamserp.db import now


def test_budget_concurrency_never_exceeds_cap(db,pipeline):
    collector=Collector(db,pipeline)
    def reserve(_):
        try:
            collector.reserve('google')
            return True
        except BudgetExceeded:
            return False
    with ThreadPoolExecutor(max_workers=8) as pool:
        results=list(pool.map(reserve,range(20)))
    assert sum(results)==5
    assert db.one('SELECT COUNT(*) n FROM budget')['n']==5


def test_retry_and_cache_reserve_each_network_call(db,pipeline):
    calls=[]
    def transport(request):
        calls.append(request)
        if len(calls)==1:
            return httpx.Response(429,json={'error':'rate limited'})
        return httpx.Response(200,json={'search_metadata':{'id':'mock-live','status':'Success'},'organic_results':[{'title':'SBI official','link':'https://sbi.bank.in/','snippet':'1800 1234'}]})
    collector=Collector(db,pipeline,transport=httpx.MockTransport(transport),sleep=lambda _:None)
    result=collector.collect('sbi-en-1','Delhi')
    assert result['status']=='success' and len(calls)==2
    assert collector.collect('sbi-en-1','Delhi')['cached']
    assert len(calls)==2 and db.one('SELECT COUNT(*) n FROM budget')['n']==2
    assert calls[0].url.params['gl']=='in' and calls[0].url.params['hl']=='en'


def test_provider_failure_creates_gap_without_secret(db,pipeline):
    collector=Collector(db,pipeline,transport=httpx.MockTransport(lambda _:httpx.Response(401,json={'error':'bad test-key'})),sleep=lambda _:None)
    with pytest.raises(RuntimeError):
        collector.collect('sbi-en-1','Delhi')
    assert db.one('SELECT status FROM run')['status']=='failed'
    assert 'test-key' not in str(db.rows('SELECT * FROM run'))


def test_ads_transparency_fetch_and_missing_fields(db,pipeline):
    def transport(request):
        if request.url.params['engine']=='google_ads_transparency_center':
            assert request.url.params['get_advertiser']=='true'
            return httpx.Response(200,json={'search_metadata':{'id':'ads-id'},'advertiser':{'id':'AR000','legal_name':'Test advertiser','country_code':'IN'},'ad_creatives':[{'first_shown':123}], 'search_information':{'total_results':4}})
        return httpx.Response(200,json={'ads':[{'title':'SBI support','link':'https://sbi.bank.in/','advertiser_id':'AR000'}]})
    c=Collector(db,pipeline,transport=httpx.MockTransport(transport))
    c.collect('sbi-en-1','Delhi')
    import json
    data=json.loads(db.one('SELECT data_json FROM advertiser')['data_json'])
    assert data['verification_status']=='unknown'
    assert db.one('SELECT COUNT(*) n FROM budget')['n']==2


def test_monthly_cap_is_also_enforced(db,pipeline):
    db.settings.monthly_cap=1
    collector=Collector(db,pipeline)
    collector.reserve('google')
    with pytest.raises(BudgetExceeded):collector.reserve('google')
