"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useAuth } from "@/features/auth/AuthContext";
import { parseApiError } from "@/lib/apiClient";

const MIN_PASSWORD_LENGTH = 8;

export default function RegisterPage() {
  const { user, isLoading, register } = useAuth();
  const router = useRouter();
  const [form, setForm] = useState({ username: "", email: "", password: "", confirm: "", fullName: "" });
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!isLoading && user) router.replace("/");
  }, [isLoading, user, router]);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    setFieldErrors({});
    if (form.password.length < MIN_PASSWORD_LENGTH) {
      setFieldErrors({ password: `Password must be at least ${MIN_PASSWORD_LENGTH} characters.` });
      return;
    }
    if (form.password !== form.confirm) {
      setFieldErrors({ confirm: "Passwords do not match." });
      return;
    }
    setSubmitting(true);
    try {
      await register({
        username: form.username,
        email: form.email,
        password: form.password,
        fullName: form.fullName,
      });
      router.replace("/");
    } catch (err) {
      const fields = parseApiError(err);
      if (Object.keys(fields).length) setFieldErrors(fields);
      else setError("Could not create your account. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="center-shell">
      <div className="auth-card workspace-card">
        <div className="auth-card-head">
          <span className="auth-logo">AIMS</span>
          <h1>Create your account</h1>
          <p className="lead">Register as a customer to track your orders.</p>
        </div>

        {error && <div className="alert alert-error">{error}</div>}

        <form className="product-form" onSubmit={handleSubmit}>
          <label className="field">
            <span>Full name</span>
            <input value={form.fullName} onChange={(e) => setForm({ ...form, fullName: e.target.value })} />
          </label>

          <label className="field">
            <span>Username</span>
            <input
              value={form.username}
              onChange={(e) => setForm({ ...form, username: e.target.value })}
              className={fieldErrors.username ? "input-error" : undefined}
              required
            />
            {fieldErrors.username && <span className="field-error">{fieldErrors.username}</span>}
          </label>

          <label className="field">
            <span>Email</span>
            <input
              type="email"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
              className={fieldErrors.email ? "input-error" : undefined}
              required
            />
            {fieldErrors.email && <span className="field-error">{fieldErrors.email}</span>}
          </label>

          <label className="field">
            <span>Password</span>
            <input
              type="password"
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              className={fieldErrors.password ? "input-error" : undefined}
              required
            />
            {fieldErrors.password && <span className="field-error">{fieldErrors.password}</span>}
          </label>

          <label className="field">
            <span>Confirm password</span>
            <input
              type="password"
              value={form.confirm}
              onChange={(e) => setForm({ ...form, confirm: e.target.value })}
              className={fieldErrors.confirm ? "input-error" : undefined}
              required
            />
            {fieldErrors.confirm && <span className="field-error">{fieldErrors.confirm}</span>}
          </label>

          <button type="submit" className="button button-primary full-width" disabled={submitting}>
            {submitting ? "Creating…" : "Create account"}
          </button>
        </form>

        <p className="auth-foot">
          Already have an account? <Link href="/login">Sign in</Link>
        </p>
      </div>
    </main>
  );
}
