from django.urls import path

from .views import (
    HealthCheckAPIView,
    InquiryListCreateAPIView,
    KakaoCallbackAPIView,
    LoginAPIView,
    LogoutAPIView,
    MeAPIView,
    MyPageDashboardAPIView,
    PasswordChangeAPIView,
    RecentViewedProductAPIView,
    RefreshAPIView,
    WishlistAPIView,
    WishlistDetailAPIView,
)

urlpatterns = [
    path("health/", HealthCheckAPIView.as_view(), name="health-check"),
    path("auth/login", LoginAPIView.as_view(), name="auth-login"),
    path("auth/kakao/callback", KakaoCallbackAPIView.as_view(), name="auth-kakao-callback"),
    path("auth/refresh", RefreshAPIView.as_view(), name="auth-refresh"),
    path("auth/logout", LogoutAPIView.as_view(), name="auth-logout"),
    path("users/me", MeAPIView.as_view(), name="users-me"),
    path("users/me/password", PasswordChangeAPIView.as_view(), name="users-password"),
    path("users/me/dashboard", MyPageDashboardAPIView.as_view(), name="users-dashboard"),
    path("users/me/wishlist", WishlistAPIView.as_view(), name="users-wishlist"),
    path("users/me/wishlist/<int:product_id>", WishlistDetailAPIView.as_view(), name="users-wishlist-detail"),
    path("users/me/recent-products", RecentViewedProductAPIView.as_view(), name="users-recent-products"),
    path("users/me/inquiries", InquiryListCreateAPIView.as_view(), name="users-inquiries"),
]
