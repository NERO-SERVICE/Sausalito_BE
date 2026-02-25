from django.urls import path

from .views import PresignedUploadAPIView

urlpatterns = [
    path("uploads/presign", PresignedUploadAPIView.as_view(), name="uploads-presign"),
]
