import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import type { StudioRole } from "../adk/client";
import { listStudioUsers, STUDIO_ROLES, updateStudioUserRole, UserManagementError, type StudioUser, type StudioUsersPage } from "../adk/users";
import { DeploymentSelect } from "../ui/DeploymentSelect";
import { PageBackButton } from "../ui/PageBackButton";
import { TextShimmer } from "../ui/text-shimmer/TextShimmer";
import "./UserManagement.css";

function RefreshIcon() {
  return <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M16 7a6.5 6.5 0 1 0 .2 5M16 3.5V7h-3.5" /></svg>;
}

function errorCode(error: unknown): string {
  return error instanceof UserManagementError ? error.code : "request_failed";
}

function RoleDialog({ user, onClose, onSaved }: { user: StudioUser; onClose: () => void; onSaved: (user: StudioUser) => void }) {
  const { t, i18n } = useTranslation("users");
  const dialogRef = useRef<HTMLDialogElement>(null);
  const controller = useRef<AbortController | null>(null);
  const titleId = useId();
  const descriptionId = useId();
  const [role, setRole] = useState(user.role);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    const dialog = dialogRef.current;
    const previousFocus = document.activeElement;
    dialog?.showModal();
    return () => {
      controller.current?.abort();
      dialog?.close();
      if (previousFocus instanceof HTMLElement && previousFocus.isConnected) previousFocus.focus();
    };
  }, []);
  const save = async () => {
    if (busy || (role === user.role && !user.roleConflict)) return;
    const request = new AbortController();
    controller.current = request;
    setBusy(true);
    setError("");
    try {
      const updated = await updateStudioUserRole(user, role, request.signal);
      if (!request.signal.aborted) onSaved(updated);
    } catch (cause) {
      if (!request.signal.aborted) setError(t(`errors.${errorCode(cause)}`, { defaultValue: t("errors.request_failed") }));
    } finally {
      if (!request.signal.aborted) setBusy(false);
    }
  };
  return (
    <dialog ref={dialogRef} className="user-role-dialog" aria-labelledby={titleId} aria-describedby={descriptionId} aria-busy={busy} onCancel={(event) => { event.preventDefault(); if (!busy) onClose(); }}>
      <header><h2 id={titleId}>{t("changeRole")}</h2><button type="button" className="users-close" onClick={onClose} disabled={busy} aria-label={t("close")}><svg viewBox="0 0 20 20" aria-hidden="true"><path d="m5 5 10 10M15 5 5 15" /></svg></button></header>
      <div className="user-role-dialog-body">
        <div className="users-account"><strong>{user.name}</strong><span>{user.email || user.id}</span></div>
        <label className="users-field-label">{t("role")}</label>
        <DeploymentSelect key={i18n.resolvedLanguage} ariaLabel={t("role")} placeholder={t("role")} value={role} disabled={busy} options={STUDIO_ROLES.map((value) => ({ value, label: t(`roles.${value}`), description: t(`descriptions.${value}`) }))} onChange={(value) => { const next = STUDIO_ROLES.find((item) => item === value); if (next) setRole(next); }} />
        <p id={descriptionId} className="users-help">{t("effectiveAfterRefresh")}</p>
        {error ? <p className="users-error" role="alert">{error}</p> : null}
      </div>
      <footer><button className="users-button" type="button" disabled={busy} onClick={onClose}>{t("cancel")}</button><button className="users-button is-primary" type="button" disabled={busy || (role === user.role && !user.roleConflict)} onClick={() => void save()}>{busy ? t("saving") : t("save")}</button></footer>
    </dialog>
  );
}

export function UserManagement({ onBack }: { onBack: () => void }) {
  const { t, i18n } = useTranslation("users");
  const [data, setData] = useState<StudioUsersPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [input, setInput] = useState("");
  const [query, setQuery] = useState("");
  const [role, setRole] = useState<StudioRole | "">("");
  const [page, setPage] = useState(1);
  const [revision, setRevision] = useState(0);
  const [editing, setEditing] = useState<StudioUser | null>(null);
  const [saved, setSaved] = useState<StudioUser | null>(null);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    listStudioUsers({ page, query, role, signal: controller.signal }).then((result) => {
      if (controller.signal.aborted) return;
      if (result.total > 0 && result.items.length === 0 && page > 1) { setPage(1); return; }
      setData(result);
      setUpdatedAt(new Date());
    }).catch((cause) => {
      if (!controller.signal.aborted) setError(errorCode(cause));
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false);
    });
    return () => controller.abort();
  }, [page, query, role, revision]);

  const search = (event: FormEvent) => { event.preventDefault(); setQuery(input.trim()); setPage(1); setRevision((value) => value + 1); };
  const lastLogin = (value: string) => {
    if (!value) return t("neverLoggedIn");
    const numeric = Number(value);
    const date = new Date(Number.isFinite(numeric) && numeric > 0 ? (numeric < 1e12 ? numeric * 1000 : numeric) : value);
    return Number.isNaN(date.getTime()) ? t("unknown") : date.toLocaleString(i18n.resolvedLanguage, { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false });
  };
  const pages = Math.max(1, Math.ceil((data?.total ?? 0) / 20));
  return (
    <section className="users-page" aria-labelledby="users-title">
      <header className="users-page-header"><PageBackButton label={t("back")} onClick={onBack} /><h1 id="users-title">{t("title")}</h1>{data ? <span className="users-count">{t("memberCount", { count: data.poolTotal })}</span> : null}</header>
      <div className="users-content">
        {data ? <div className="users-pool"><span>{data.provider === "byteplus" ? "BytePlus Identity" : t("volcengineIdentity")}</span><span className="users-pool-id" title={data.userPoolId}>{t("pool")} {data.userPoolId}</span></div> : null}
        <div className="users-toolbar">
          <form className="users-search" onSubmit={search}><input value={input} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && (event.nativeEvent.isComposing || event.keyCode === 229)) event.preventDefault(); }} aria-label={t("searchPlaceholder")} placeholder={t("searchPlaceholder")} maxLength={200} /><button type="submit" className="users-button" disabled={loading}>{t("search")}</button></form>
          <div className="users-role-filter"><DeploymentSelect ariaLabel={t("filterRole")} placeholder={t("allRoles")} value={role} options={[{ value: "", label: t("allRoles") }, ...STUDIO_ROLES.map((value) => ({ value, label: t(`roles.${value}`) }))]} onChange={(value) => { const next = STUDIO_ROLES.find((item) => item === value); setRole(next ?? ""); setPage(1); }} /></div>
          <button type="button" className="users-button users-refresh" disabled={loading} onClick={() => { setSaved(null); setRevision((value) => value + 1); }}><RefreshIcon /><span>{t("refresh")}</span></button>
        </div>
        <div className="users-feedback" aria-live="polite">{loading ? <TextShimmer>{t("loading")}</TextShimmer> : saved ? <span>{t("saved", { name: saved.name, role: t(`roles.${saved.role}`) })}</span> : updatedAt ? <span>{t("updatedAt", { time: updatedAt.toLocaleTimeString(i18n.resolvedLanguage, { hour: "2-digit", minute: "2-digit", hour12: false }) })}</span> : null}</div>
        {error ? <div className="users-error users-error-banner" role="alert"><span>{t(`errors.${error}`, { defaultValue: t("errors.request_failed") })}</span><button type="button" className="users-button" onClick={() => setRevision((value) => value + 1)}>{t("retry")}</button></div> : null}
        <div className="users-table-wrap" aria-busy={loading}>
          <table className="users-table"><thead><tr><th scope="col">{t("user")}</th><th scope="col">{t("role")}</th><th scope="col">{t("status")}</th><th scope="col">{t("lastLogin")}</th><th scope="col"><span className="sr-only">{t("actions")}</span></th></tr></thead>
            <tbody>{data?.items.map((user) => <tr key={user.id}>
              <td data-label={t("user")}><div className="users-person"><span className="users-avatar" aria-hidden="true">{Array.from(user.name)[0]?.toUpperCase()}</span><div className="users-account"><strong>{user.name}{user.currentUser ? <span className="users-self">{t("you")}</span> : null}</strong><span title={user.email || user.id}>{user.email || user.id}</span></div></div></td>
              <td data-label={t("role")}><span className={`users-role-badge${user.role === "super_admin" ? " is-super" : ""}`}>{t(`roles.${user.role}`)}</span>{user.roleConflict ? <span className="users-inline-warning">{t("roleConflict")}</span> : null}</td>
              <td data-label={t("status")}><span className="users-status">{t(`states.${user.status}`, { defaultValue: t("unknown") })}</span></td>
              <td data-label={t("lastLogin")} className="users-last-login">{lastLogin(user.lastLogin)}</td>
              <td className="users-actions">{user.protected ? <span className="users-protected" title={t("protectedExplanation")}>{t("initialAdministrator")}</span> : <button type="button" className="users-button is-text" disabled={loading || Boolean(error) || user.currentUser} onClick={() => { setSaved(null); setEditing(user); }}>{t("changeRole")}</button>}</td>
            </tr>)}</tbody>
          </table>
          {!loading && !error && data?.items.length === 0 ? <div className="users-empty"><strong>{t("noUsers")}</strong><span>{query || role ? t("tryAnotherSearch") : t("poolEmpty")}</span></div> : null}
          {loading && !data ? <div className="users-empty"><TextShimmer>{t("loading")}</TextShimmer></div> : null}
        </div>
        {data ? <footer className="users-pagination"><span>{t("resultCount", { count: data.total })}</span><div><button type="button" className="users-button" disabled={page <= 1 || loading} onClick={() => setPage((value) => value - 1)}>{t("previous")}</button><span>{page} / {pages}</span><button type="button" className="users-button" disabled={page >= pages || loading} onClick={() => setPage((value) => value + 1)}>{t("next")}</button></div></footer> : null}
      </div>
      {editing ? <RoleDialog user={editing} onClose={() => setEditing(null)} onSaved={(user) => { setEditing(null); setSaved(user); setRevision((value) => value + 1); }} /> : null}
    </section>
  );
}
