from __future__ import annotations

import uuid
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth import login as django_login
from django.db import transaction
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from apps.common.response import error_response, success_response
from apps.catalog.models import Product
from apps.catalog.serializers import ProductListSerializer
from apps.orders.models import Order
from apps.orders.serializers import OrderSerializer
from apps.reviews.models import Review
from apps.reviews.serializers import ReviewListSerializer

from .admin_security import get_admin_role, log_audit_event
from .models import (
    DepositTransaction,
    OneToOneInquiry,
    PointTransaction,
    RecentViewedProduct,
    UserCoupon,
    WishlistItem,
)
from .serializers import (
    DepositTransactionSerializer,
    KakaoAuthorizeUrlSerializer,
    KakaoCallbackSerializer,
    LoginSerializer,
    LogoutSerializer,
    OneToOneInquiryReadSerializer,
    OneToOneInquirySerializer,
    PasswordChangeSerializer,
    PointTransactionSerializer,
    RecentViewedCreateSerializer,
    RegisterSerializer,
    TokenRefreshRequestSerializer,
    UserWithdrawSerializer,
    UserCouponSerializer,
    UserMeSerializer,
    WishlistCreateSerializer,
)
from .services import KakaoOAuthClient


def issue_tokens_for_user(user) -> dict:
    refresh = RefreshToken.for_user(user)
    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
    }


class LoginAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        django_login(request, user)
        if user.is_staff:
            log_audit_event(
                request,
                action="ADMIN_LOGIN",
                target_type="AdminUser",
                target_id=str(user.id),
                metadata={"admin_role": get_admin_role(user)},
            )
        return success_response(
            {
                "user": UserMeSerializer(user).data,
                "tokens": issue_tokens_for_user(user),
            },
            message="로그인되었습니다.",
        )


class RegisterAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            user = serializer.save()
            django_login(request, user)

        return success_response(
            {
                "user": UserMeSerializer(user).data,
                "tokens": issue_tokens_for_user(user),
            },
            message="회원가입이 완료되었습니다.",
            status_code=status.HTTP_201_CREATED,
        )


class KakaoAuthorizeUrlAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        serializer = KakaoAuthorizeUrlSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)

        if not settings.KAKAO_REST_API_KEY:
            return error_response(
                code="KAKAO_CONFIG_MISSING",
                message="카카오 OAuth 설정이 비어 있습니다.",
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        redirect_uri = serializer.validated_data.get("redirect_uri") or settings.KAKAO_REDIRECT_URI
        if not redirect_uri:
            return error_response(
                code="KAKAO_REDIRECT_URI_REQUIRED",
                message="카카오 redirect_uri 설정이 필요합니다.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        allowed_redirect_uris = settings.KAKAO_ALLOWED_REDIRECT_URIS
        if allowed_redirect_uris and redirect_uri not in allowed_redirect_uris:
            return error_response(
                code="INVALID_REDIRECT_URI",
                message="허용되지 않은 redirect_uri 입니다.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        scopes = ["profile_nickname"]
        if settings.KAKAO_INCLUDE_EMAIL_SCOPE:
            scopes.append("account_email")

        query = {
            "response_type": "code",
            "client_id": settings.KAKAO_REST_API_KEY,
            "redirect_uri": redirect_uri,
            "scope": ",".join(scopes),
        }
        state_value = serializer.validated_data.get("state")
        if state_value:
            query["state"] = state_value

        authorize_url = f"https://kauth.kakao.com/oauth/authorize?{urlencode(query)}"
        return success_response(
            {
                "authorize_url": authorize_url,
                "redirect_uri": redirect_uri,
            }
        )


class KakaoCallbackAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = KakaoCallbackSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        redirect_uri = serializer.validated_data.get("redirect_uri")

        allowed_redirect_uris = settings.KAKAO_ALLOWED_REDIRECT_URIS
        if allowed_redirect_uris and redirect_uri and redirect_uri not in allowed_redirect_uris:
            return error_response(
                code="INVALID_REDIRECT_URI",
                message="허용되지 않은 redirect_uri 입니다.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        user = KakaoOAuthClient().get_or_create_user(
            code=serializer.validated_data["code"],
            redirect_uri=redirect_uri,
        )

        return success_response(
            {
                "user": UserMeSerializer(user).data,
                "tokens": issue_tokens_for_user(user),
            },
            message="카카오 로그인이 완료되었습니다.",
        )


class RefreshAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        request_serializer = TokenRefreshRequestSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        serializer = TokenRefreshSerializer(data=request_serializer.validated_data)
        serializer.is_valid(raise_exception=True)
        return success_response(serializer.validated_data, message="토큰이 갱신되었습니다.")


class LogoutAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        refresh_token = serializer.validated_data["refresh"]
        try:
            RefreshToken(refresh_token).blacklist()
        except TokenError as exc:
            raise AuthenticationFailed("유효하지 않은 리프레시 토큰입니다.") from exc

        if request.user.is_staff:
            log_audit_event(
                request,
                action="ADMIN_LOGOUT",
                target_type="AdminUser",
                target_id=str(request.user.id),
                metadata={"admin_role": get_admin_role(request.user)},
            )
        return success_response(message="로그아웃되었습니다.")


class MeAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        serializer = UserMeSerializer(request.user)
        return success_response(serializer.data)

    def patch(self, request, *args, **kwargs):
        serializer = UserMeSerializer(instance=request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return success_response(serializer.data, message="회원 정보가 업데이트되었습니다.")


class UserWithdrawAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = UserWithdrawSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = request.user

        if user.is_staff:
            return error_response(
                code="STAFF_WITHDRAW_NOT_ALLOWED",
                message="관리자 계정은 해당 화면에서 탈퇴할 수 없습니다.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            now = timezone.now().strftime("%Y%m%d%H%M%S")
            suffix = uuid.uuid4().hex[:10]
            anonymized_email = f"withdrawn_{user.id}_{now}_{suffix}@withdrawn.local"
            user.set_unusable_password()
            user.is_active = False
            user.email = anonymized_email
            user.username = anonymized_email
            user.name = ""
            user.phone = ""
            user.kakao_sub = None
            user.save(
                update_fields=[
                    "password",
                    "is_active",
                    "email",
                    "username",
                    "name",
                    "phone",
                    "kakao_sub",
                    "updated_at",
                ]
            )

        return success_response(message="회원 탈퇴가 처리되었습니다.")


def _serialize_product_rows_with_timestamp(rows, request, timestamp_key: str):
    serialized = []
    for row in rows:
        product = row.product
        if not product or not product.is_active:
            continue
        product_data = ProductListSerializer(product, context={"request": request}).data
        product_data[timestamp_key] = row.viewed_at if hasattr(row, "viewed_at") else row.created_at
        serialized.append(product_data)
    return serialized


class MyPageDashboardAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = request.user

        total_order_count = Order.objects.filter(user=user).count()
        orders = (
            Order.objects.filter(user=user)
            .prefetch_related("items")
            .order_by("-created_at")[:20]
        )
        point_rows = PointTransaction.objects.filter(user=user).order_by("-created_at", "-id")[:20]
        deposit_rows = DepositTransaction.objects.filter(user=user).order_by("-created_at", "-id")[:20]
        coupon_rows = UserCoupon.objects.filter(user=user).order_by("-created_at", "-id")

        wishlist_rows = (
            WishlistItem.objects.filter(user=user, product__is_active=True)
            .select_related("product")
            .prefetch_related("product__images", "product__badges")
            .order_by("-created_at", "-id")[:20]
        )
        recent_rows = (
            RecentViewedProduct.objects.filter(user=user, product__is_active=True)
            .select_related("product")
            .prefetch_related("product__images", "product__badges")
            .order_by("-viewed_at", "-id")[:20]
        )
        my_reviews = (
            Review.objects.filter(user=user, status=Review.Status.VISIBLE)
            .select_related("product")
            .prefetch_related("images")
            .order_by("-created_at", "-id")[:20]
        )
        inquiries = OneToOneInquiry.objects.filter(user=user).order_by("-created_at", "-id")[:20]

        point_balance = (
            PointTransaction.objects.filter(user=user).aggregate(total=Coalesce(Sum("amount"), 0)).get("total")
            or 0
        )
        deposit_balance = (
            DepositTransaction.objects.filter(user=user).aggregate(total=Coalesce(Sum("amount"), 0)).get("total")
            or 0
        )

        data = {
            "shopping": {
                "summary": {
                    "order_count": total_order_count,
                    "point_balance": int(point_balance),
                    "deposit_balance": int(deposit_balance),
                    "coupon_count": coupon_rows.filter(is_used=False).count(),
                },
                "orders": OrderSerializer(orders, many=True).data,
                "point_history": PointTransactionSerializer(point_rows, many=True).data,
                "deposit_history": DepositTransactionSerializer(deposit_rows, many=True).data,
                "coupon_history": UserCouponSerializer(coupon_rows, many=True).data,
            },
            "activity": {
                "recent_products": _serialize_product_rows_with_timestamp(
                    recent_rows, request, timestamp_key="viewed_at"
                ),
                "wishlist_products": _serialize_product_rows_with_timestamp(
                    wishlist_rows, request, timestamp_key="wished_at"
                ),
                "my_reviews": ReviewListSerializer(my_reviews, many=True, context={"request": request}).data,
            },
            "profile": UserMeSerializer(user).data,
            "inquiries": OneToOneInquiryReadSerializer(inquiries, many=True).data,
        }
        return success_response(data)


class WishlistAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        rows = (
            WishlistItem.objects.filter(user=request.user, product__is_active=True)
            .select_related("product")
            .prefetch_related("product__images", "product__badges")
            .order_by("-created_at", "-id")
        )
        data = _serialize_product_rows_with_timestamp(rows, request, timestamp_key="wished_at")
        return success_response(data)

    def post(self, request, *args, **kwargs):
        serializer = WishlistCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = get_object_or_404(Product, id=serializer.validated_data["product_id"], is_active=True)

        row, created = WishlistItem.objects.get_or_create(user=request.user, product=product)
        item_data = ProductListSerializer(product, context={"request": request}).data
        item_data["wished_at"] = row.created_at

        return success_response(
            item_data,
            message="위시리스트에 추가되었습니다." if created else "이미 위시리스트에 등록된 상품입니다.",
            status_code=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class WishlistDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, product_id: int, *args, **kwargs):
        deleted_count, _ = WishlistItem.objects.filter(user=request.user, product_id=product_id).delete()
        if not deleted_count:
            return error_response(
                code="NOT_FOUND",
                message="위시리스트에 없는 상품입니다.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        return success_response(message="위시리스트에서 제거되었습니다.")


class RecentViewedProductAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        rows = (
            RecentViewedProduct.objects.filter(user=request.user, product__is_active=True)
            .select_related("product")
            .prefetch_related("product__images", "product__badges")
            .order_by("-viewed_at", "-id")
        )
        data = _serialize_product_rows_with_timestamp(rows, request, timestamp_key="viewed_at")
        return success_response(data)

    def post(self, request, *args, **kwargs):
        serializer = RecentViewedCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = get_object_or_404(Product, id=serializer.validated_data["product_id"], is_active=True)

        RecentViewedProduct.objects.update_or_create(
            user=request.user,
            product=product,
            defaults={"viewed_at": timezone.now()},
        )
        return success_response(message="최근 본 상품에 반영되었습니다.", status_code=status.HTTP_201_CREATED)


class InquiryListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        queryset = OneToOneInquiry.objects.filter(user=request.user).order_by("-created_at", "-id")
        return success_response(OneToOneInquiryReadSerializer(queryset, many=True).data)

    def post(self, request, *args, **kwargs):
        serializer = OneToOneInquirySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        inquiry = serializer.save(user=request.user)
        return success_response(
            OneToOneInquiryReadSerializer(inquiry).data,
            message="1:1 문의가 접수되었습니다.",
            status_code=status.HTTP_201_CREATED,
        )


class PasswordChangeAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = PasswordChangeSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return success_response(message="비밀번호가 변경되었습니다.")


class HealthCheckAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        return Response({"ok": True})
