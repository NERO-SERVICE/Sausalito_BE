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
- Object Storage 실검증이 필요하면 아래처럼 실행합니다.
```bash
RUN_OBJECT_STORAGE_SMOKE_TEST=true ./scripts/predeploy_check.sh
```
또는
```bash
./scripts/check_object_storage.sh
```

## Clean CI/CD Flow (sausalito_be only)
1. Local verify
```bash
./scripts/predeploy_check.sh
docker compose config >/tmp/sausalito.compose.yaml
```
2. Push to main (GitHub Actions: test -> build/push -> deploy)
```bash
git add .
git commit -m "deploy: update backend"
git push origin main
```
3. VM post-check
```bash
cd /opt/sausalito_be
docker compose ps
curl -I https://sansakorea.com/healthz
```
- GitHub Secrets 최소 목록: `docs/GITHUB_ACTIONS_SECRETS.md`
- 배포 키 자동 동기화(권장): `DEPLOY_SSH_AUTO_SYNC=true` + GCP 관련 시크릿 구성 (상세는 문서 참고)

## Docker Cleanup (safe)
```bash
PRUNE_UNTIL=168h ./scripts/maintenance/prune_docker.sh
```
- `docker volume prune`는 DB 데이터 손실 위험이 있으므로 자동 실행하지 않습니다.
- 운영 기준 문서: `docs/DOCKER_OPERATION.md`

## Runtime Automation (recommended on VM)
```bash
cd /opt/sausalito_be
sudo ./scripts/systemd/install_runtime_automation.sh
```
- certbot 자동 갱신, 디스크 가드, 런타임 헬스 가드, 백업 가드 타이머를 한 번에 설치합니다.

## Environment Files
- 로컬 개발: `.env.local.example` -> `.env` 복사 후 값 수정
- 운영 배포: `.env.prod.example` -> `.env.prod` 복사 후 값 수정
- GCS S3 호환 사용 시 `AWS_S3_REGION_NAME=auto` 권장
- GCS S3 호환 서명 안정화를 위해 `AWS_REQUEST_CHECKSUM_CALCULATION=when_required`, `AWS_RESPONSE_CHECKSUM_VALIDATION=when_required` 권장
- GCS S3 호환에서 `SignatureDoesNotMatch(Invalid argument)`가 반복되면 이미지를 재빌드하여 `requirements/prod.txt`의 boto3/botocore 고정 버전을 반영하세요.


## Notes
- Admin mutation APIs accept `idempotency_key` in body (or `Idempotency-Key` header for delete flows).
- Full PII response is intentionally limited by role and recorded in audit logs.
