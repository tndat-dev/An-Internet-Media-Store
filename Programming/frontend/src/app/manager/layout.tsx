"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

import { useAuth } from "@/features/auth/AuthContext";

import { ManagerSidebar } from "./ManagerSidebar";

/**
 * Client-side guard for /manager/*. UX only — the backend (IsProductManager) is
 * the real enforcement. Renders nothing for unauthorized users while redirecting,
 * so manager content never flashes.
 */
export default function ManagerLayout({ children }: { children: React.ReactNode }) {
  const { roles, isLoading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const allowed = roles.includes("PRODUCT_MANAGER") || roles.includes("ADMIN");

  useEffect(() => {
    if (!isLoading && !allowed) {
      router.replace(`/login?next=${encodeURIComponent(pathname)}`);
    }
  }, [isLoading, allowed, router, pathname]);

  if (isLoading) {
    return (
      <main className="manager-shell">
        <p className="alert">Checking access…</p>
      </main>
    );
  }
  if (!allowed) {
    return null;
  }
  return (
    <div className="manager-layout">
      <ManagerSidebar />
      <div className="manager-content">{children}</div>
    </div>
  );
}
