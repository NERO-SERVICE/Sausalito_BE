# GitHub Actions Required Secrets (Backend Deploy)

배포 워크플로우(`.github/workflows/backend.yml`) 기준 필수 시크릿만 정리했습니다.

## Required
- `GHCR_PUSH_TOKEN`
  - 이미지 push 용 GitHub PAT
  - 최소 권한: `write:packages`
- `GHCR_READ_TOKEN`
  - VM에서 이미지 pull 용 GitHub PAT
  - 최소 권한: `read:packages`
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
