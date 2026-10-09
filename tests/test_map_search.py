import httpx
import pytest


def install_mock(app):
    calls=[]
    def handler(request):
        calls.append(request)
        if request.url.params['engine']=='google_maps':
            return httpx.Response(200,json={'search_metadata':{'id':'map-test'},'local_results':[{'position':1,'title':'SBI official fixture','website':'https://sbi.bank.in','phone':'1800 1234','address':'Public listing address','gps_coordinates':{'latitude':28.61,'longitude':77.20}},{'position':2,'title':'SBI support fixture','website':'https://sbi-risk.example','phone':'1800 000 0000','gps_coordinates':{'latitude':28.62,'longitude':77.21}}]})
        return httpx.Response(200,json={'search_metadata':{'id':'search-test'},'organic_results':[{'title':'SBI official','link':'https://sbi.bank.in','snippet':'1800 1234'}]})
    app.state.collector.transport=httpx.MockTransport(handler)
    app.state.db.settings.map_search_enabled=True
    return calls


def test_map_search_collects_and_scores_places(client,app):
    calls=install_mock(app)
    response=client.post('/api/map/search',json={'query':'SBI customer care','state':'Delhi'})
    assert response.status_code==200,response.text
    data=response.json()
    assert {r['engine'] for r in data['runs']}=={'google','google_maps'}
    assert len(calls)==2
    assert data['entity']['id']=='sbi'
    assert data['summary']['verified']==2
    assert data['withheld']==1
    assert data['summary']['spot_exposure'] is None
    assert 'sbi-risk.example' not in response.text
    place=next(r for r in data['results'] if r['kind']=='local')
    assert place['coordinates']=={'latitude':28.61,'longitude':77.20}
    assert client.post('/api/map/search',json={'query':'SBI customer care','state':'Delhi'}).status_code==200
    assert len(calls)==2


def test_precise_search_area_is_rounded_before_provider_and_storage(client,app):
    calls=install_mock(app)
    response=client.post('/api/map/search',json={'query':'SBI helpline','latitude':28.6139876,'longitude':77.2098765})
    assert response.status_code==200
    maps=next(r for r in calls if r.url.params['engine']=='google_maps')
    assert maps.url.params['ll']=='@28.61,77.21,12z'
    assert '28.6139876' not in str(app.state.db.rows('SELECT * FROM run'))
    assert client.post('/api/map/search',json={'query':'SBI helpline','latitude':999,'longitude':77}).status_code==422
    assert client.post('/api/map/search',json={'query':'SBI helpline','latitude':28}).status_code==422


def test_map_search_can_be_disabled(client,app):
    app.state.db.settings.map_search_enabled=False
    assert client.post('/api/map/search',json={'query':'SBI customer care'}).status_code==403


def test_partial_budget_has_explicit_gap(client,app):
    calls=install_mock(app)
    app.state.db.settings.daily_cap=1
    result=client.post('/api/map/search',json={'query':'SBI customer care'}).json()
    assert len(calls)==1 and result['gaps']
    assert result['summary']['spot_exposure'] is None


def test_unknown_entity_remains_unverified(client,app):
    install_mock(app)
    app.state.collector.transport=httpx.MockTransport(lambda request:httpx.Response(200,json={'local_results':[{'title':'Independent support fixture','website':'https://unknown-support.example','gps_coordinates':{'latitude':28.6,'longitude':77.2}}]} if request.url.params['engine']=='google_maps' else {'organic_results':[{'title':'Independent support fixture','link':'https://unknown-support.example'}]}))
    data=client.post('/api/map/search',json={'query':'support office'}).json()
    assert data['entity'] is None
    assert all(r['verdict']=='Unverified' for r in data['results'])


def test_failed_surfaces_are_recorded_as_gaps(client,app):
    app.state.db.settings.map_search_enabled=True
    app.state.collector.transport=httpx.MockTransport(lambda _:httpx.Response(401,json={'error':'Rejected test credential'}))
    result=client.post('/api/map/search',json={'query':'SBI customer care'})
    assert result.status_code==503
    assert app.state.db.one("SELECT COUNT(*) n FROM run WHERE status='failed'")['n']==1
    assert 'rejected the configured API key' in result.json()['detail']
