# GitHub Actions Required Secrets (Backend Deploy)

배포 워크플로우(`.github/workflows/backend.yml`) 기준 필수 시크릿만 정리했습니다.

## Required
- `GHCR_TOKEN`
  - GHCR push/pull 공용 GitHub PAT
  - 최소 권한: `read:packages`, `write:packages`
- `DEPLOY_HOST`
  - 예: `sansakorea.com` 또는 VM 고정 외부 IP
- `DEPLOY_USER`
  - VM SSH 사용자 (예: `official`)
- `DEPLOY_SSH_KEY`
  - `DEPLOY_USER`로 접속 가능한 개인키 전체(멀티라인)
- `DEPLOY_PORT`
  - 보통 `22`
- `DEPLOY_PATH`
  - 예: `/opt/sausalito_be`

## Optional
- `DEPLOY_SSH_PASSPHRASE`
  - `DEPLOY_SSH_KEY`가 암호화되어 있을 때만 사용

## Optional (Recommended: SSH key auto-sync to VM)
- `DEPLOY_SSH_AUTO_SYNC`
  - 값: `true`
  - 켜면 GitHub Actions가 GCP API로 VM metadata `ssh-keys`를 자동 갱신
- `DEPLOY_SSH_PUBLIC_KEY`
  - `DEPLOY_SSH_KEY`에 대응되는 공개키 한 줄
  - 예: `ssh-ed25519 AAAA... deploy@sansakorea.com`
- `GCP_PROJECT_ID`
  - 예: `sausalito-be`
- `GCP_ZONE`
  - 예: `asia-northeast3-c`
- `GCP_INSTANCE_NAME`
  - 예: `instance-sausalito-be`
- `GCP_SERVICE_ACCOUNT_JSON`
  - GCP 서비스 계정 JSON 키 전체
  - 권장 권한: `Compute Instance Admin (v1)` (최소 set/get metadata 권한 포함 커스텀 역할 가능)

주의:
- OS Login(`enable-oslogin=true`)이 켜져 있으면 instance metadata `ssh-keys` 방식이 무시됩니다.
- 자동 동기화 방식을 쓰려면 OS Login을 끄거나, 별도 OS Login 배포 방식으로 전환해야 합니다.
