/*
 * Coupling/Cohesion: owns HTTP integration for administrator user/role management
 * only (mounted at /api/admin/, all endpoints require an ADMIN token attached by
 * apiClient). Service-layer guards (last-admin, self-lockout) surface as 400s.
 */
import { apiClient } from "@/lib/apiClient";
import type { Role } from "@/features/auth/types";

import type {
  AdminRole,
  AdminUser,
  AdminUserFilters,
  CreateUserPayload,
  Paginated,
  UserStatus,
} from "./types";

function toQueryString(params: Record<string, string | undefined>) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value) {
      query.set(key, value);
    }
  }
  const queryString = query.toString();
  return queryString ? `?${queryString}` : "";
}

export function listAdminUsers(filters: AdminUserFilters = {}, page = 1) {
  const query = toQueryString({
    search: filters.search,
    role: filters.role,
    status: filters.status,
    page: page > 1 ? String(page) : undefined,
  });
  return apiClient<Paginated<AdminUser>>(`/admin/users/${query}`);
}

export function createAdminUser(payload: CreateUserPayload) {
  return apiClient<AdminUser>("/admin/users/", {
    method: "POST",
    body: payload,
  });
}

export function setAdminUserRoles(userId: string, roleNames: Role[]) {
  return apiClient<AdminUser>(`/admin/users/${userId}/roles/`, {
    method: "POST",
    body: { roleNames },
  });
}

export function setAdminUserStatus(userId: string, status: UserStatus) {
  return apiClient<AdminUser>(`/admin/users/${userId}/status/`, {
    method: "POST",
    body: { status },
  });
}

export function resetAdminUserPassword(userId: string) {
  return apiClient<void>(`/admin/users/${userId}/reset-password/`, {
    method: "POST",
  });
}

export function listAdminRoles() {
  return apiClient<AdminRole[]>("/admin/roles/");
}
