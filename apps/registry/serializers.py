from rest_framework import serializers

from apps.registry.models import Client, Organization


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ["id", "code", "legal_name", "kind", "is_active", "is_demo", "created_at"]


class OrganizationInputSerializer(serializers.Serializer):
    legal_name = serializers.CharField(max_length=200)
    code = serializers.SlugField(max_length=40)
    kind = serializers.ChoiceField(choices=["channel", "agency"])


class ClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client
        fields = ["id", "code", "legal_name", "is_demo", "created_at"]


class ClientInputSerializer(serializers.Serializer):
    legal_name = serializers.CharField(max_length=200)
    code = serializers.SlugField(max_length=40)
    participant_ids = serializers.ListField(
        child=serializers.UUIDField(), min_length=1, max_length=20
    )
