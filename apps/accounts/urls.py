from django.urls import path

from .views import (
    HealthCheckAPIView,
    KakaoCallbackAPIView,
    LoginAPIView,
    LogoutAPIView,
    MeAPIView,
    RefreshAPIView,
)

urlpatterns = [
    path("health/", HealthCheckAPIView.as_view(), name="health-check"),
    path("auth/login", LoginAPIView.as_view(), name="auth-login"),
    path("auth/kakao/callback", KakaoCallbackAPIView.as_view(), name="auth-kakao-callback"),
    path("auth/refresh", RefreshAPIView.as_view(), name="auth-refresh"),
    path("auth/logout", LogoutAPIView.as_view(), name="auth-logout"),
    path("users/me", MeAPIView.as_view(), name="users-me"),
]
