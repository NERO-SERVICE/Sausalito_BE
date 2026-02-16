from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.views import exception_handler


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return response

    if isinstance(exc, ValidationError):
        response.data = {
            "success": False,
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "입력값을 확인해주세요.",
                "details": response.data,
            },
        }
        return response

    details = response.data if isinstance(response.data, dict) else {"detail": response.data}
    code = _default_error_code(response.status_code)
    message = _default_error_message(response.status_code)

    response.data = {
        "success": False,
        "error": {
            "code": code,
            "message": message,
            "details": details,
        },
    }
    return response


def _default_error_code(status_code: int) -> str:
    mapping = {
        status.HTTP_400_BAD_REQUEST: "BAD_REQUEST",
        status.HTTP_401_UNAUTHORIZED: "UNAUTHORIZED",
        status.HTTP_403_FORBIDDEN: "FORBIDDEN",
        status.HTTP_404_NOT_FOUND: "NOT_FOUND",
        status.HTTP_429_TOO_MANY_REQUESTS: "TOO_MANY_REQUESTS",
    }
    return mapping.get(status_code, "API_ERROR")


def _default_error_message(status_code: int) -> str:
    mapping = {
        status.HTTP_400_BAD_REQUEST: "잘못된 요청입니다.",
        status.HTTP_401_UNAUTHORIZED: "인증이 필요합니다.",
        status.HTTP_403_FORBIDDEN: "권한이 없습니다.",
        status.HTTP_404_NOT_FOUND: "리소스를 찾을 수 없습니다.",
        status.HTTP_429_TOO_MANY_REQUESTS: "요청이 너무 많습니다.",
    }
    return mapping.get(status_code, "요청 처리 중 오류가 발생했습니다.")
