"""Reproducible synthetic data. Never use in a production banking environment.

Scenario planting is deliberately kept here, not in payment features or rules.
"""
import argparse
import random
import sqlite3
from datetime import datetime, timedelta
from app.db import DB_PATH, connect, initialize

SEED = 2266

def stamp(value):
    return value.strftime('%Y-%m-%dT%H:%M:%S')

def seed(reset=False):
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        if not reset:
            try:
                with sqlite3.connect(DB_PATH) as existing:
                    size = existing.execute('SELECT COUNT(*) FROM payments').fetchone()[0]
                if size > 0:
                    print(f'Database already contains {size} payments; leaving existing cases and decisions untouched.')
                    print('To intentionally rebuild synthetic data, stop the server and run: python -m app.seed --reset')
                    return
            except sqlite3.Error as exc:
                raise SystemExit('Existing database cannot be read; back it up and use --reset if you intend to replace it.') from exc
            raise SystemExit('Existing empty database found; use --reset if you intend to replace it.')
        DB_PATH.unlink()
    db = connect()
    initialize(db)
    rng = random.Random(SEED)
    payments = []
    events = []
    complaints = []
    outcomes = []
    counts = {'payments': 0, 'complaints': 0, 'fraud': 0}
    n = 0
    c = 0
    e = 0
    start = datetime(2026, 7, 1)
    last_payment_times = {}
    for day_index in range(92):
        day = start + timedelta(days=day_index)
        month = day.month
        daily = {7: 40, 8: 64, 9: 84}[month]
        cluster_member = None
        for i in range(daily):
            n += 1
            payment_id = f'PAY-{n:06d}'
            if i % 15 == 0:
                cluster_member = f'MBR-{rng.randint(1, 1400):04d}'
            member = cluster_member if i % 15 in (0,1,2,3) else f'MBR-{rng.randint(1, 1400):04d}'
            spacing = 86000 // daily
            # Four successive multi-bill payments by the same member occur close together.
            # All other payments occur later in the daily event stream.
            seconds = (i // 15 * 15) * spacing + (i % 15) * 40 if i % 15 in (0,1,2,3) else i * spacing
            time = day + timedelta(seconds=seconds)
            amount = rng.randint(450, 32000) * 100
            flow = rng.choices(['credit_card_bill','rent','utilities'], [0.72,0.13,0.15])[0]
            new_device = int(rng.random() < 0.19)
            history = last_payment_times.setdefault(member, [])
            history[:] = [seen for seen in history if time-timedelta(hours=1) <= seen < time]
            velocity = len(history)  # Causal, strictly prior member payments within one hour.
            history.append(time)
            age = 0 if new_device else rng.randint(14, 600)
            status = 'pending' if rng.random() < 0.025 else 'success'
            # Aug: posting-delay incident; September: higher payment volume and fraud concentration.
            posting_delay = status == 'success' and month == 8 and flow == 'credit_card_bill' and rng.random() < 0.23
            if posting_delay:
                post_hours = rng.randint(48, 96)
            else:
                post_hours = rng.randint(0, 4)
            fraud_rate = 0.008 if month != 9 else 0.017
            if new_device and amount >= 1200000:
                fraud_rate += 0.085 if month == 9 else 0.055
            if velocity >= 3 and amount >= 700000:
                fraud_rate += 0.075 if month == 9 else 0.025
            is_fraud = rng.random() < fraud_rate and status == 'success'
            if is_fraud: counts['fraud'] += 1
            payments.append((payment_id,member,stamp(time),amount,flow,status,new_device,velocity,age))
            e += 1; events.append((f'EVT-{e:07d}',payment_id,stamp(time),'initiated','Payment submitted'))
            e += 1; events.append((f'EVT-{e:07d}',payment_id,stamp(time+timedelta(minutes=1)),'status',status.upper()))
            if status == 'success':
                e += 1; events.append((f'EVT-{e:07d}',payment_id,stamp(time+timedelta(hours=post_hours)),'posted',f'Ledger posting after {post_hours} hours'))
            # All outcomes are synthetic, post-payment investigation outcomes, not rule inputs.
            # Unknown outcomes remain separate and are excluded from resolved-label precision/recall.
            if status == 'pending' or (not is_fraud and rng.random() < 0.13):
                outcome, available, loss = 'unresolved', None, 0
            elif is_fraud:
                delay = rng.randint(8, 54)
                outcome, available, loss = 'confirmed_fraud', stamp(time + timedelta(days=delay)), int(amount*0.78)
            else:
                outcome, available, loss = 'genuine', stamp(time + timedelta(days=rng.randint(2, 18))), 0
            outcomes.append((payment_id,outcome,available,loss,'synthetic_followup'))
            # A complaint can represent fraud, a posting issue, or ordinary confusion.
            complaint_probability = 0.82 if is_fraud else (0.56 if posting_delay else 0.014)
            if rng.random() < complaint_probability:
                c += 1
                opened = time + timedelta(days=rng.randint(1,7) if is_fraud else rng.randint(0,4))
                complaints.append((f'CMP-{c:06d}',payment_id,member,stamp(opened),'unrecognized_payment','Member requested investigation of a credit-card bill payment'))
                if rng.random() < (0.33 if posting_delay else 0.08):
                    c += 1
                    complaints.append((f'CMP-{c:06d}',payment_id,member,stamp(opened+timedelta(hours=12)),'repeat_contact','Member followed up about the same payment'))
    # Explicit deterministic unresolved complaint, with independent payment-time inputs.
    for idx,p in enumerate(payments):
        if p[5]=='pending':
            pid,mid,t = p[0],p[1],datetime.fromisoformat(p[2])
            c += 1
            complaints.append((f'CMP-{c:06d}',pid,mid,stamp(t+timedelta(days=1)),'unrecognized_payment','Outcome pending investigation'))
            break
    with db:
        db.executemany('INSERT INTO payments VALUES (?,?,?,?,?,?,?,?,?)',payments)
        db.executemany('INSERT INTO payment_events VALUES (?,?,?,?,?)',events)
        db.executemany('INSERT INTO complaints VALUES (?,?,?,?,?,?)',complaints)
        db.executemany('INSERT INTO outcomes VALUES (?,?,?,?,?)',outcomes)
    db.close()
    print(f'Seeded {len(payments)} payments, {len(complaints)} contacts, {counts["fraud"]} synthetic confirmed-fraud outcomes (seed={SEED}).')
    print(f'Database: {DB_PATH}')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Seed deterministic synthetic fraud lab')
    parser.add_argument('--reset', action='store_true', help='Destructively rebuild all synthetic data and wipe locally recorded cases')
    args = parser.parse_args()
    seed(reset=args.reset)
