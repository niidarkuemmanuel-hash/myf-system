from django.contrib.auth.models import User
from rest_framework import serializers

from .models import Profile


class SignupSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True, min_length=6)
    full_name = serializers.CharField(max_length=150)
    phone = serializers.CharField(max_length=20)
    level = serializers.CharField(max_length=100, required=False, allow_blank=True)

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
        profile.save()
        return profile


class ProfileFullSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profile
        fields = ["id", "full_name", "phone", "level", "role", "status"]


class ProfileNameSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profile
        fields = ["id", "full_name"]

from .models import Announcement, AttendanceRecord


class AnnouncementSerializer(serializers.ModelSerializer):
    posted_by = serializers.SerializerMethodField()

    class Meta:
        model = Announcement
        fields = ["id", "title", "message", "created_at", "posted_by"]
        read_only_fields = ["created_at"]

    def get_posted_by(self, obj):
        if obj.created_by and hasattr(obj.created_by, "profile"):
            return obj.created_by.profile.full_name
        return ""


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
