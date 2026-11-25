# Verified local build — QA notes

The synthetic demo is designed to run offline after dependencies are installed. It does **not** process real financial transactions or make live bank API calls.

## Checks performed

- Python regression and integration suite: `python -m pytest -q` — **19 passed**.
- Disposable-database API smoke test: `python -m app.smoke` — **5 workflow stages passed**.
- JavaScript syntax: `node --check static/app.js` — **passed**.
- Headless Chromium UI exercise: actual HTML/CSS/JS connected to FastAPI TestClient in-process — **passed** for overview, member intake, case timeline, analyst decision history, SQL analysis, and rule comparison; **no JavaScript page errors**. The browser's direct network requests were blocked by the audit environment, so its API calls were bridged in-process; this is not a public-hosting test.
- Decision memo generated directly from SQL + Python: `python -m app.report` — **passed**.

## Important behavioral checks

- A support allegation remains unresolved until an analyst records a separate finding.
- Multiple contacts for the same payment do not inflate payment value.
- Payment selection is required before creating a dispute case.
- Payment-to-member linkage is checked server-side using synthetic member IDs.
- A case's dispositions append to history rather than modifying the independent synthetic outcome ledger.
- Unresolved labels are excluded from observed-label precision/recall and shown separately.
- Same 45-day maturity window is applied to monthly payment cohorts and available labels.
- Baseline and new-rule decisions use **payment-time-only inputs**.
- `READ_ONLY_DEMO=1` blocks all state-changing API calls and disables front-end write controls.
- `/health` indicates process liveness, while `/ready` also verifies SQLite availability.
- Re-running `python -m app.seed` without `--reset` does not delete newly entered local complaints/dispositions.

## Not included / limitations

- Not a production-grade bank platform: no authentication, role-based permissions, dispute adjudication integrations, or real transaction processing.
- Public deployment must run with `READ_ONLY_DEMO=1`, or add real authn/authz and abuse protection before allowing writes.
- Concurrent user/load testing, persistent cloud deployment, service-level objectives, and live voice/LLM flows are **not** part of this fraud analytics demo.
- Synthetic loss coverage is **not** realized fraud savings; the rules are illustrative and require forward-looking shadow evaluation.

A passing test suite cannot guarantee zero defects. Always run tests locally before publishing or interviewing.
