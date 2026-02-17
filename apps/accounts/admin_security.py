from __future__ import annotations

import hashlib
import json
from typing import Any

from django.db import IntegrityError
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import BasePermission
from rest_framework.response import Response

from .models import AuditLog, IdempotencyRecord, User


class AdminPermission:
    DASHBOARD_VIEW = "DASHBOARD_VIEW"
    ORDER_VIEW = "ORDER_VIEW"
    ORDER_UPDATE = "ORDER_UPDATE"
    RETURN_VIEW = "RETURN_VIEW"
    RETURN_UPDATE = "RETURN_UPDATE"
    REFUND_EXECUTE = "REFUND_EXECUTE"
    SETTLEMENT_VIEW = "SETTLEMENT_VIEW"
    SETTLEMENT_UPDATE = "SETTLEMENT_UPDATE"
    INQUIRY_VIEW = "INQUIRY_VIEW"
    INQUIRY_UPDATE = "INQUIRY_UPDATE"
    REVIEW_VIEW = "REVIEW_VIEW"
    REVIEW_UPDATE = "REVIEW_UPDATE"
    PRODUCT_VIEW = "PRODUCT_VIEW"
    PRODUCT_UPDATE = "PRODUCT_UPDATE"
    USER_VIEW = "USER_VIEW"
    USER_UPDATE = "USER_UPDATE"
    COUPON_VIEW = "COUPON_VIEW"
    COUPON_UPDATE = "COUPON_UPDATE"
    BANNER_VIEW = "BANNER_VIEW"
    BANNER_UPDATE = "BANNER_UPDATE"
    STAFF_VIEW = "STAFF_VIEW"
    AUDIT_LOG_VIEW = "AUDIT_LOG_VIEW"
    PII_FULL_VIEW = "PII_FULL_VIEW"
    PII_EXPORT = "PII_EXPORT"


ROLE_PERMISSION_MATRIX: dict[str, set[str]] = {
    User.AdminRole.SUPER_ADMIN: {
        AdminPermission.DASHBOARD_VIEW,
        AdminPermission.ORDER_VIEW,
        AdminPermission.ORDER_UPDATE,
        AdminPermission.RETURN_VIEW,
        AdminPermission.RETURN_UPDATE,
        AdminPermission.REFUND_EXECUTE,
        AdminPermission.SETTLEMENT_VIEW,
        AdminPermission.SETTLEMENT_UPDATE,
        AdminPermission.INQUIRY_VIEW,
        AdminPermission.INQUIRY_UPDATE,
        AdminPermission.REVIEW_VIEW,
        AdminPermission.REVIEW_UPDATE,
        AdminPermission.PRODUCT_VIEW,
        AdminPermission.PRODUCT_UPDATE,
        AdminPermission.USER_VIEW,
        AdminPermission.USER_UPDATE,
        AdminPermission.COUPON_VIEW,
        AdminPermission.COUPON_UPDATE,
        AdminPermission.BANNER_VIEW,
        AdminPermission.BANNER_UPDATE,
        AdminPermission.STAFF_VIEW,
        AdminPermission.AUDIT_LOG_VIEW,
        AdminPermission.PII_FULL_VIEW,
        AdminPermission.PII_EXPORT,
    },
    User.AdminRole.OPS: {
        AdminPermission.DASHBOARD_VIEW,
        AdminPermission.ORDER_VIEW,
        AdminPermission.ORDER_UPDATE,
        AdminPermission.RETURN_VIEW,
        AdminPermission.INQUIRY_VIEW,
        AdminPermission.PRODUCT_VIEW,
        AdminPermission.PRODUCT_UPDATE,
        AdminPermission.STAFF_VIEW,
    },
    User.AdminRole.CS: {
        AdminPermission.DASHBOARD_VIEW,
        AdminPermission.ORDER_VIEW,
        AdminPermission.ORDER_UPDATE,
        AdminPermission.RETURN_VIEW,
        AdminPermission.RETURN_UPDATE,
        AdminPermission.INQUIRY_VIEW,
        AdminPermission.INQUIRY_UPDATE,
        AdminPermission.REVIEW_VIEW,
        AdminPermission.REVIEW_UPDATE,
        AdminPermission.USER_VIEW,
        AdminPermission.STAFF_VIEW,
    },
    User.AdminRole.WAREHOUSE: {
        AdminPermission.DASHBOARD_VIEW,
        AdminPermission.ORDER_VIEW,
        AdminPermission.ORDER_UPDATE,
        AdminPermission.PRODUCT_VIEW,
        AdminPermission.PRODUCT_UPDATE,
    },
    User.AdminRole.FINANCE: {
        AdminPermission.DASHBOARD_VIEW,
        AdminPermission.ORDER_VIEW,
        AdminPermission.RETURN_VIEW,
        AdminPermission.RETURN_UPDATE,
        AdminPermission.REFUND_EXECUTE,
        AdminPermission.SETTLEMENT_VIEW,
        AdminPermission.SETTLEMENT_UPDATE,
        AdminPermission.USER_VIEW,
        AdminPermission.AUDIT_LOG_VIEW,
        AdminPermission.PII_FULL_VIEW,
        AdminPermission.PII_EXPORT,
    },
    User.AdminRole.MARKETING: {
        AdminPermission.DASHBOARD_VIEW,
        AdminPermission.PRODUCT_VIEW,
        AdminPermission.PRODUCT_UPDATE,
        AdminPermission.REVIEW_VIEW,
        AdminPermission.REVIEW_UPDATE,
        AdminPermission.COUPON_VIEW,
        AdminPermission.COUPON_UPDATE,
        AdminPermission.BANNER_VIEW,
        AdminPermission.BANNER_UPDATE,
    },
    User.AdminRole.READ_ONLY: {
        AdminPermission.DASHBOARD_VIEW,
        AdminPermission.ORDER_VIEW,
        AdminPermission.RETURN_VIEW,
        AdminPermission.SETTLEMENT_VIEW,
        AdminPermission.INQUIRY_VIEW,
        AdminPermission.REVIEW_VIEW,
        AdminPermission.PRODUCT_VIEW,
        AdminPermission.USER_VIEW,
        AdminPermission.COUPON_VIEW,
        AdminPermission.BANNER_VIEW,
        AdminPermission.AUDIT_LOG_VIEW,
    },
}


def get_admin_role(user: User | None) -> str:
    if not user:
        return User.AdminRole.READ_ONLY
    if getattr(user, "is_superuser", False):
        return User.AdminRole.SUPER_ADMIN
    return getattr(user, "admin_role", User.AdminRole.READ_ONLY) or User.AdminRole.READ_ONLY


def get_admin_permissions(user: User | None) -> set[str]:
    if not user:
        return set()
    if getattr(user, "is_superuser", False):
        return set(ROLE_PERMISSION_MATRIX[User.AdminRole.SUPER_ADMIN])
    return set(ROLE_PERMISSION_MATRIX.get(get_admin_role(user), set()))


def has_admin_permission(user: User | None, permission: str) -> bool:
    return permission in get_admin_permissions(user)


def has_full_pii_access(user: User | None) -> bool:
    return has_admin_permission(user, AdminPermission.PII_FULL_VIEW)


class AdminRBACPermission(BasePermission):
    message = "관리자 권한이 없습니다."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if not getattr(user, "is_staff", False):
            return False

        required = getattr(view, "required_permissions", None)
        if not required:
            return False

        required_for_method = required.get(request.method)
        if required_for_method is None:
            return False

        if isinstance(required_for_method, str):
            required_permissions = {required_for_method}
        else:
            required_permissions = set(required_for_method)

        user_permissions = get_admin_permissions(user)
        missing = required_permissions - user_permissions
        if missing:
            self.message = "요청한 기능에 필요한 권한이 없습니다."
            return False
        return True


def _mask_middle(value: str, visible_prefix: int = 1, visible_suffix: int = 1) -> str:
    source = str(value or "")
    if not source:
        return ""
    if len(source) <= visible_prefix + visible_suffix:
        return source[0] + "*" * max(len(source) - 1, 0)
    return f"{source[:visible_prefix]}{'*' * (len(source) - visible_prefix - visible_suffix)}{source[-visible_suffix:]}"


def mask_email(email: str) -> str:
    source = str(email or "")
    if "@" not in source:
        return _mask_middle(source, visible_prefix=1, visible_suffix=0)
    local, domain = source.split("@", 1)
    return f"{_mask_middle(local, visible_prefix=1, visible_suffix=0)}@{domain}"


def mask_phone(phone: str) -> str:
    digits = "".join(ch for ch in str(phone or "") if ch.isdigit())
    if len(digits) < 7:
        return _mask_middle(str(phone or ""), visible_prefix=2, visible_suffix=0)
    return f"{digits[:3]}****{digits[-4:]}"


def mask_name(name: str) -> str:
    source = str(name or "")
    if len(source) <= 1:
        return source
    return source[0] + "*" * (len(source) - 1)


def mask_address(address: str) -> str:
    source = str(address or "")
    if len(source) <= 4:
        return _mask_middle(source, visible_prefix=1, visible_suffix=0)
    return source[:4] + "*" * max(len(source) - 4, 0)


def apply_masking_to_orders(rows: list[dict[str, Any]] | dict[str, Any]) -> list[dict[str, Any]] | dict[str, Any]:
    is_single = isinstance(rows, dict)
    targets = [rows] if is_single else rows
    for row in targets:
        if "user_email" in row:
            row["user_email"] = mask_email(str(row.get("user_email") or ""))
        if "user_name" in row:
            row["user_name"] = mask_name(str(row.get("user_name") or ""))
        if "recipient" in row:
            row["recipient"] = mask_name(str(row.get("recipient") or ""))
        if "phone" in row:
            row["phone"] = mask_phone(str(row.get("phone") or ""))
        for field in ("road_address", "jibun_address", "detail_address"):
            if field in row:
                row[field] = mask_address(str(row.get(field) or ""))
    return targets[0] if is_single else targets


def apply_masking_to_users(rows: list[dict[str, Any]] | dict[str, Any]) -> list[dict[str, Any]] | dict[str, Any]:
    is_single = isinstance(rows, dict)
    targets = [rows] if is_single else rows
    for row in targets:
        if "email" in row:
            row["email"] = mask_email(str(row.get("email") or ""))
        if "name" in row:
            row["name"] = mask_name(str(row.get("name") or ""))
        if "phone" in row:
            row["phone"] = mask_phone(str(row.get("phone") or ""))
    return targets[0] if is_single else targets


def apply_masking_to_inquiries(rows: list[dict[str, Any]] | dict[str, Any]) -> list[dict[str, Any]] | dict[str, Any]:
    is_single = isinstance(rows, dict)
    targets = [rows] if is_single else rows
    for row in targets:
        if "user_email" in row:
            row["user_email"] = mask_email(str(row.get("user_email") or ""))
        if "user_name" in row:
            row["user_name"] = mask_name(str(row.get("user_name") or ""))
    return targets[0] if is_single else targets


def apply_masking_to_returns(rows: list[dict[str, Any]] | dict[str, Any]) -> list[dict[str, Any]] | dict[str, Any]:
    is_single = isinstance(rows, dict)
    targets = [rows] if is_single else rows
    for row in targets:
        if "user_email" in row:
            row["user_email"] = mask_email(str(row.get("user_email") or ""))
        if "order_no" in row:
            row["order_no"] = str(row.get("order_no") or "")
    return targets[0] if is_single else targets


def apply_masking_to_settlements(rows: list[dict[str, Any]] | dict[str, Any]) -> list[dict[str, Any]] | dict[str, Any]:
    is_single = isinstance(rows, dict)
    targets = [rows] if is_single else rows
    for row in targets:
        if "user_email" in row:
            row["user_email"] = mask_email(str(row.get("user_email") or ""))
    return targets[0] if is_single else targets


def get_client_ip(request) -> str:
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return str(request.META.get("REMOTE_ADDR") or "")


def log_audit_event(
    request,
    *,
    action: str,
    target_type: str = "",
    target_id: str = "",
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    result: str = AuditLog.Result.SUCCESS,
    error_code: str = "",
    idempotency_key: str = "",
) -> None:
    user = request.user if request and getattr(request, "user", None) and request.user.is_authenticated else None
    try:
        AuditLog.objects.create(
            actor_admin=user if user and getattr(user, "is_staff", False) else None,
            actor_role=get_admin_role(user) if user else "",
            action=action,
            target_type=target_type,
            target_id=str(target_id or ""),
            request_id=str(request.headers.get("X-Request-Id", "")) if request else "",
            idempotency_key=idempotency_key,
            ip=get_client_ip(request) if request else "",
            user_agent=str(request.headers.get("User-Agent", "")) if request else "",
            before_json=before or {},
            after_json=after or {},
            metadata_json=metadata or {},
            result=result,
            error_code=error_code,
        )
    except Exception:
        # Audit logging must not break operational APIs.
        return


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def build_request_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_stable_json(payload).encode("utf-8")).hexdigest()


def extract_idempotency_key(request, payload: dict[str, Any]) -> str:
    body_key = payload.get("idempotency_key") or payload.get("idempotencyKey")
    header_key = request.headers.get("Idempotency-Key")
    return str(body_key or header_key or "").strip()


def get_idempotent_replay_response(
    *,
    key: str,
    action: str,
    request_hash: str,
) -> Response | None:
    if not key:
        return None

    record = IdempotencyRecord.objects.filter(key=key).first()
    if not record:
        return None

    if record.action != action:
        raise ValidationError({"idempotency_key": "이미 다른 작업에서 사용된 멱등키입니다."})
    if record.request_hash != request_hash:
        raise ValidationError({"idempotency_key": "동일 멱등키로 다른 요청 본문을 사용할 수 없습니다."})
    return Response(record.response_body, status=record.response_status_code)


def save_idempotent_response(
    *,
    request,
    key: str,
    action: str,
    request_hash: str,
    response: Response,
    target_type: str = "",
    target_id: str = "",
) -> None:
    if not key:
        return

    user = request.user if request and getattr(request, "user", None) and request.user.is_authenticated else None
    try:
        record, created = IdempotencyRecord.objects.get_or_create(
            key=key,
            defaults={
                "action": action,
                "actor_admin": user if user and getattr(user, "is_staff", False) else None,
                "request_hash": request_hash,
                "response_status_code": int(response.status_code),
                "response_body": response.data if isinstance(response.data, dict) else {},
                "target_type": target_type,
                "target_id": str(target_id or ""),
            },
        )
    except IntegrityError:
        record = IdempotencyRecord.objects.filter(key=key).first()
        created = False

    if not record:
        return
    if created:
        return

    if record.action != action or record.request_hash != request_hash:
        raise ValidationError({"idempotency_key": "이미 사용된 멱등키입니다."})


def require_admin_permission(user: User, permission: str) -> None:
    if not has_admin_permission(user, permission):
        raise PermissionDenied("요청한 기능에 필요한 권한이 없습니다.")
