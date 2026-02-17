# UAT / Core Scenarios

## Prerequisites
- Run migrations:
```bash
./venv/bin/python manage.py migrate
```
- Seed demo data:
```bash
./venv/bin/python manage.py seed_demo_data --reset
```
- Start server:
```bash
./venv/bin/python manage.py runserver
```

## Test Accounts
- `admin@sausalito.com` / `admin1234` (`SUPER_ADMIN`)
- `ops@sausalito.com` / `admin1234` (`OPS`)
- `finance@sausalito.com` / `admin1234` (`FINANCE`)
- `readonly@sausalito.com` / `admin1234` (`READ_ONLY`)

## UAT Scenarios
1. RBAC enforcement (`ADM-SEC-001`)
- Login as `OPS`, call settlement update API.
- Expected: `403 FORBIDDEN`.

2. Return/refund idempotency (`ADM-CS-004`, `ADM-CS-005`)
- As `FINANCE`, send same return update (`REFUNDED`) with same `idempotency_key` twice.
- Expected: first request mutates state, second returns replay; no duplicate refund side effects.

3. PII masking (`ADM-SEC-004`, `ADM-ORD-002`, `ADM-CUST-001`)
- As `OPS`, call `/admin/orders`.
- Expected: phone/address/email masked.
- As `FINANCE`, call `/admin/orders`.
- Expected: full values returned and `PII_FULL_VIEW` audit event recorded.

4. Status transition validation (`ADM-SHIP-001`, `ADM-SHIP-002`)
- Try shipping transition `READY -> DELIVERED` directly.
- Expected: `400 VALIDATION_ERROR`.

5. Role change audit (`ADM-SEC-001`, `ADM-SEC-003`)
- As `SUPER_ADMIN`, change staff `admin_role`.
- Expected: role change succeeds and `ADMIN_ROLE_CHANGED` audit log exists.

## Automated Test Command
```bash
./venv/bin/python manage.py test apps.accounts.tests.test_admin_security --verbosity 2
```
