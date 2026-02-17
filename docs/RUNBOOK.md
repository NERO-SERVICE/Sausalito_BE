# Deployment Runbook (Admin P0)

## 1) Environment
- Backend root: `sausalito_be`
- Required env: `.env` (`DB_*`, JWT, CORS, CSRF, payment keys)
- Entry point: `./venv/bin/python manage.py runserver` (local)

## 2) Deployment Steps
1. Pull source and install deps
```bash
pip install -r requirements/local.txt
```
2. Apply migrations
```bash
./venv/bin/python manage.py migrate
```
3. Seed (non-prod only)
```bash
./venv/bin/python manage.py seed_demo_data --reset
```
4. Smoke checks
- Admin login
- `/api/v1/admin/orders` (RBAC + masking)
- Return update with `idempotency_key`
- `/api/v1/admin/audit-logs`

## 3) Rollback Plan
1. Application rollback
- Re-deploy previous stable build/tag.
2. DB rollback
- If rollback requires schema revert, apply reverse migration:
```bash
./venv/bin/python manage.py migrate accounts 0003
```
- Caution: dropping `AuditLog` / `IdempotencyRecord` removes new audit/idempotency data.
3. Validation after rollback
- Admin login and order list retrieval
- Settlement and return endpoints respond without 5xx

## 4) Operational Monitoring
- Track spikes:
  - `FORBIDDEN` (RBAC mismatch)
  - `VALIDATION_ERROR` for invalid transitions
  - refund/settlement mutation volume
- Audit trail checks:
  - `REFUND_EXECUTED`
  - `SETTLEMENT_UPDATED`
  - `ADMIN_ROLE_CHANGED`
  - `PII_FULL_VIEW`

## 5) OpenAPI Export
```bash
./venv/bin/python manage.py spectacular --file openapi.yaml
```
