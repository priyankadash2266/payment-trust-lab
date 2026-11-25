"""One-command end-to-end API check using a disposable database.

Run `python -m app.smoke` after installing requirements-dev.txt.
Never modifies the main demo database.
"""
import os
import tempfile
from pathlib import Path

# The DB environment variable is resolved when app.db is imported.
with tempfile.TemporaryDirectory(prefix='payment-trust-smoke-') as directory:
    os.environ['FRAUD_LAB_DB'] = str(Path(directory) / 'smoke.sqlite3')
    os.environ.pop('READ_ONLY_DEMO', None)

    from fastapi.testclient import TestClient
    from .seed import seed
    from .main import app

    seed()
    client = TestClient(app)
    assert client.get('/ready').json()['status'] == 'ready'
    overview = client.get('/api/overview').json()
    sample = overview['example']

    missing_selection = client.post('/api/complaints', json={
        'member_id': sample['member_id'],
        'note': 'I do not recognize this payment',
    })
    assert missing_selection.status_code == 409

    created = client.post('/api/complaints', json={
        **sample,
        'note': 'I do not recognize this payment',
    })
    assert created.status_code == 201
    case_id = created.json()['complaint_id']
    assert client.get('/api/cases/' + case_id).json()['dispositions'] == []

    payment = client.get('/api/payments/' + sample['payment_id']).json()
    assert any(c['complaint_id'] == case_id for c in payment['complaints'])
    assert len(payment['events']) >= 2

    decision = client.post('/api/cases/' + case_id + '/disposition', json={
        'status': 'genuine',
        'rationale': 'Checked the bank posting event and verified with member',
    })
    assert decision.status_code == 200
    assert client.get('/api/cases/' + case_id).json()['dispositions'][-1]['status'] == 'genuine'
    assert len(client.get('/api/investigation').json()['monthly']) == 3
    rules = client.get('/api/rules').json()
    assert rules['combined']['reviews'] >= rules['baseline']['reviews']

    print('PASS: readiness and existing API endpoints')
    print('PASS: payment selection guard and complaint intake')
    print('PASS: payment event timeline and case history')
    print('PASS: analyst disposition and persistence')
    print('PASS: mature-cohort SQL analysis and fraud rule evaluation')
    print(f"Synthetic records: {overview['counts']['payments']} payments; {overview['counts']['contacts']} original contacts")
    print('Main project database was not changed.')
