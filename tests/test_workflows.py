from app import db
from app.analytics import baseline, proposed


def test_health_and_root(client):
    assert client.get('/health').json()=={'status':'healthy'}
    assert client.get('/').status_code==200
    assert client.get('/demo').status_code==200


def test_complaint_requires_payment_selection(client):
    sample=client.get('/api/overview').json()['example']
    response=client.post('/api/complaints',json={'member_id':sample['member_id'],'note':'Payment was not recognised'})
    assert response.status_code==409
    assert response.json()['detail']['candidate_payments']


def test_complaint_never_labels_fraud(client):
    sample=client.get('/api/overview').json()['example']
    before=client.get('/api/payments/'+sample['payment_id']).json()['synthetic_outcome']
    count_before=len(client.get('/api/payments/'+sample['payment_id']).json()['complaints'])
    response=client.post('/api/complaints',json={**sample,'note':'I did not authorise this payment'})
    assert response.status_code==201
    assert response.json()['status']=='unresolved'
    after=client.get('/api/payments/'+sample['payment_id']).json()
    assert len(after['complaints'])==count_before+1
    assert after['synthetic_outcome']==before


def test_payment_cannot_be_linked_to_wrong_member(client):
    sample=client.get('/api/overview').json()['example']
    response=client.post('/api/complaints',json={'member_id':'MBR-DOES-NOT-OWN','payment_id':sample['payment_id'],'note':'Unrecognised credit card payment'})
    assert response.status_code==403


def test_duplicate_contacts_do_not_duplicate_payment_amount(client):
    with db.connect() as con:
        wrong=con.execute('''SELECT SUM(p.amount_paise) total FROM payments p JOIN complaints c ON c.payment_id=p.payment_id JOIN payment_events e ON e.payment_id=p.payment_id''').fetchone()['total']
        correct=con.execute('''SELECT SUM(amount_paise) total FROM payments p WHERE EXISTS(SELECT 1 FROM complaints c WHERE c.payment_id=p.payment_id) AND EXISTS(SELECT 1 FROM payment_events e WHERE e.payment_id=p.payment_id)''').fetchone()['total']
        assert wrong > correct
        count=con.execute('SELECT COUNT(*) AS n FROM (SELECT payment_id FROM complaints GROUP BY payment_id HAVING COUNT(*)>1)').fetchone()['n']
        assert count>0


def test_pending_unresolved_and_late_labels(client):
    with db.connect() as con:
        pending=con.execute("SELECT COUNT(*) AS n FROM payments WHERE status='pending'").fetchone()['n']
        unresolved=con.execute("SELECT COUNT(*) AS n FROM outcomes WHERE outcome='unresolved'").fetchone()['n']
        late=con.execute("SELECT COUNT(*) AS n FROM outcomes o JOIN payments p ON p.payment_id=o.payment_id WHERE o.outcome='confirmed_fraud' AND julianday(o.available_at)-julianday(p.created_at)>=25").fetchone()['n']
        assert pending>0 and unresolved>0 and late>0


def test_disposition_is_append_only_not_outcome_mutation(client):
    example=client.get('/api/cases').json()['cases'][0]
    original=client.get('/api/payments/'+example['payment_id']).json()['synthetic_outcome']
    new=client.post(f"/api/cases/{example['complaint_id']}/disposition",json={'status':'genuine','rationale':'Member verified the scheduled bill payment'})
    assert new.status_code==200
    assert client.get('/api/payments/'+example['payment_id']).json()['synthetic_outcome']==original
    with db.connect() as con:
        n=con.execute('SELECT COUNT(*) n FROM dispositions WHERE complaint_id=?',(example['complaint_id'],)).fetchone()['n']
        assert n==1


def test_rule_evaluation_no_future_fields_and_coherent_counts(client):
    assert baseline({'device_new':1,'amount_paise':1_200_000})
    assert proposed({'payments_last_hour':3,'amount_paise':700_000})
    data=client.get('/api/rules').json()
    assert data['combined']['reviews']>=data['baseline']['reviews']
    assert data['combined']['confirmed_fraud']>=data['baseline']['confirmed_fraud']
    assert data['incremental']['reviews']==data['combined']['reviews']-data['baseline']['reviews']
    assert data['combined']['reviews']==data['combined']['confirmed_fraud']+data['combined']['genuine_reviews']+data['combined']['unresolved_reviews']


def test_mature_cohorts_and_nonnegative_loss(client):
    data=client.get('/api/investigation').json()
    assert [x['period'] for x in data['monthly']]==['2026-07','2026-08','2026-09']
    assert all(x['confirmed_loss_bps']>=0 for x in data['monthly'])
    assert data['monthly'][1]['tickets']>data['monthly'][0]['tickets']


def test_public_readonly_demo_rejects_writes(client,monkeypatch):
    monkeypatch.setenv('READ_ONLY_DEMO','1')
    sample=client.get('/api/overview').json()['example']
    response=client.post('/api/complaints',json={**sample,'note':'Unrecognized bill payment'})
    assert response.status_code==403
    example=client.get('/api/cases').json()['cases'][0]
    response=client.post(f"/api/cases/{example['complaint_id']}/disposition",
                         json={'status':'confirmed_fraud','rationale':'Evidence has been checked carefully'})
    assert response.status_code==403


def test_payment_velocity_is_derived_from_prior_member_events(client):
    with db.connect() as con:
        row=con.execute('''SELECT p.payment_id,p.member_id,p.created_at,p.payments_last_hour,
            (SELECT COUNT(*) FROM payments prev WHERE prev.member_id=p.member_id
               AND prev.created_at<p.created_at AND prev.created_at>=DATETIME(p.created_at,'-1 hour')) AS prior_count
            FROM payments p WHERE p.payments_last_hour >= 3 LIMIT 1''').fetchone()
        assert row is not None
        # SQL datetime comparison needs explicit normalization because stored timestamps use 'T'.
        earlier=con.execute('''SELECT COUNT(*) AS n FROM payments
             WHERE member_id=? AND datetime(created_at)<datetime(?)
                   AND datetime(created_at)>=datetime(?,'-1 hour')''',(row['member_id'],row['created_at'],row['created_at'])).fetchone()['n']
        assert earlier == row['payments_last_hour']
