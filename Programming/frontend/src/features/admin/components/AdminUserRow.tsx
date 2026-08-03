"use client";

import { useState } from "react";

import { parseApiError } from "@/lib/apiClient";
import type { Role } from "@/features/auth/types";

import { resetAdminUserPassword, setAdminUserRoles, setAdminUserStatus } from "../api";
import type { AdminUser } from "../types";

type AdminUserRowProps = {
  user: AdminUser;
  availableRoles: Role[];
  isSelf: boolean;
  onChanged: (user: AdminUser) => void;
  onError: (message: string) => void;
  onNotice: (message: string) => void;
};

const ROLE_LABEL: Record<Role, string> = {
  CUSTOMER: "Customer",
  PRODUCT_MANAGER: "Product Manager",
  ADMIN: "Administrator",
};

function sameRoles(a: Role[], b: Role[]) {
  return a.length === b.length && [...a].sort().join() === [...b].sort().join();
}

/**
 * Component: AdminUserRow
 *
 * One editable user row: inline role assignment, status toggle, and password
 * reset. Each action delegates to the admin API; backend guards (last-admin,
 * self-lockout) surface as inline errors. Functional cohesion per user record.
 */
export function AdminUserRow({ user, availableRoles, isSelf, onChanged, onError, onNotice }: AdminUserRowProps) {
  const [draftRoles, setDraftRoles] = useState<Role[]>(user.roles);
  const [busy, setBusy] = useState(false);

  const rolesChanged = !sameRoles(draftRoles, user.roles);
  const isActive = user.status === "ACTIVE";

  function toggleRole(role: Role) {
    setDraftRoles((current) =>
      current.includes(role) ? current.filter((item) => item !== role) : [...current, role],
    );
  }

  async function run(action: () => Promise<AdminUser | void>, successNotice?: string) {
    setBusy(true);
    onError("");
    onNotice("");
    try {
      const updated = await action();
      if (updated) {
        onChanged(updated);
        setDraftRoles(updated.roles);
      }
      if (successNotice) {
        onNotice(successNotice);
      }
    } catch (error) {
      const fields = parseApiError(error);
      const firstField = Object.values(fields)[0];
      onError(firstField ?? (error instanceof Error ? error.message : "Action failed."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <tr>
      <td>
        <strong>{user.username}</strong>
        <span className="muted-line">{user.email}</span>
        {user.fullName ? <span className="muted-line">{user.fullName}</span> : null}
      </td>
      <td>
        <span className={`status-pill status-${user.status.toLowerCase()}`}>{user.status}</span>
        {isSelf ? <span className="muted-line">(you)</span> : null}
      </td>
      <td>
        <div className="role-options">
          {availableRoles.map((role) => (
            <label key={role} className="role-checkbox">
              <input
                type="checkbox"
                checked={draftRoles.includes(role)}
                disabled={busy}
                onChange={() => toggleRole(role)}
              />
              <span>{ROLE_LABEL[role] ?? role}</span>
            </label>
          ))}
        </div>
        {rolesChanged ? (
          <button
            type="button"
            className="button button-secondary button-small"
            disabled={busy}
            onClick={() => run(() => setAdminUserRoles(user.userId, draftRoles), "Roles updated.")}
          >
            Save roles
          </button>
        ) : null}
      </td>
      <td>
        <div className="row-actions">
          <button
            type="button"
            className={isActive ? "button button-danger button-small" : "button button-secondary button-small"}
            disabled={busy}
            onClick={() =>
              run(
                () => setAdminUserStatus(user.userId, isActive ? "DEACTIVATED" : "ACTIVE"),
                isActive ? "User deactivated." : "User activated.",
              )
            }
          >
            {isActive ? "Deactivate" : "Activate"}
          </button>
          <button
            type="button"
            className="button button-secondary button-small"
            disabled={busy}
            onClick={() =>
              run(async () => {
                await resetAdminUserPassword(user.userId);
              }, "Password reseted — new password emailed.")
            }
          >
            Reset password
          </button>
        </div>
      </td>
    </tr>
  );
}
