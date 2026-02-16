from __future__ import annotations

from rest_framework import serializers


class NaverPayReadySerializer(serializers.Serializer):
    order_no = serializers.CharField()
    return_url = serializers.URLField()
    cancel_url = serializers.URLField()
    fail_url = serializers.URLField()


class NaverPayApproveSerializer(serializers.Serializer):
    order_no = serializers.CharField()
    payment_key = serializers.CharField()
    amount = serializers.IntegerField(min_value=0)


class NaverPayWebhookSerializer(serializers.Serializer):
    provider = serializers.CharField(default="NAVERPAY")
    event_type = serializers.CharField()
    event_id = serializers.CharField()
    order_no = serializers.CharField(required=False)
    status = serializers.CharField(required=False)
    payload = serializers.JSONField(required=False)


class NaverPayCancelSerializer(serializers.Serializer):
    order_no = serializers.CharField()
    amount = serializers.IntegerField(min_value=0, required=False)
    reason = serializers.CharField(required=False, allow_blank=True)
