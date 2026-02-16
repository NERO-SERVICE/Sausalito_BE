from rest_framework import status
from rest_framework.response import Response


def success_response(data=None, message: str = "", status_code: int = status.HTTP_200_OK) -> Response:
    return Response({"success": True, "data": data, "message": message}, status=status_code)


def error_response(
    code: str,
    message: str,
    details=None,
    status_code: int = status.HTTP_400_BAD_REQUEST,
) -> Response:
    return Response(
        {
            "success": False,
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
            },
        },
        status=status_code,
    )
