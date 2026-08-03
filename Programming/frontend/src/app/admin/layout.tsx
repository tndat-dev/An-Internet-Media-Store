"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

import { useAuth } from "@/features/auth/AuthContext";

/**
 * Client-side guard for /admin/*. UX only — the backend (IsAdministrator) is the
 * real enforcement. Only ADMIN may enter; PRODUCT_MANAGER is sent to its own area.
 * Renders nothing for unauthorized users while redirecting (no content flash).
 */
export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const { roles, isLoading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const isAdmin = roles.includes("ADMIN");

  useEffect(() => {
    if (isLoading) {
      return;
    }
    if (!isAdmin) {
      const fallback = roles.includes("PRODUCT_MANAGER")
        ? "/manager/products"
        : `/login?next=${encodeURIComponent(pathname)}`;
      router.replace(fallback);
    }
  }, [isLoading, isAdmin, roles, router, pathname]);

  if (isLoading) {
    return (
      <main className="manager-shell">
        <p className="alert">Checking access…</p>
      </main>
    );
  }
  if (!isAdmin) {
    return null;
  }
  return <>{children}</>;
}
