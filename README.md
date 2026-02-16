## Tech Stack
- Django 5.x
- Django REST Framework
- JWT (`djangorestframework-simplejwt`)
- drf-spectacular (OpenAPI)
- django-cors-headers
- Pillow
- Local media storage (`MEDIA_ROOT`) for product/banner/review images

## Project Structure
```text
sausalito_be/
  manage.py
  config/
    api_v1_urls.py
    settings/
      base.py
      local.py
      prod.py
  apps/
    common/
    accounts/
    catalog/
    reviews/
    cart/
    orders/
    payments/
  requirements/
    base.txt
    local.txt
    prod.txt
  .env.local
  .env.prod
```

## Quick Start
1. 가상환경 생성
```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. 의존성 설치
```bash
pip install -r requirements/local.txt
```

3. 환경변수 설정
```bash
cp .env.local .env
```

4. 마이그레이션
```bash
python manage.py makemigrations
python manage.py migrate
```

5. 데모 데이터 시드
```bash
python manage.py seed_demo_data --reset
```

6. 서버 실행
```bash
python manage.py runserver
```

## Demo Account
- email: `demo@sausalito.com`
- password: `demo1234`

## API Docs
- Swagger UI: `http://127.0.0.1:8000/api/docs/`
- OpenAPI JSON: `http://127.0.0.1:8000/api/schema/`

## API Prefix
- `/api/v1`

## Implemented Endpoints
### Auth / Accounts
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/kakao/callback`
- `POST /api/v1/auth/refresh`
- `POST /api/v1/auth/logout`
- `GET /api/v1/users/me`
- `PATCH /api/v1/users/me`

### Catalog
- `GET /api/v1/banners/home`
- `GET /api/v1/products`
  - query: `q`, `sort`, `min_price`, `max_price`, `page`, `page_size`
- `GET /api/v1/products/{id}`
- `GET /api/v1/products/{id}/detail-meta`

### Reviews
- `GET /api/v1/reviews`
  - query: `product_id`, `sort(latest|helpful|score)`, `has_image`, `page`, `page_size`
- `POST /api/v1/reviews` (multipart, images 최대 3장)
- `GET /api/v1/products/{id}/reviews/summary`

### Cart
- `GET /api/v1/cart`
- `POST /api/v1/cart/items`
- `PATCH /api/v1/cart/items/{item_id}`
- `DELETE /api/v1/cart/items/{item_id}`

### Orders
- `GET /api/v1/orders`
- `POST /api/v1/orders`
- `GET /api/v1/orders/{order_no}`

### Payments (NaverPay)
- `POST /api/v1/payments/naverpay/ready`
- `POST /api/v1/payments/naverpay/approve`
- `POST /api/v1/payments/naverpay/webhook`
- `POST /api/v1/payments/naverpay/cancel`

## Response Shape
### Success
```json
{
  "success": true,
  "data": {},
  "message": ""
}
```

### Error
```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "입력값을 확인해주세요.",
    "details": {}
  }
}
```

## Notes
- 카카오/네이버페이 연동은 실제 운영키/시그니처 정책으로 교체해야 합니다.
- 결제 `ready/approve/webhook/cancel`은 현재 확장 가능한 기본 구현 + mock URL 기반입니다.
- 프론트(`sausalito_fe`)는 기존 더미 서비스 레이어를 API 호출로 교체하면 연동 가능합니다.
- 이미지 저장 정책:
  - 상품/배너/상세/리뷰 이미지는 모두 백엔드 `MEDIA_ROOT`에 저장됩니다.
  - 관리자 페이지에서 직접 업로드 가능하며, 리뷰 이미지는 최대 3장까지 허용됩니다.
  - 업로드 파일명은 UUID 기반으로 저장되어 원본 파일명을 그대로 노출하지 않습니다.
