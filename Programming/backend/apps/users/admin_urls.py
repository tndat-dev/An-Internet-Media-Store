from django.urls import path

from apps.users.admin_views import (
    AdminAuditLogListView,
    AdminRoleListCreateView,
    AdminUserDetailView,
    AdminUserListCreateView,
    AdminUserResetPasswordView,
    AdminUserRolesView,
    AdminUserStatusView,
)


urlpatterns = [
    path("users/", AdminUserListCreateView.as_view(), name="admin-user-list-create"),
    path("users/<uuid:user_id>/", AdminUserDetailView.as_view(), name="admin-user-detail"),
    path("users/<uuid:user_id>/status/", AdminUserStatusView.as_view(), name="admin-user-status"),
    path("users/<uuid:user_id>/roles/", AdminUserRolesView.as_view(), name="admin-user-roles"),
    path("users/<uuid:user_id>/reset-password/", AdminUserResetPasswordView.as_view(), name="admin-user-reset-password"),
    path("roles/", AdminRoleListCreateView.as_view(), name="admin-role-list-create"),
    path("audit-logs/", AdminAuditLogListView.as_view(), name="admin-audit-logs"),
]
