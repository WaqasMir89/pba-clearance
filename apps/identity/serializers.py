from rest_framework import serializers


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(max_length=256, trim_whitespace=False, write_only=True)


class SessionSerializer(serializers.Serializer):
    user = serializers.DictField()
    memberships = serializers.ListField(child=serializers.DictField())
    environment = serializers.CharField()
    enforcement_enabled = serializers.BooleanField()
