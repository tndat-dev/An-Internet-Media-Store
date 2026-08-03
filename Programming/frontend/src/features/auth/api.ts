/*
 * Coupling/Cohesion: owns HTTP integration for authentication only.
 * The auth token is attached automatically by apiClient when present.
 */
import { apiClient } from "@/lib/apiClient";

import type { AuthResponse, AuthUser, LoginPayload, RegisterPayload } from "./types";

export function login(payload: LoginPayload) {
  return apiClient<AuthResponse>("/auth/login/", { method: "POST", body: payload });
}

export function register(payload: RegisterPayload) {
  return apiClient<AuthResponse>("/auth/register/", { method: "POST", body: payload });
}

export function logout() {
  return apiClient<void>("/auth/logout/", { method: "POST", body: {} });
}

export function me() {
  return apiClient<AuthUser>("/auth/me/");
}

export function changePassword(oldPassword: string, newPassword: string) {
  return apiClient<{ token: string }>("/auth/change-password/", {
    method: "POST",
    body: { oldPassword, newPassword },
  });
}
