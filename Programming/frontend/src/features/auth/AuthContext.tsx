"use client";

/*
 * Auth provider for AIMS internal users + customers. Holds the current user and
 * exposes login/register/logout/changePassword. Hydrates from a stored token via
 * GET /me on mount (useEffect only -> no SSR hydration mismatch). The token is
 * stored by authToken.ts and attached to requests by apiClient.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import * as authApi from "./api";
import type { AuthUser, LoginPayload, RegisterPayload, Role } from "./types";
import { clearAuthToken, setAuthToken, UNAUTHORIZED_EVENT } from "@/lib/authToken";

type AuthContextValue = {
  user: AuthUser | null;
  roles: Role[];
  isLoading: boolean;
  login: (payload: LoginPayload) => Promise<AuthUser>;
  register: (payload: RegisterPayload) => Promise<AuthUser>;
  logout: () => Promise<void>;
  changePassword: (oldPassword: string, newPassword: string) => Promise<void>;
  refresh: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      setUser(await authApi.me());
    } catch {
      clearAuthToken();
      setUser(null);
    }
  }, []);

  // Hydrate on mount (client-only): if a token exists, resolve the user.
  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const current = await authApi.me();
        if (active) setUser(current);
      } catch {
        clearAuthToken();
        if (active) setUser(null);
      } finally {
        if (active) setIsLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  // React to 401s from anywhere: drop the user (token already cleared by apiClient).
  useEffect(() => {
    function onUnauthorized() {
      setUser(null);
    }
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
  }, []);

  const login = useCallback(async (payload: LoginPayload) => {
    const res = await authApi.login(payload);
    setAuthToken(res.token);
    setUser(res.user);
    return res.user;
  }, []);

  const register = useCallback(async (payload: RegisterPayload) => {
    const res = await authApi.register(payload);
    setAuthToken(res.token);
    setUser(res.user);
    return res.user;
  }, []);

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } catch {
      // best-effort; clear locally regardless
    }
    clearAuthToken();
    setUser(null);
  }, []);

  const changePassword = useCallback(async (oldPassword: string, newPassword: string) => {
    const res = await authApi.changePassword(oldPassword, newPassword);
    setAuthToken(res.token); // token rotates; swap immediately to avoid a 401 loop
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({ user, roles: user?.roles ?? [], isLoading, login, register, logout, changePassword, refresh }),
    [user, isLoading, login, register, logout, changePassword, refresh],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return ctx;
}
