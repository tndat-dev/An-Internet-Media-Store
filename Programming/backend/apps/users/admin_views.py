"""Administrator-only user/role management endpoints (mounted at /api/admin/).

All views require an authenticated ADMIN (IsAdministrator). Views are thin: they
validate input, delegate to the service layer (where guards + audit + email live),
and translate Django ValidationError to DRF 400. Soft-delete only — there is no
hard DELETE route (FK PROTECT on product history would block it).
"""

from django.core.exceptions import ObjectDoesNotExist, ValidationError as DjangoValidationError
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users.models import User, UserAuditLog
from apps.users.permissions import IsAdministrator
from apps.users.serializers import (
    AdminUserCreateSerializer,
    AdminUserSerializer,
    AdminUserUpdateSerializer,
    RoleSerializer,
    SetRolesSerializer,
    SetStatusSerializer,
    UserAuditLogSerializer,
)
from apps.users.services import AdminUserService, RoleService


class _Pagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


def _raise_drf(error: DjangoValidationError):
    raise ValidationError(error.message_dict if hasattr(error, "message_dict") else error.messages)


def _get_user_or_404(user_id: str) -> User:
    try:
        return AdminUserService.get_user(str(user_id))
    except (ObjectDoesNotExist, ValueError) as error:
        raise NotFound("User not found.") from error


class AdminUserListCreateView(APIView):
    permission_classes = [IsAdministrator]

    def get(self, request):
        users = AdminUserService.list_users()
        role = request.query_params.get("role")
        user_status = request.query_params.get("status")
        search = request.query_params.get("search")
        if role:
            users = users.filter(user_roles__role__role_name=role)
        if user_status:
            users = users.filter(status=user_status)
        if search:
            users = users.filter(username__icontains=search) | users.filter(email__icontains=search)
        users = users.distinct()
        paginator = _Pagination()
        page = paginator.paginate_queryset(users, request)
        return paginator.get_paginated_response(AdminUserSerializer(page, many=True).data)

    def post(self, request):
        serializer = AdminUserCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            user = AdminUserService.create_user(
                request.user,
                username=data["username"],
                email=data["email"],
                full_name=data.get("fullName", ""),
                phone=data.get("phone", ""),
                role_names=data.get("roleNames", []),
            )
        except DjangoValidationError as error:
            _raise_drf(error)
        return Response(AdminUserSerializer(user).data, status=status.HTTP_201_CREATED)


class AdminUserDetailView(APIView):
    permission_classes = [IsAdministrator]

    def get(self, request, user_id):
        return Response(AdminUserSerializer(_get_user_or_404(user_id)).data)

    def patch(self, request, user_id):
        target = _get_user_or_404(user_id)
        serializer = AdminUserUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            user = AdminUserService.update_profile(
                request.user, target,
                full_name=data.get("fullName"),
                phone=data.get("phone"),
                email=data.get("email"),
            )
        except DjangoValidationError as error:
            _raise_drf(error)
        return Response(AdminUserSerializer(user).data)


class AdminUserStatusView(APIView):
    permission_classes = [IsAdministrator]

    def post(self, request, user_id):
        target = _get_user_or_404(user_id)
        serializer = SetStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            user = AdminUserService.set_status(request.user, target, serializer.validated_data["status"])
        except DjangoValidationError as error:
            _raise_drf(error)
        return Response(AdminUserSerializer(user).data)


class AdminUserRolesView(APIView):
    permission_classes = [IsAdministrator]

    def post(self, request, user_id):
        target = _get_user_or_404(user_id)
        serializer = SetRolesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            user = AdminUserService.set_roles(request.user, target, serializer.validated_data["roleNames"])
        except DjangoValidationError as error:
            _raise_drf(error)
        return Response(AdminUserSerializer(user).data)


class AdminUserResetPasswordView(APIView):
    permission_classes = [IsAdministrator]

    def post(self, request, user_id):
        target = _get_user_or_404(user_id)
        try:
            AdminUserService.reset_password(request.user, target)
        except DjangoValidationError as error:
            _raise_drf(error)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminRoleListCreateView(APIView):
    permission_classes = [IsAdministrator]

    def get(self, request):
        return Response(RoleSerializer(RoleService.list_roles(), many=True).data)

    def post(self, request):
        serializer = RoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            role = RoleService.create_role(
                request.user,
                role_name=serializer.validated_data["role_name"],
                description=serializer.validated_data.get("description", ""),
            )
        except DjangoValidationError as error:
            _raise_drf(error)
        return Response(RoleSerializer(role).data, status=status.HTTP_201_CREATED)


class AdminAuditLogListView(APIView):
    permission_classes = [IsAdministrator]

    def get(self, request):
        logs = UserAuditLog.objects.select_related("actor", "target_user").all()
        paginator = _Pagination()
        page = paginator.paginate_queryset(logs, request)
        return paginator.get_paginated_response(UserAuditLogSerializer(page, many=True).data)
