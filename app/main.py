"""Payment Trust Lab API. Synthetic data and intentionally local-only analyst writes."""
from datetime import datetime, timezone
import os
from uuid import uuid4
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from .db import ROOT, DB_PATH, session
from .analytics import AS_OF, evaluate, investigation

app = FastAPI(
    title="Payment Trust Lab",
    version="1.1.0",
    description="Reproducible, synthetic payment dispute and fraud investigation API",
)
app.mount('/static', StaticFiles(directory=ROOT / 'static'), name='static')

@app.middleware('http')
async def prevent_stale_demo_data(request: Request, call_next):
    response = await call_next(request)
    if request.url.path == '/demo' or request.url.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
    return response



class ComplaintIn(BaseModel):
    member_id: str = Field(min_length=1, max_length=40)
    payment_id: str | None = Field(default=None, max_length=40)
    reason: Literal['unrecognized_payment', 'posting_delay', 'other'] = 'unrecognized_payment'
    note: str = Field(min_length=6, max_length=500)

    @field_validator('member_id', 'payment_id', 'note')
    @classmethod
    def strip_text(cls, value):
        return value.strip() if isinstance(value, str) else value


class DispositionIn(BaseModel):
    status: Literal['confirmed_fraud', 'genuine']
    rationale: str = Field(min_length=10, max_length=500)

    @field_validator('rationale')
    @classmethod
    def strip_rationale(cls, value):
        return value.strip()


def get_payment(db, payment_id: str) -> dict:
    row = db.execute('SELECT * FROM payments WHERE payment_id=?', (payment_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail='Payment not found')
    return dict(row)


def ensure_mutable() -> None:
    if os.environ.get('READ_ONLY_DEMO', '').strip().lower() in ('1', 'true', 'yes'):
        raise HTTPException(status_code=403, detail='This demo is read-only. Run it locally with writes enabled.')


def db_required() -> None:
    if not DB_PATH.is_file():
        raise HTTPException(status_code=503, detail='Demo database unavailable. Run python -m app.seed first.')
    try:
        with session() as db:
            db.execute('SELECT 1 FROM payments LIMIT 1').fetchone()
    except Exception as exc:
        # Never reveal connection details or SQL internals in an HTTP error.
        raise HTTPException(status_code=503, detail='Demo database is not initialized. Run python -m app.seed --reset.') from exc


@app.get('/')
def root():
    return {'message': 'Welcome to Banking AI Agent', 'demo': '/demo'}


@app.get('/health', summary='Liveness check')
def health():
    return {'status': 'healthy'}


@app.get('/ready', summary='Readiness check (includes database)')
def ready():
    db_required()
    return {'status': 'ready', 'database': 'available'}


@app.get('/api/meta')
def metadata():
    return {
        'name': 'Payment Trust Lab',
        'read_only': os.environ.get('READ_ONLY_DEMO', '').strip().lower() in ('1', 'true', 'yes'),
        'synthetic_data': True,
        'analytics_as_of': AS_OF.isoformat(),
    }


@app.get('/demo', include_in_schema=False)
def demo():
    return FileResponse(ROOT / 'static' / 'index.html')


@app.get('/api/overview')
def overview():
    db_required()
    with session() as db:
        summary = db.execute('''SELECT (SELECT COUNT(*) FROM payments) AS payments,
             (SELECT COUNT(*) FROM complaints) AS contacts,
             (SELECT COUNT(DISTINCT payment_id) FROM complaints) AS disputed_payments,
             (SELECT COUNT(*) FROM outcomes WHERE outcome='confirmed_fraud') AS confirmed_fraud''').fetchone()
        example = db.execute('''SELECT member_id,payment_id FROM complaints
            WHERE reason='unrecognized_payment' ORDER BY created_at LIMIT 1''').fetchone()
    return {'counts': dict(summary), 'example': dict(example) if example else None}


@app.get('/api/members/{member_id}/payments')
def member_payments(member_id: str):
    db_required()
    with session() as db:
        result = db.execute('''SELECT payment_id,member_id,created_at,amount_paise,product_flow,status
             FROM payments WHERE member_id=? ORDER BY created_at DESC LIMIT 100''', (member_id,)).fetchall()
    return {'member_id': member_id, 'payments': [dict(x) for x in result]}


@app.post('/api/complaints', status_code=201)
def create_complaint(body: ComplaintIn):
    ensure_mutable()
    db_required()
    # Normalized member identifiers avoid an accidental mismatch on surrounding whitespace.
    if not body.member_id:
        raise HTTPException(status_code=422, detail='member_id must not be blank')
    if not body.note or len(body.note) < 6:
        raise HTTPException(status_code=422, detail='Provide a descriptive complaint (6+ characters)')
    with session() as db:
        if not body.payment_id:
            choices = db.execute('''SELECT payment_id,created_at,amount_paise,product_flow,status
                FROM payments WHERE member_id=? ORDER BY created_at DESC LIMIT 100''', (body.member_id,)).fetchall()
            if not choices:
                raise HTTPException(status_code=404, detail='No payments found for this member')
            raise HTTPException(status_code=409, detail={
                'message': 'Select a payment before opening a case',
                'candidate_payments': [dict(x) for x in choices]
            })
        payment = get_payment(db, body.payment_id)
        if payment['member_id'] != body.member_id:
            raise HTTPException(status_code=403, detail='Payment does not belong to member')
        complaint_id = 'CMP-NEW-' + uuid4().hex[:10].upper()
        now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
        db.execute('''INSERT INTO complaints
            (complaint_id,payment_id,member_id,created_at,reason,note)
            VALUES (?,?,?,?,?,?)''',
            (complaint_id, body.payment_id, body.member_id, now, body.reason, body.note))
    return {
        'complaint_id': complaint_id,
        'payment_id': body.payment_id,
        'status': 'unresolved',
        'message': 'Member allegation recorded. No fraud finding has been made.',
    }


@app.get('/api/cases')
def cases(limit: int = Query(default=60, ge=1, le=100)):
    db_required()
    with session() as db:
        result = db.execute('''SELECT c.*,p.amount_paise,p.product_flow,p.status AS payment_status,
            (SELECT COUNT(*) FROM complaints c2 WHERE c2.payment_id=c.payment_id) AS contact_count,
            (SELECT d.status FROM dispositions d WHERE d.complaint_id=c.complaint_id
                 ORDER BY d.disposition_id DESC LIMIT 1) AS analyst_disposition
            FROM complaints c JOIN payments p ON p.payment_id=c.payment_id
            ORDER BY c.created_at DESC, c.complaint_id DESC LIMIT ?''', (limit,)).fetchall()
    return {'cases': [dict(x) for x in result]}


@app.get('/api/cases/{complaint_id}')
def case_detail(complaint_id: str):
    """A case has its own history; independent outcomes remain in the payment ledger."""
    db_required()
    with session() as db:
        case = db.execute('''SELECT c.*,p.amount_paise,p.product_flow,p.status AS payment_status
            FROM complaints c JOIN payments p ON p.payment_id=c.payment_id
            WHERE c.complaint_id=?''', (complaint_id,)).fetchone()
        if case is None:
            raise HTTPException(status_code=404, detail='Case not found')
        history = db.execute('''SELECT disposition_id,complaint_id,status,decided_at,rationale
            FROM dispositions WHERE complaint_id=? ORDER BY disposition_id ASC''', (complaint_id,)).fetchall()
    return {'case': dict(case), 'dispositions': [dict(d) for d in history]}


@app.get('/api/payments/{payment_id}')
def payment_detail(payment_id: str):
    db_required()
    with session() as db:
        payment = get_payment(db, payment_id)
        events = db.execute('''SELECT * FROM payment_events WHERE payment_id=?
            ORDER BY occurred_at,event_id''', (payment_id,)).fetchall()
        contacts = db.execute('''SELECT c.*,(SELECT d.status FROM dispositions d
                WHERE d.complaint_id=c.complaint_id ORDER BY d.disposition_id DESC LIMIT 1)
                AS analyst_disposition FROM complaints c WHERE c.payment_id=?
                ORDER BY c.created_at''', (payment_id,)).fetchall()
        outcome = db.execute('SELECT * FROM outcomes WHERE payment_id=?', (payment_id,)).fetchone()
    return {
        'payment': payment,
        'events': [dict(x) for x in events],
        'complaints': [dict(x) for x in contacts],
        'synthetic_outcome': dict(outcome) if outcome else None,
        'notice': 'Outcome is synthetic retrospective evidence, never a payment-time rule input.',
    }


@app.post('/api/cases/{complaint_id}/disposition')
def set_disposition(complaint_id: str, body: DispositionIn):
    ensure_mutable()
    db_required()
    if len(body.rationale) < 10:
        raise HTTPException(status_code=422, detail='Give at least 10 characters of rationale')
    with session() as db:
        exists = db.execute('SELECT complaint_id FROM complaints WHERE complaint_id=?', (complaint_id,)).fetchone()
        if exists is None:
            raise HTTPException(status_code=404, detail='Case not found')
        when = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
        cur = db.execute('''INSERT INTO dispositions(complaint_id,status,decided_at,rationale)
            VALUES (?,?,?,?)''', (complaint_id, body.status, when, body.rationale))
        disposition_id = cur.lastrowid
    return {
        'disposition_id': disposition_id,
        'complaint_id': complaint_id,
        'analyst_disposition': body.status,
        'notice': 'Append-only decision; independent synthetic outcome and rule metrics unchanged.',
    }


@app.get('/api/investigation')
def investigate():
    db_required()
    return investigation()


@app.get('/api/rules')
def rules():
    db_required()
    return evaluate()
