from scamserp.scheduler import SchedulerRunner, coverage


def test_single_scheduler_owner_and_clean_shutdown(client,db,app):
    calls=[]
    app.state.collector.scheduled=lambda limit:calls.append(limit)
    first=SchedulerRunner(db,app.state.collector,app.state.service)
    second=SchedulerRunner(db,app.state.collector,app.state.service)
    try:
        assert first.start()
        assert not second.start()
        first.tick()
        assert calls
        assert coverage(db,app.state.collector)['scheduler']['state']=='running'
    finally:
        first.stop()
    assert coverage(db,app.state.collector)['scheduler']['state']=='stopped'


def test_coverage_does_not_promise_full_cadence_at_small_budget(client,app):
    data=client.get('/api/coverage').json()
    assert data['planned_cells']>data['active_queries']
    assert data['minimum_monthly_requests_for_full_cadence']>data['configured_monthly_cap']
    assert not data['full_cadence_budget_sufficient']
