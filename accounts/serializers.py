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