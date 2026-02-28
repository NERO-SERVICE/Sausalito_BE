# Docker 운영 기준 (sausalito_be)

## 1) 이미지를 언제 다시 만들어야 하나
- 운영 기준: 코드를 `main`에 push하면 GitHub Actions가 자동으로 이미지를 빌드/푸시/배포합니다.
- 따라서 운영 반영을 위해 로컬에서 매번 `docker build`를 수동 실행할 필요는 없습니다.
- 예외적으로 아래 경우는 수동 빌드가 유용합니다.
  - 로컬에서 배포 전 동작을 미리 검증하고 싶을 때
  - GitHub Actions를 쓰지 않는 임시 수동 배포를 할 때

## 2) 이미지/컨테이너/볼륨 저장 위치
- GHCR 원격 레지스트리:
  - `ghcr.io/nero-service/sausalito-be:<tag>`
  - 태그: `latest`, `${GITHUB_SHA}`
- VM 로컬 Docker 데이터 루트:
  - 일반적으로 `/var/lib/docker`
  - 이미지 레이어: `/var/lib/docker/overlay2`
  - 볼륨: `/var/lib/docker/volumes`

## 3) 현재 저장 구조
- 컨테이너(실행 단위):
  - `app_blue`, `app_green`, `nginx`, `db`, `redis`
- 영속 볼륨(데이터 유지):
  - `sausalito_postgres_data` : PostgreSQL 데이터
  - `sausalito_django_static` : collectstatic 결과
  - `sausalito_certbot_etc` : 인증서
  - `sausalito_certbot_webroot` : ACME webroot
- 미디어 파일:
  - 서버 디스크가 아니라 Object Storage(GCS S3 호환) 버킷에 저장

## 4) 운영 정리 원칙
- 정기 정리:
  - `PRUNE_UNTIL=168h ./scripts/maintenance/prune_docker.sh`
- 주의:
  - `docker volume prune`는 DB/인증서 데이터 손실 위험이 있으므로 자동 실행 금지
- 권장 자동화:
  - `sudo ./scripts/systemd/install_runtime_automation.sh`
  - certbot 갱신, 디스크 가드, 런타임 헬스 가드, 백업 가드 타이머를 동시에 활성화
  - `BACKUP_S3_URI` 미설정 시 백업 가드는 자동으로 skip 처리

## 5) 점검 명령
```bash
docker compose ps
docker image ls ghcr.io/nero-service/sausalito-be
docker volume ls | grep sausalito
docker system df
```
