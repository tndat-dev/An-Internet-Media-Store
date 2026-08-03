"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { useAuth } from "@/features/auth/AuthContext";
import { CART_UPDATED_EVENT, getCart } from "@/features/carts/api";

export function AccountBar() {
  const { user, roles, isLoading, logout } = useAuth();
  const router = useRouter();
  const isAdmin = roles.includes("ADMIN");
  const isManager = roles.includes("PRODUCT_MANAGER");
  const isStaff = isManager || isAdmin;
  const [cartCount, setCartCount] = useState(0);

  // Staff don't shop, so only customers track a cart badge. Seed from the current
  // cart on mount, then keep in sync with mutations broadcast by the cart API.
  useEffect(() => {
    if (isStaff) {
      return;
    }
    void getCart().catch(() => undefined);

    function handleCartUpdate(event: Event) {
      setCartCount((event as CustomEvent<number>).detail ?? 0);
    }
    window.addEventListener(CART_UPDATED_EVENT, handleCartUpdate);
    return () => window.removeEventListener(CART_UPDATED_EVENT, handleCartUpdate);
  }, [isStaff]);

  async function handleLogout() {
    await logout();
    router.push("/login");
  }

  return (
    <header className="account-bar">
      <Link href="/" className="account-bar-logo">
        AIMS
      </Link>
      <nav className="account-bar-actions">
        {/* Cart is a customer-only action; staff (PM/Admin) don't shop. */}
        {!isStaff ? (
          <Link href="/cart" className="account-bar-cart">
            Cart
            {cartCount > 0 ? <span className="cart-badge">{cartCount}</span> : null}
          </Link>
        ) : null}
        {isLoading ? (
          <span className="account-bar-placeholder" aria-hidden="true" />
        ) : user ? (
          <>
            {/* Entry points into the role workspaces; in-workspace navigation
                lives in each area's own sidebar/nav. */}
            {isManager && <Link href="/manager/products">Manager</Link>}
            {isAdmin && <Link href="/admin/users">User Management</Link>}
            <span className="account-bar-user">Hi, {user.username}</span>
            <button type="button" className="button-link account-bar-logout" onClick={handleLogout}>
              Logout
            </button>
          </>
        ) : (
          <>
            <Link href="/login">Login</Link>
            <Link href="/register">Register</Link>
          </>
        )}
      </nav>
    </header>
  );
}
