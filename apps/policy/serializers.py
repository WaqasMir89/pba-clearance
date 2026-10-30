from rest_framework import serializers

from apps.policy.models import ClearanceCycle, Milestone, PolicyVersion


class PolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = PolicyVersion
        fields = [
            "id",
            "code",
            "version",
            "title",
            "source_reference",
            "source_sha256",
            "effective_from",
            "effective_until",
            "is_demo",
            "status",
            "created_at",
        ]


class PolicyInputSerializer(serializers.Serializer):
    code = serializers.SlugField(max_length=40)
    version = serializers.IntegerField(min_value=1)
    title = serializers.CharField(max_length=200)
    source_reference = serializers.CharField(max_length=255)
    source_sha256 = serializers.RegexField(r"^[a-f0-9]{64}$")
    effective_from = serializers.DateField()
    effective_until = serializers.DateField(required=False, allow_null=True)


class MilestoneSerializer(serializers.ModelSerializer):
    label = serializers.CharField(source="get_code_display", read_only=True)

    class Meta:
        model = Milestone
        fields = ["id", "code", "label", "local_date", "local_time", "timezone_name", "occurs_at"]


class CycleSerializer(serializers.ModelSerializer):
    policy = PolicySerializer(read_only=True)
    milestones = MilestoneSerializer(many=True, read_only=True)

    class Meta:
        model = ClearanceCycle
        fields = ["id", "code", "title", "policy", "broadcast_start", "broadcast_end", "milestones"]


class MilestoneInputSerializer(serializers.Serializer):
    code = serializers.ChoiceField(choices=Milestone.Code.choices)
    local_date = serializers.DateField()
    local_time = serializers.TimeField()


class CycleInputSerializer(serializers.Serializer):
    code = serializers.SlugField(max_length=60)
    title = serializers.CharField(max_length=200)
    policy_id = serializers.UUIDField()
    broadcast_start = serializers.DateField()
    broadcast_end = serializers.DateField()
    milestones = MilestoneInputSerializer(many=True, min_length=3, max_length=5)
