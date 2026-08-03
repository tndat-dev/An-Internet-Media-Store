"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useAuth } from "@/features/auth/AuthContext";
import type { Role } from "@/features/auth/types";
import { parseApiError } from "@/lib/apiClient";

function destinationFor(roles: Role[]): string {
  if (typeof window !== "undefined") {
    const next = new URLSearchParams(window.location.search).get("next");
    if (next) return next;
  }
  return roles.includes("PRODUCT_MANAGER") || roles.includes("ADMIN") ? "/manager/products" : "/";
}

export default function LoginPage() {
  const { user, isLoading, login } = useAuth();
  const router = useRouter();
  const [form, setForm] = useState({ username: "", password: "" });
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  useEffect(() => {
    if (!isLoading && user) router.replace(destinationFor(user.roles));
  }, [isLoading, user, router]);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      const loggedIn = await login(form);
      router.replace(destinationFor(loggedIn.roles));
    } catch (err) {
      setError(parseApiError(err).detail ?? "Invalid username or password.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="center-shell">
      <div className="auth-card workspace-card">
        <div className="auth-card-head">
          <span className="auth-logo">AIMS</span>
          <h1>Sign in</h1>
          <p className="lead">Access your account to enjoy more!</p>
        </div>

        {error && <div className="alert alert-error">{error}</div>}

        <form className="product-form" onSubmit={handleSubmit}>
          <label className="field">
            <span>Email or Username</span>
            <input
              type="text"
              autoComplete="username"
              value={form.username}
              onChange={(e) => setForm({ ...form, username: e.target.value })}
              required
            />
          </label>

          <label className="field">
            <span>Password</span>
            <div className="input-with-action">
              <input
                type={showPassword ? "text" : "password"}
                autoComplete="current-password"
                value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
                required
              />
              <button type="button" className="button-link" onClick={() => setShowPassword((v) => !v)}>
                {showPassword ? "Hide" : "Show"}
              </button>
            </div>
          </label>

          <button type="submit" className="button button-primary full-width" disabled={submitting}>
            {submitting ? "Signing in…" : "Login"}
          </button>
        </form>

        <p className="auth-foot">
          New customer? <Link href="/register">Create an account</Link>
        </p>
        <p className="auth-foot">
          <Link href="/">← Back to Home</Link>
        </p>
      </div>
    </main>
  );
}
