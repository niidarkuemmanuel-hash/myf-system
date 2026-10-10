from django.contrib.auth.models import User
from rest_framework import serializers

from .models import Announcement, AttendanceRecord, Group, Profile


class SignupSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True, min_length=6)
    full_name = serializers.CharField(max_length=150)
    phone = serializers.CharField(max_length=20)
    level = serializers.CharField(max_length=100, required=False, allow_blank=True)
    school = serializers.CharField(max_length=150, required=False, allow_blank=True)
    group = serializers.PrimaryKeyRelatedField(
        queryset=Group.objects.all(), required=False, allow_null=True
    )

    def validate_username(self, value):
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("That username is already taken.")
        return value

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data["username"],
            password=validated_data["password"],
        )
        profile = user.profile
        profile.full_name = validated_data["full_name"]
        profile.phone = validated_data["phone"]
        profile.level = validated_data.get("level", "")
        profile.school = validated_data.get("school", "")
        profile.group = validated_data.get("group")
        profile.save()
        return profile


class ProfileFullSerializer(serializers.ModelSerializer):
    group_name = serializers.SerializerMethodField()

    class Meta:
        model = Profile
        fields = [
            "id", "full_name", "phone", "level", "school", "role", "status",
            "group", "group_name",
        ]

    def get_group_name(self, obj):
        return obj.group.name if obj.group else ""


class ProfileNameSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profile
        fields = ["id", "full_name"]


class AnnouncementSerializer(serializers.ModelSerializer):
    posted_by = serializers.SerializerMethodField()
    media_url = serializers.SerializerMethodField()
    media = serializers.FileField(required=False, allow_null=True, write_only=True)

    class Meta:
        model = Announcement
        fields = [
            "id", "title", "message", "created_at", "posted_by",
            "media", "media_type", "media_url",
        ]
        read_only_fields = ["created_at", "media_type"]

    def get_posted_by(self, obj):
        if obj.created_by and hasattr(obj.created_by, "profile"):
            return obj.created_by.profile.full_name
        return ""

    def get_media_url(self, obj):
        if not obj.media:
            return ""
        request = self.context.get("request")
        url = obj.media.url
        return request.build_absolute_uri(url) if request else url

    def validate_media(self, f):
        if f is None:
            return f
        ctype = getattr(f, "content_type", "") or ""
        if not (ctype.startswith("image/") or ctype.startswith("video/")):
            raise serializers.ValidationError("Only pictures and videos are allowed.")
        if f.size > 50 * 1024 * 1024:
            raise serializers.ValidationError("That file is bigger than 50 MB.")
        return f


class AttendanceSerializer(serializers.ModelSerializer):
    present = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Profile.objects.filter(status="approved"),
        required=False,
    )
    present_names = serializers.SerializerMethodField()

    class Meta:
        model = AttendanceRecord
        fields = ["id", "event", "date", "present", "present_names"]

    def get_present_names(self, obj):
        return [p.full_name for p in obj.present.all()]
