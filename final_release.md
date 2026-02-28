# sausalito_be Final Release Guide

이 문서는 `sausalito_be` 저장소 기준 최종 배포/운영 문서다.
모든 Docker/CI-CD/운영 명령은 `sausalito_be` 루트 기준이다.

## 0) e2-medium 무개입 운영 가능성 검토 결과

판정: **조건부 YES**
- 현재 구조는 특별 이슈가 없으면 장기간 자동 운영 가능하도록 설계되어 있다.
- 단, 완전 무개입(never touch)은 불가능하다. 클라우드/도메인/보안/비용/용량은 주기적 확인이 필요하다.

자동화로 커버되는 범위:
- 코드 배포: GitHub Actions 자동 빌드/배포
- 컨테이너 재기동: `restart: unless-stopped`
- HTTPS 갱신 + Nginx reload: certbot timer
- 디스크 압박 시 prune: disk guard timer
- 런타임 장애 자동 복구 시도: runtime guard timer
- DB 백업(설정 시): backup timer + backup guard

수동 확인이 필요한 범위(경고):
- GCP 과금/쿼터/정책 변경
- 도메인 갱신/네임서버 상태
- Secret/PAT 만료 및 회전
- 백업 복구 리허설(백업 성공 != 복구 가능)
- 급격한 트래픽 증가 시 인프라 스케일링

---

## 1) 아키텍처 요약
- App: Django + Gunicorn
- Proxy: Nginx
- DB: Postgres (컨테이너)
- Cache/Session: Redis (컨테이너)
- Media: Object Storage(GCS S3 호환)
- Deploy: GitHub Actions -> GHCR -> VM SSH 배포
- 무중단 배포: `app_blue`, `app_green` 동시 운영

핵심 원칙:
- 사용자 미디어는 VM 디스크에 저장하지 않음
- 로그는 파일 적재 대신 stdout/stderr
- Docker 로그 로테이션/주기적 정리 적용

---

## 2) 컨테이너 역할

### `db`
- PostgreSQL 운영 DB
- 영속 볼륨: `postgres_data`
- 외부 포트 미노출

### `redis`
- 캐시/세션 저장소
- 메모리 정책 기반 운영
- 외부 포트 미노출

### `app_blue`, `app_green`
- Django 앱 풀 2개
- 롤링 교체를 위한 무중단 배포 단위

### `nginx`
- 80/443 종단
- health 체크 라우팅
- 80 -> 443 리다이렉트

### `certbot`
- 인증서 발급/갱신 전용(필요 시 실행)

---

## 3) Docker 저장 구조

원격 레지스트리:
- `ghcr.io/nero-service/sausalito-be:{latest|sha}`

VM 로컬:
- Docker root: `/var/lib/docker`
- 레이어: `/var/lib/docker/overlay2`
- 볼륨: `/var/lib/docker/volumes`

Compose 영속 볼륨:
- `postgres_data`
- `django_static`
- `certbot_etc`
- `certbot_webroot`

미디어:
- `USE_S3_MEDIA=true` 운영 시 Object Storage 저장
- 미디어 원본은 VM 디스크에 누적되지 않음

---

## 4) 파일/폴더 구조 핵심

### 인프라/배포
- `docker-compose.yml`: 운영 오케스트레이션
- `Dockerfile`: 앱 이미지 빌드
- `.github/workflows/backend.yml`: CI/CD
- `.github/workflows/security.yml`: 시크릿 패턴 스캔

### 설정
- `config/settings/base.py`: 공통
- `config/settings/prod.py`: 운영 보안 강제
- `.env.prod.example`: 운영 env 템플릿

### Nginx/SSL
- `nginx/conf.d/00-http.conf`
- `nginx/conf.d/10-https.conf.template`
- `scripts/ssl/bootstrap_letsencrypt.sh`
- `scripts/ssl/renew_letsencrypt.sh`
- `scripts/ssl/enable_https_conf.sh`

### 운영 스크립트
- `scripts/deploy_backend.sh`
- `scripts/predeploy_check.sh`
- `scripts/check_object_storage.sh`
- `scripts/validate_env_prod.sh`

### 유지보수
- `scripts/maintenance/prune_docker.sh`
- `scripts/maintenance/disk_guard.sh`
- `scripts/maintenance/runtime_guard.sh`
- `scripts/maintenance/backup_guard.sh`
- `scripts/maintenance/backup_postgres_to_object_storage.sh`

### systemd 자동화
- `scripts/systemd/install_runtime_automation.sh`
- `scripts/systemd/sausalito-certbot-renew.*`
- `scripts/systemd/sausalito-disk-guard.*`
- `scripts/systemd/sausalito-runtime-guard.*`
- `scripts/systemd/sausalito-backup.*`

---

## 5) CI/CD 표준 흐름

`main` push 시:
1. test
- 시크릿 패턴 검사
- Django 테스트
- compose/env/script 정합성 검사

2. build-and-push
- GHCR 로그인(`GHCR_TOKEN`)
- 이미지 빌드 후 `${GITHUB_SHA}`, `latest` 푸시

3. deploy
- VM SSH 접속
- `git pull --ff-only`
- GHCR 로그인
- `./scripts/deploy_backend.sh`

필수 GitHub Secrets:
- `GHCR_TOKEN` (read:packages, write:packages)
- `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`, `DEPLOY_PORT`, `DEPLOY_PATH`

권장 GitHub Secrets(키 교체 시 VM 수동작업 최소화):
- `DEPLOY_SSH_AUTO_SYNC=true`
- `DEPLOY_SSH_PUBLIC_KEY`
- `GCP_PROJECT_ID`
- `GCP_ZONE`
- `GCP_INSTANCE_NAME`
- `GCP_SERVICE_ACCOUNT_JSON`

주의:
- 위 자동 동기화는 GCP instance metadata `ssh-keys` 방식이다.
- OS Login(`enable-oslogin=true`)이 켜져 있으면 metadata 키가 무시되므로 동작하지 않는다.

---

## 6) 배포 표준 명령

로컬 사전 점검:
```bash
cd /Users/hoyeon/workspace/sausalito_project/sausalito_be
./scripts/predeploy_check.sh
```

배포 트리거:
```bash
git add .
git commit -m "deploy: update backend"
git push origin main
```

VM 수동 배포(필요 시):
```bash
cd /opt/sausalito_be
docker login ghcr.io -u pump9918
export BACKEND_IMAGE=ghcr.io/nero-service/sausalito-be
export IMAGE_TAG=latest
./scripts/deploy_backend.sh
```

상태 확인:
```bash
docker compose ps
curl -I https://sansakorea.com/healthz
./scripts/check_object_storage.sh
```

---

## 7) 자동화 설치 (권장)

VM에서 1회 실행:
```bash
cd /opt/sausalito_be
sudo ./scripts/systemd/install_runtime_automation.sh
```

활성화되는 타이머:
- `sausalito-certbot-renew.timer` (인증서 자동 갱신)
- `sausalito-disk-guard.timer` (디스크 임계치 기반 정리)
- `sausalito-runtime-guard.timer` (헬스체크 + 자동 복구 시도)
- `sausalito-backup.timer` (백업 가드; 설정 없으면 스킵)

상태 확인:
```bash
systemctl list-timers --all | grep sausalito-
```

---

## 8) 경고사항 (반드시 수동 관리 필요)

1. **백업 복구 검증**
- 자동 백업만으로는 불충분
- 월 1회 이상 복구 리허설 필요

2. **보안 키 회전**
- `GHCR_TOKEN`, S3/GCS 키, OAuth 키 유출/만료 대비 회전 필요

3. **OS 보안 업데이트**
- 컨테이너 외 호스트 취약점은 별도 패치 필요

4. **도메인/DNS/인증서 체인 이슈**
- DNS 오변경, 도메인 만료, CA 정책 변화는 자동으로 해결되지 않음

5. **트래픽 급증 한계**
- e2-medium 단일 VM은 급격한 증가에 한계
- DB/Redis가 동일 인스턴스에 있어 병목 가능

6. **비용/쿼터**
- GCP 과금/쿼터/정책은 수동 모니터링 필요

---

## 9) e2-medium 운영 한계와 확장 기준

현재 구조로 적합:
- 초기~중간 트래픽
- 운영 복잡도를 낮추고 빠르게 서비스할 때

확장 신호:
- API p95 지연 상승
- DB CPU/IO 포화
- 배포/마이그레이션 시간 증가
- 장애 복구 시간 증가

다음 단계:
- VM 스펙 상향 + 디스크 IOPS 증설
- Cloud SQL/Memorystore 분리
- 인스턴스 다중화 + Load Balancer
- 모니터링/알람 고도화

---

## 10) 최종 체크리스트
- [ ] `./scripts/predeploy_check.sh` 통과
- [ ] Actions `test/build-and-push/deploy` 성공
- [ ] `https://sansakorea.com/healthz` 200
- [ ] `./scripts/check_object_storage.sh` 성공
- [ ] 자동화 타이머 4종 활성화 확인
- [ ] 백업 복구 리허설 일정 수립
- [ ] 롤백용 안정 SHA 기록

