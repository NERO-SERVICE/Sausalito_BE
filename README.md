# sausalito_be

## Stack
- Django 5.x
- Django REST Framework
- JWT (`djangorestframework-simplejwt`)
- drf-spectacular
- django-cors-headers

## P0 Focus Implemented
- RBAC server enforcement for all admin APIs (`admin_role` + permission matrix)
- Audit logging (`AuditLog`) for critical security/financial actions
- Idempotency support (`IdempotencyRecord`) for admin mutation endpoints
- Order/return/settlement transition validation
- PII role-based masking + full-view audit tracking

Reference docs:
- `docs/IMPLEMENTATION_PLAN.md`
- `docs/UAT.md`
- `docs/RUNBOOK.md`

## Quick Start
```bash
cd sausalito_be
python3 -m venv venv
source venv/bin/activate
pip install -r requirements/local.txt
cp .env.local.example .env.local
cp .env.local .env
./venv/bin/python manage.py migrate
./venv/bin/python manage.py seed_demo_data --reset
./venv/bin/python manage.py runserver
```

## Test
```bash
./venv/bin/python manage.py test apps.accounts.tests.test_admin_security --verbosity 2
```

## OpenAPI
- Swagger UI: `http://127.0.0.1:8000/api/docs/`
- JSON schema endpoint: `http://127.0.0.1:8000/api/schema/`
- Export file:
```bash
./venv/bin/python manage.py spectacular --file openapi.yaml
```

## Security Check (Before Push)
```bash
./scripts/check_sensitive.sh
```
- `.env`, `.env.local`, `.env.prod` 같은 실환경 파일은 git에 포함되지 않도록 강제 점검합니다.
- API 키/토큰/개인키 패턴이 추적 파일에 있으면 실패합니다.

## Demo Accounts
- Customer
  - `demo@sausalito.com` / `demo1234`
- Admin (`SUPER_ADMIN`)
  - `admin@sausalito.com` / `admin1234`
- Role-specific admins (all password `admin1234`)
  - `ops@sausalito.com`
  - `cs@sausalito.com`
  - `finance@sausalito.com`
  - `warehouse@sausalito.com`
  - `marketing@sausalito.com`
  - `readonly@sausalito.com`

## Notes
- Admin mutation APIs accept `idempotency_key` in body (or `Idempotency-Key` header for delete flows).
- Full PII response is intentionally limited by role and recorded in audit logs.
