from django.urls import include, path

urlpatterns = [
    path("", include("apps.accounts.urls")),
    path("", include("apps.catalog.urls")),
    path("", include("apps.reviews.urls")),
    path("", include("apps.cart.urls")),
    path("", include("apps.orders.urls")),
    path("", include("apps.payments.urls")),
]
