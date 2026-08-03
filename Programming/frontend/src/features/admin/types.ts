import type { Role } from "@/features/auth/types";

export type UserStatus = "ACTIVE" | "DEACTIVATED" | "BLOCKED";

export type AdminUser = {
  userId: string;
  username: string;
  email: string;
  fullName: string;
  phone: string;
  status: UserStatus;
  roles: Role[];
  createdAt: string;
  lastLogin: string | null;
};

export type AdminRole = {
  roleId: string;
  roleName: string;
  description: string;
};

export type CreateUserPayload = {
  username: string;
  email: string;
  fullName?: string;
  phone?: string;
  roleNames: Role[];
};

export type AdminUserFilters = {
  search?: string;
  role?: string;
  status?: string;
};

// Mirrors DRF PageNumberPagination response shape.
export type Paginated<T> = {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
};
