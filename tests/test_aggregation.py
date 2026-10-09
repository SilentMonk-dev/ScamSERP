from scamserp.service import csv_text
from conftest import ADMIN


def test_position_weighted_exposure_and_sample_threshold(client,db,pipeline):
    payload={'organic_results':[{'position':1,'title':'SBI contact','link':'https://sbi.bank.in','snippet':'1800 1234'},{'position':2,'title':'SBI care','link':'https://sbi-care.example'}],'ads':[{'title':'SBI care','link':'https://sbi-instant.example'}],'related_questions':[{'title':'SBI question'}]}
    for _ in range(2):pipeline.ingest(payload,'sbi-en-1','google','Delhi','Delhi','en')
    summary=client.get('/api/map').json()['summary']
    # Official rank 1 weight 1; suspicious organic rank 2 weight .5; suspicious ad weight 1.5.
    assert summary['exposure']==66.7 and summary['n']==6 and summary['n_runs']==2
    assert client.get('/api/map?window=1&category=logistics').json()['summary']['exposure'] is None


def test_csv_formula_injection_is_escaped():
    assert "'=HYPERLINK" in csv_text([{'entity':'=HYPERLINK("evil")','risk':20}])


def test_review_invalidated_when_cluster_grows(client,db,pipeline,risky_payload):
    pipeline.ingest(risky_payload,'sbi-en-1','google','Delhi','Delhi','en')
    campaign=db.one('SELECT * FROM campaign')
    client.post('/api/admin/campaigns/'+campaign['id']+'/review',headers=ADMIN,json={'decision':'approved','reviewer':'Staff review'})
    pipeline.ingest(risky_payload,'sbi-en-1','google','Delhi','Delhi','en')
    assert db.one('SELECT review_state FROM campaign')['review_state']=='pending'
    assert client.get('/api/campaigns').json()['items']==[]
