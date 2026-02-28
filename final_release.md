# sausalito_be Final Release Protocol (Single-Repo Standard)

이 문서는 `sausalito_be` 저장소만 기준으로 배포를 수행하는 최종 가이드다.

원칙:
- 모든 CI/CD, Docker 이미지 빌드/배포, 서버 배포 스크립트 실행은 `sausalito_be` 내부에서만 수행한다.
- 상위 폴더(`sausalito_project`)는 로컬 작업 편의용이며 배포/운영 기준점이 아니다.

---

## 0) 기준 파일 위치 (모두 `sausalito_be` 내부)

- Compose: `docker-compose.yml`
- 배포 스크립트: `scripts/deploy_backend.sh`
- HTTPS 스크립트: `scripts/ssl/*.sh`
- 유지보수 스크립트: `scripts/maintenance/*.sh`
- systemd 템플릿: `scripts/systemd/*`
- CI/CD: `.github/workflows/backend.yml`, `.github/workflows/security.yml`
- 환경변수 예시: `.env.prod.example`

---

## 1) 로컬 최종 점검 (배포 전)

로컬에서 `sausalito_be` 루트로 이동 후 실행:

```bash
cd /Users/hoyeon/workspace/sausalito_project/sausalito_be

# 민감정보 점검
./scripts/check_sensitive.sh

# 운영 env 점검
./scripts/validate_env_prod.sh --file .env.prod

# 테스트
./venv/bin/python manage.py test --verbosity 2 --settings=config.settings.local

# compose 정합성 확인
docker compose config > /tmp/docker-compose.validated.yaml

# 원샷 사전 점검
./scripts/predeploy_check.sh
```

---

## 2) GCP 콘솔 생성 순서 (클릭 경로)

### 2-1. 프로젝트/결제
1. GCP Console 접속
2. 프로젝트 선택기 -> `NEW PROJECT`
3. 프로젝트 생성
4. `Billing` 연결

### 2-2. API 활성화
1. `APIs & Services` -> `Enabled APIs & services`
2. `+ ENABLE APIS AND SERVICES`
3. `Compute Engine API` 활성화

### 2-3. VM 생성 (무료 범위 우선)
1. `Compute Engine` -> `VM instances` -> `CREATE INSTANCE`
2. 권장 입력
   - Machine type: `e2-micro`
   - Region: Always Free 대상 (`us-west1`, `us-central1`, `us-east1`)
   - Boot disk: Ubuntu 22.04 LTS, Standard PD
3. `Allow HTTP traffic`, `Allow HTTPS traffic` 체크
4. `CREATE`

주의(2026-02-24 기준):
- Compute Engine Always Free는 리전/자원 제한이 있다.
- Cloud SQL/Memorystore는 Always Free 대상이 아니다.
- 과금 방지를 위해 이 설계는 VM 내 Docker Postgres/Redis를 사용한다.

공식 문서:
- https://cloud.google.com/free/docs/free-cloud-features
- https://cloud.google.com/sql/pricing
- https://cloud.google.com/appengine/docs/standard/services/memorystore

---

## 3) DNS 연결

도메인 구매처 DNS에서:
1. `A` 레코드 생성
2. Host: `@` 와 `www` 둘 다 생성
3. Value: GCP VM External IP

검증:

```bash
nslookup sansakorea.com
```

---

## 4) 서버 초기 세팅 (SSH 접속 후)

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg lsb-release git

curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
newgrp docker

docker --version
docker compose version
```

배포 디렉토리 생성/클론:

```bash
sudo mkdir -p /opt/sausalito_be
sudo chown -R $USER:$USER /opt/sausalito_be
cd /opt/sausalito_be

git clone https://github.com/NERO-SERVICE/Sausalito_BE.git .
```

---

## 5) 프로덕션 환경변수 작성

```bash
cd /opt/sausalito_be
cp .env.prod.example .env.prod
nano .env.prod
```

필수 항목:
- Django
  - `DJANGO_SECRET_KEY`
  - `DJANGO_ALLOWED_HOSTS=sansakorea.com,www.sansakorea.com`
  - `PUBLIC_BACKEND_ORIGIN=https://sansakorea.com`
- DB
  - `DB_HOST=db`, `DB_PORT=5432`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`
  - `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`
- Redis
  - `USE_REDIS_CACHE=true`
  - `REDIS_CACHE_URL=redis://redis:6379/1`
  - `REDIS_SESSION_URL=redis://redis:6379/2`
- CORS/CSRF
  - `CORS_ALLOWED_ORIGINS=https://sausalito.co.kr,https://www.sausalito.co.kr`
  - `CSRF_TRUSTED_ORIGINS=https://sausalito.co.kr,https://www.sausalito.co.kr,https://sansakorea.com,https://www.sansakorea.com`
- Object Storage(Media)
  - `USE_S3_MEDIA=true`
  - `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_STORAGE_BUCKET_NAME`
  - `AWS_S3_ENDPOINT_URL`, `AWS_QUERYSTRING_AUTH` 등
- HTTPS
  - `LETSENCRYPT_EMAIL`
  - `LETSENCRYPT_DOMAINS=sansakorea.com,www.sansakorea.com`

---

## 6) 최초 기동

```bash
cd /opt/sausalito_be

docker compose pull
docker compose up -d db redis
docker compose run --rm --no-deps app_blue python manage.py migrate --noinput
docker compose run --rm --no-deps app_blue python manage.py collectstatic --noinput
docker compose up -d nginx app_blue app_green
```

검증:

```bash
docker compose ps
curl -f http://127.0.0.1/healthz
docker compose exec -T redis redis-cli ping
docker compose exec -T db sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

---

## 7) HTTPS 적용 (Let's Encrypt)

최초 발급:

```bash
cd /opt/sausalito_be
./scripts/ssl/bootstrap_letsencrypt.sh
```

확인:

```bash
curl -I http://sansakorea.com/healthz
curl -I https://sansakorea.com/healthz
```

수동 갱신:

```bash
./scripts/ssl/renew_letsencrypt.sh
```

인증서 자동갱신 타이머 등록:

```bash
sudo cp scripts/systemd/sausalito-certbot-renew.service /etc/systemd/system/
sudo cp scripts/systemd/sausalito-certbot-renew.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now sausalito-certbot-renew.timer
```

참고:
- `renew_letsencrypt.sh`는 certbot 갱신 후 `nginx -s reload`까지 수행한다.

---

## 8) GitHub Actions CI/CD 연결

### 8-1. GitHub Secrets
Repository -> `Settings` -> `Secrets and variables` -> `Actions`:

- `DEPLOY_HOST`
- `DEPLOY_USER`
- `DEPLOY_SSH_KEY`
- `DEPLOY_PORT` (예: `22`)
- `DEPLOY_PATH` (`/opt/sausalito_be`)
- `GHCR_TOKEN` (read:packages, write:packages)

### 8-2. 파이프라인 동작
- 워크플로 파일:
  - `.github/workflows/backend.yml`
  - `.github/workflows/security.yml`
- `main` push 시: test -> build/push -> deploy

---

## 9) 운영 배포/롤백 명령

배포:

```bash
cd /opt/sausalito_be
export BACKEND_IMAGE=ghcr.io/nero-service/sausalito-be
export IMAGE_TAG=<sha_or_tag>
./scripts/deploy_backend.sh
```

롤백:

```bash
cd /opt/sausalito_be
export BACKEND_IMAGE=ghcr.io/nero-service/sausalito-be
export IMAGE_TAG=<previous_stable_tag>
./scripts/deploy_backend.sh
```

---

## 10) 운영 유지보수 (디스크/로그/백업)

```bash
cd /opt/sausalito_be
./scripts/maintenance/disk_guard.sh
./scripts/maintenance/prune_docker.sh
./scripts/maintenance/backup_postgres_to_object_storage.sh
```

디스크 가드 타이머 등록:

```bash
sudo cp scripts/systemd/sausalito-disk-guard.service /etc/systemd/system/
sudo cp scripts/systemd/sausalito-disk-guard.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now sausalito-disk-guard.timer
```

---

## 11) 최종 체크리스트

- [ ] 모든 명령이 `sausalito_be` 루트에서 실행됨
- [ ] `.env.prod` 작성 및 민감정보 Git 미추적 확인
- [ ] Postgres/Redis 외부 포트 미노출 확인
- [ ] `https://sansakorea.com/healthz` 정상 확인
- [ ] Object Storage 기반 media(`USE_S3_MEDIA=true`) 확인
- [ ] CI/CD secrets의 `DEPLOY_PATH=/opt/sausalito_be` 확인
- [ ] certbot 갱신 + nginx reload 자동화 확인

---

## 12) 실제 이미지 빌드/푸시 (NERO-SERVICE + pump9918)

```bash
cd /Users/hoyeon/workspace/sausalito_project/sausalito_be
export BACKEND_IMAGE=ghcr.io/nero-service/sausalito-be
export IMAGE_TAG=dev-$(date +%Y%m%d%H%M)

docker build -t ${BACKEND_IMAGE}:${IMAGE_TAG} .
docker tag ${BACKEND_IMAGE}:${IMAGE_TAG} ${BACKEND_IMAGE}:latest

# 수기 로그인 (PAT 입력)
docker login ghcr.io -u pump9918

docker push ${BACKEND_IMAGE}:${IMAGE_TAG}
docker push ${BACKEND_IMAGE}:latest
```

주의:
- `docker login` 비밀번호 칸에는 GitHub 비밀번호가 아니라 PAT를 입력해야 한다.
- 수동 배포 시 `IMAGE_TAG`를 위 태그로 지정해서 `./scripts/deploy_backend.sh`를 실행한다.
