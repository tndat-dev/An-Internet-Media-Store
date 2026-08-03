"use client";

import { useState } from "react";

import { parseApiError } from "@/lib/apiClient";
import type { Role } from "@/features/auth/types";

import { createAdminUser } from "../api";
import type { AdminUser } from "../types";

type AdminUserCreateFormProps = {
  availableRoles: Role[];
  onCreated: (user: AdminUser) => void;
};

const ROLE_LABEL: Record<Role, string> = {
  CUSTOMER: "Customer",
  PRODUCT_MANAGER: "Product Manager",
  ADMIN: "Administrator",
};

/**
 * Component: AdminUserCreateForm
 *
 * Coupling/Cohesion: Data coupling with the admin API through explicit user fields.
 * Functional cohesion — it only collects and submits a new internal user. The
 * server generates and emails the initial password (printed to the backend console
 * in the demo); it is never returned here.
 */
export function AdminUserCreateForm({ availableRoles, onCreated }: AdminUserCreateFormProps) {
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [phone, setPhone] = useState("");
  const [roleNames, setRoleNames] = useState<Role[]>(["PRODUCT_MANAGER"]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  function toggleRole(role: Role) {
    setRoleNames((current) =>
      current.includes(role) ? current.filter((item) => item !== role) : [...current, role],
    );
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setNotice("");
    if (roleNames.length === 0) {
      setError("Select at least one role.");
      return;
    }
    setIsSubmitting(true);
    try {
      const user = await createAdminUser({ username, email, fullName, phone, roleNames });
      setNotice(
        `User "${user.username}" created. A generated password was emailed (printed to the backend console in the demo).`,
      );
      setUsername("");
      setEmail("");
      setFullName("");
      setPhone("");
      setRoleNames(["PRODUCT_MANAGER"]);
      onCreated(user);
    } catch (submitError) {
      const fields = parseApiError(submitError);
      const firstField = Object.values(fields)[0];
      setError(firstField ?? (submitError instanceof Error ? submitError.message : "Could not create user."));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <form className="workspace-card admin-create-form" onSubmit={handleSubmit}>
      <h2>Create internal user</h2>
      <p className="lead">
        Administrators create Product Manager / Administrator accounts. Customers self-register and are
        not managed here.
      </p>

      {error ? <div className="alert alert-error">{error}</div> : null}
      {notice ? <div className="alert">{notice}</div> : null}

      <div className="form-grid">
        <label className="field">
          <span>Username *</span>
          <input value={username} required onChange={(event) => setUsername(event.target.value)} />
        </label>
        <label className="field">
          <span>Email *</span>
          <input type="email" value={email} required onChange={(event) => setEmail(event.target.value)} />
        </label>
        <label className="field">
          <span>Full name</span>
          <input value={fullName} onChange={(event) => setFullName(event.target.value)} />
        </label>
        <label className="field">
          <span>Phone</span>
          <input value={phone} onChange={(event) => setPhone(event.target.value)} />
        </label>
      </div>

      <fieldset className="form-section">
        <legend>Roles *</legend>
        <div className="role-options">
          {availableRoles.map((role) => (
            <label key={role} className="role-checkbox">
              <input
                type="checkbox"
                checked={roleNames.includes(role)}
                onChange={() => toggleRole(role)}
              />
              <span>{ROLE_LABEL[role] ?? role}</span>
            </label>
          ))}
        </div>
      </fieldset>

      <button className="button button-primary" type="submit" disabled={isSubmitting}>
        {isSubmitting ? "Creating..." : "Create user"}
      </button>
    </form>
  );
}
