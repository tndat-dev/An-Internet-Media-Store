"""Authentication endpoints for internal users (Product Manager / Administrator)."""

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users.serializers import (
    ChangePasswordSerializer,
    LoginInputSerializer,
    RegisterInputSerializer,
    UserSerializer,
)
from apps.users.services import AuthService


def _raise_drf(error: DjangoValidationError):
    raise ValidationError(error.message_dict if hasattr(error, "message_dict") else error.messages)


class LoginView(APIView):
    """POST /api/auth/login/ — verify credentials, return a token + user."""

    authentication_classes: list = []  # login itself needs no prior auth
    permission_classes: list = []

    def post(self, request):
        serializer = LoginInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            user, token = AuthService.login(
                username=serializer.validated_data["username"],
                password=serializer.validated_data["password"],
            )
        except DjangoValidationError as error:
            _raise_drf(error)
        return Response(
            {"token": token.key, "user": UserSerializer(user).data},
            status=status.HTTP_200_OK,
        )


class RegisterView(APIView):
    """POST /api/auth/register/ — public self-registration (always CUSTOMER)."""

    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request):
        serializer = RegisterInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            user, token = AuthService.register(
                username=data["username"],
                email=data["email"],
                password=data["password"],
                full_name=data.get("fullName", ""),
                phone=data.get("phone", ""),
            )
        except DjangoValidationError as error:
            _raise_drf(error)
        return Response(
            {"token": token.key, "user": UserSerializer(user).data},
            status=status.HTTP_201_CREATED,
        )


class ChangePasswordView(APIView):
    """POST /api/auth/change-password/ — optional self-service change (rotates token)."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            token = AuthService.change_password(
                request.user,
                old_password=serializer.validated_data["oldPassword"],
                new_password=serializer.validated_data["newPassword"],
            )
        except DjangoValidationError as error:
            _raise_drf(error)
        return Response({"token": token.key}, status=status.HTTP_200_OK)


class LogoutView(APIView):
    """POST /api/auth/logout/ — revoke the caller's token."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        AuthService.logout(request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    """GET /api/auth/me/ — the current authenticated internal user."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)
