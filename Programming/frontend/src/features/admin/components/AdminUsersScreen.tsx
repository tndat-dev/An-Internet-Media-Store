"use client";

import { useEffect, useState } from "react";

import { useAuth } from "@/features/auth/AuthContext";
import type { Role } from "@/features/auth/types";

import { listAdminRoles, listAdminUsers } from "../api";
import type { AdminUser, AdminUserFilters } from "../types";
import { AdminUserCreateForm } from "./AdminUserCreateForm";
import { AdminUserRow } from "./AdminUserRow";

const STATUS_OPTIONS = ["ACTIVE", "DEACTIVATED", "BLOCKED"];

/**
 * Component: AdminUsersScreen
 *
 * Coupling/Cohesion: Procedural cohesion — coordinates user listing, filtering,
 * pagination, creation, and per-row mutations, delegating each concern to the
 * admin API and focused child components.
 */
export function AdminUsersScreen() {
  const { user: currentUser } = useAuth();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [availableRoles, setAvailableRoles] = useState<Role[]>([]);
  const [filters, setFilters] = useState<AdminUserFilters>({});
  const [draftFilters, setDraftFilters] = useState<AdminUserFilters>({});
  const [page, setPage] = useState(1);
  const [count, setCount] = useState(0);
  const [hasNext, setHasNext] = useState(false);
  const [hasPrev, setHasPrev] = useState(false);
  const [status, setStatus] = useState("Loading users...");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    let active = true;
    listAdminRoles()
      .then((roles) => {
        if (active) {
          setAvailableRoles(roles.map((role) => role.roleName as Role));
        }
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const response = await listAdminUsers(filters, page);
        if (active) {
          setUsers(response.results);
          setCount(response.count);
          setHasNext(Boolean(response.next));
          setHasPrev(Boolean(response.previous));
          setStatus("");
        }
      } catch (loadError) {
        if (active) {
          setStatus(loadError instanceof Error ? loadError.message : "Could not load users.");
        }
      }
    }
    void load();
    return () => {
      active = false;
    };
  }, [filters, page]);

  function reload() {
    // Re-trigger the load effect by cloning the current filters object.
    setFilters((current) => ({ ...current }));
  }

  function applyFilters(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setStatus("Loading users...");
    setPage(1);
    setFilters(draftFilters);
  }

  function handleUserChanged(updated: AdminUser) {
    setUsers((current) => current.map((item) => (item.userId === updated.userId ? updated : item)));
  }

  return (
    <main className="manager-shell">
      <header className="workspace-header">
        <div>
          <p className="eyebrow">AIMS Administrator</p>
          <h1>User Management</h1>
          <p className="lead">
            Create and manage Product Manager / Administrator accounts, assign roles, and control access.
          </p>
        </div>
      </header>

      <AdminUserCreateForm
        availableRoles={availableRoles}
        onCreated={() => {
          setPage(1);
          reload();
        }}
      />

      <section className="workspace-card">
        <form className="toolbar" onSubmit={applyFilters}>
          <label className="field compact-field">
            <span>Search</span>
            <input
              value={draftFilters.search ?? ""}
              placeholder="Username or email"
              onChange={(event) => setDraftFilters((current) => ({ ...current, search: event.target.value }))}
            />
          </label>
          <label className="field compact-field">
            <span>Role</span>
            <select
              value={draftFilters.role ?? ""}
              onChange={(event) => setDraftFilters((current) => ({ ...current, role: event.target.value }))}
            >
              <option value="">All roles</option>
              {availableRoles.map((role) => (
                <option key={role} value={role}>
                  {role}
                </option>
              ))}
            </select>
          </label>
          <label className="field compact-field">
            <span>Status</span>
            <select
              value={draftFilters.status ?? ""}
              onChange={(event) => setDraftFilters((current) => ({ ...current, status: event.target.value }))}
            >
              <option value="">All statuses</option>
              {STATUS_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </label>
          <button className="button button-secondary" type="submit">
            Apply
          </button>
        </form>

        {error ? <div className="alert alert-error">{error}</div> : null}
        {notice ? <div className="alert">{notice}</div> : null}
        {status ? <div className="alert">{status}</div> : null}

        <p className="catalog-summary">{count} user{count === 1 ? "" : "s"}</p>

        <div className="table-shell">
          <table>
            <thead>
              <tr>
                <th>User</th>
                <th>Status</th>
                <th>Roles</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map((user) => (
                <AdminUserRow
                  key={user.userId}
                  user={user}
                  availableRoles={availableRoles}
                  isSelf={currentUser?.userId === user.userId}
                  onChanged={handleUserChanged}
                  onError={setError}
                  onNotice={setNotice}
                />
              ))}
            </tbody>
          </table>
        </div>

        {hasPrev || hasNext ? (
          <nav className="catalog-pagination" aria-label="User pages">
            <button
              type="button"
              className="button button-secondary"
              disabled={!hasPrev}
              onClick={() => setPage((current) => current - 1)}
            >
              Previous
            </button>
            <span className="catalog-page-indicator">Page {page}</span>
            <button
              type="button"
              className="button button-secondary"
              disabled={!hasNext}
              onClick={() => setPage((current) => current + 1)}
            >
              Next
            </button>
          </nav>
        ) : null}
      </section>
    </main>
  );
}
