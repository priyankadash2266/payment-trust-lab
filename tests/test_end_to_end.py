"""Real API flows on disposable seeded SQLite databases; no network or paid APIs."""
from datetime import datetime, timedelta
import os
from pathlib import Path

from app import db, seed, main
from app.analytics import investigation, evaluate


def test_member_to_analyst_workflow(client):
    overview = client.get('/api/overview').json()
    example = overview['example']
    member_id, payment_id = example['member_id'], example['payment_id']

    choices = client.get(f'/api/members/{member_id}/payments')
    assert choices.status_code == 200
    assert payment_id in [p['payment_id'] for p in choices.json()['payments']]

    ambiguous = client.post('/api/complaints', json={
        'member_id': member_id,
        'note': 'This payment looks unfamiliar',
    })
    assert ambiguous.status_code == 409
    assert len(ambiguous.json()['detail']['candidate_payments']) >= 1

    original_payment = client.get(f'/api/payments/{payment_id}').json()
    original_outcome = original_payment['synthetic_outcome']
    original_rules = client.get('/api/rules').json()
    creation = client.post('/api/complaints', json={
        'member_id': f' {member_id} ',
        'payment_id': payment_id,
        'reason': 'unrecognized_payment',
        'note': '  I do not recognize this bill payment.  ',
    })
    assert creation.status_code == 201
    case_id = creation.json()['complaint_id']
    assert creation.json()['status'] == 'unresolved'

    detail = client.get(f'/api/cases/{case_id}').json()
    assert detail['case']['note'] == 'I do not recognize this bill payment.'
    assert detail['case']['payment_id'] == payment_id
    assert detail['dispositions'] == []

    timeline = client.get(f'/api/payments/{payment_id}').json()
    assert len(timeline['events']) >= 2
    assert any(c['complaint_id'] == case_id for c in timeline['complaints'])
    assert timeline['synthetic_outcome'] == original_outcome

    decision = client.post(f'/api/cases/{case_id}/disposition', json={
        'status': 'genuine',
        'rationale': 'Checked posting events, contacted member, confirmed payment.',
    })
    assert decision.status_code == 200
    assert decision.json()['analyst_disposition'] == 'genuine'

    correction = client.post(f'/api/cases/{case_id}/disposition', json={
        'status': 'confirmed_fraud',
        'rationale': 'Follow-up evidence changed the earlier analyst assessment.',
    })
    assert correction.status_code == 200
    refreshed = client.get(f'/api/cases/{case_id}').json()
    assert [row['status'] for row in refreshed['dispositions']] == ['genuine', 'confirmed_fraud']
    assert all(row['rationale'] for row in refreshed['dispositions'])
    assert any(c['complaint_id'] == case_id and c['analyst_disposition'] == 'confirmed_fraud'
               for c in client.get('/api/cases?limit=100').json()['cases'])

    # The complaint and analyst decision must never change the independent outcome ledger
    # or the fixed, payment-time retrospective evaluation.
    assert client.get(f'/api/payments/{payment_id}').json()['synthetic_outcome'] == original_outcome
    assert client.get('/api/rules').json() == original_rules


def test_readiness_distinguishes_missing_database_from_live_process(client, tmp_path, monkeypatch):
    assert client.get('/ready').status_code == 200
    assert client.get('/health').json() == {'status': 'healthy'}
    missing_db = tmp_path / 'database_does_not_exist.sqlite3'
    monkeypatch.setattr(main, 'DB_PATH', missing_db)
    assert client.get('/ready').status_code == 503
    assert client.get('/api/overview').status_code == 503
    assert client.get('/health').status_code == 200


def test_invalid_requests_return_meaningful_status_codes(client):
    assert client.get('/api/payments/PAY-INVALID').status_code == 404
    assert client.get('/api/cases/CMP-INVALID').status_code == 404
    assert client.get('/api/cases?limit=500').status_code == 422
    assert client.get('/api/cases?limit=abc').status_code == 422
    assert client.get('/api/members/NONEXISTENT/payments').json()['payments'] == []
    assert client.post('/api/complaints', json={'member_id': '   ', 'note': 'Missing member'}).status_code == 422
    assert client.post('/api/complaints', json={'member_id': 'M', 'note': '  ABC   '}).status_code == 422
    assert client.post('/api/complaints', json={'member_id': 'M', 'note': 'Enough chars', 'reason': 'auto_fraud'}).status_code == 422
    cid = client.get('/api/cases').json()['cases'][0]['complaint_id']
    assert client.post(f'/api/cases/{cid}/disposition', json={
        'status': 'unresolved', 'rationale': 'This decision is not allowed'
    }).status_code == 422
    assert client.post(f'/api/cases/{cid}/disposition', json={
        'status': 'genuine', 'rationale': '   short  '
    }).status_code == 422


def test_read_only_mode_does_not_modify_case_history(client, monkeypatch):
    monkeypatch.setenv('READ_ONLY_DEMO', '1')
    assert client.get('/api/meta').json()['read_only'] is True
    case = client.get('/api/cases').json()['cases'][0]
    before = client.get(f"/api/cases/{case['complaint_id']}").json()
    assert client.post('/api/complaints', json={
        'member_id': case['member_id'], 'payment_id': case['payment_id'], 'note': 'A new complaint in read only mode'
    }).status_code == 403
    assert client.post(f"/api/cases/{case['complaint_id']}/disposition", json={
        'status': 'genuine', 'rationale': 'Should never be saved in preview mode'
    }).status_code == 403
    assert client.get(f"/api/cases/{case['complaint_id']}").json() == before
    assert client.get('/api/overview').status_code == 200
    assert client.get('/api/rules').status_code == 200


def test_frontend_assets_and_api_contract(client):
    html = client.get('/demo')
    js = client.get('/static/app.js')
    css = client.get('/static/style.css')
    assert html.status_code == js.status_code == css.status_code == 200
    for required in ('overview', 'cases', 'analysis', 'rules', 'support', 'caseList', 'paymentDetail'):
        assert f'id="{required}"' in html.text
    for url in ('/api/overview', '/api/cases', '/api/payments/', '/api/investigation', '/api/rules', '/api/meta'):
        assert url in js.text
    assert 'case-inspector' in css.text


def test_time_window_boundaries_are_inclusive_only_within_window(client):
    with db.session() as con:
        row = con.execute('''SELECT * FROM payments p WHERE p.status='success'
             AND p.created_at < '2026-08-01' AND NOT EXISTS (
                SELECT 1 FROM complaints c WHERE c.payment_id=p.payment_id)
             LIMIT 1''').fetchone()
        before = investigation()['monthly'][0]['tickets']
        on_limit = datetime.fromisoformat(row['created_at']) + timedelta(days=45)
        beyond = on_limit + timedelta(minutes=1)
        con.execute('''INSERT INTO complaints(complaint_id,payment_id,member_id,created_at,reason,note)
                 VALUES(?,?,?,?,?,?)''', ('CMP-BOUNDARY-IN', row['payment_id'], row['member_id'], on_limit.isoformat(timespec='seconds'), 'other', 'Boundary exactly 45 days'))
        con.execute('''INSERT INTO complaints(complaint_id,payment_id,member_id,created_at,reason,note)
                 VALUES(?,?,?,?,?,?)''', ('CMP-BOUNDARY-OUT', row['payment_id'], row['member_id'], beyond.isoformat(timespec='seconds'), 'other', 'After forty five days'))
    after = investigation()['monthly'][0]['tickets']
    assert after - before == 1


def test_posting_is_matured_and_payment_grain(client):
    d = client.get('/api/investigation').json()
    assert len(d['posting']) == 3
    for month, posting in zip(d['monthly'], d['posting']):
        assert posting['period'] == month['period']
        assert posting['successful_payments'] == month['successful_payments']
        assert 0 <= posting['posted_after_24h'] <= posting['successful_payments']
    assert any(row['delayed_payment_contacts'] for row in d['posting'])


def test_seed_does_not_delete_new_cases_while_reseed_requires_explicit_reset(client, capsys):
    original = client.get('/api/overview').json()['counts']['contacts']
    sample = client.get('/api/overview').json()['example']
    created = client.post('/api/complaints', json={
        **sample, 'note': 'Save case across repeated seed command'
    })
    assert created.status_code == 201
    seed.seed()  # Equivalent to python -m app.seed without --reset.
    assert 'leaving existing cases' in capsys.readouterr().out
    assert client.get('/api/overview').json()['counts']['contacts'] == original + 1
    assert client.get(f"/api/cases/{created.json()['complaint_id']}").status_code == 200
