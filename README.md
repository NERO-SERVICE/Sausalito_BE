# sausalito_be

## Stack
- Django 5.x
- Django REST Framework
- JWT (`djangorestframework-simplejwt`)
- drf-spectacular
- django-cors-headers

## Repository Scope
- 이 저장소(`sausalito_be`)가 배포/CI/CD/컨테이너 운영의 단일 기준점이다.
- Docker Compose, GitHub Actions, 배포 스크립트는 모두 이 루트에서 실행한다.

## P0 Focus Implemented
- RBAC server enforcement for all admin APIs (`admin_role` + permission matrix)
- Audit logging (`AuditLog`) for critical security/financial actions
- Idempotency support (`IdempotencyRecord`) for admin mutation endpoints
- Order/return/product-order transition validation
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
cp .env.local.example .env
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

## Pre-Deploy Check
```bash
./scripts/predeploy_check.sh
```
- `.env.prod` 필수값/placeholder/보안 설정을 점검합니다.
- `localhost` 허용값은 사전 검증 단계에서 경고(warn)로 처리됩니다.

## Environment Files
- 로컬 개발: `.env.local.example` -> `.env` 복사 후 값 수정
- 운영 배포: `.env.prod.example` -> `.env.prod` 복사 후 값 수정


## Notes
- Admin mutation APIs accept `idempotency_key` in body (or `Idempotency-Key` header for delete flows).
- Full PII response is intentionally limited by role and recorded in audit logs.
