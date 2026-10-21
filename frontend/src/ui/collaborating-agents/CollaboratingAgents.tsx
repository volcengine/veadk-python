import { useEffect, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Button,
  Checkbox,
  FormLabel,
  InputWithTailIcon,
  Select,
  Textarea,
} from "../../components/primitives";
import { requestCollaborators } from "../../adk/client";
import {
  collaboratorResponse,
  CollaboratorApiError,
  type Collaborator,
  type CollaboratorConfig,
} from "../../adk/collaboratingAgents";
import { TextShimmer } from "../text-shimmer/TextShimmer";
import "./CollaboratingAgents.css";

type Target = { runtimeId: string; region: string };
const blank = (): CollaboratorConfig => ({
  name: "",
  description: "",
  card_url: "",
  enabled: true,
  auth_type: "none",
  secret: "",
  header_name: "",
});
function configOf(item: Collaborator): CollaboratorConfig {
  const {
    name,
    description,
    card_url,
    enabled,
    auth_type,

    header_name,
  } = item;
  return {
    name,
    description,
    card_url,
    enabled,
    auth_type,

    header_name,
    secret: "",
  };
}
function sameOrigin(left: string, right: string): boolean {
  try {
    return new URL(left).origin === new URL(right).origin;
  } catch {
    return false;
  }
}
export function CollaboratorManager({ runtimeId, region }: Target) {
  const { t } = useTranslation("collaboratingAgents");
  const [items, setItems] = useState<Collaborator[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState<Collaborator | "new" | null>(null);
  const [showSecret, setShowSecret] = useState(false);
  const [form, setForm] = useState<CollaboratorConfig>(blank);
  const [removing, setRemoving] = useState<Collaborator | null>(null);
  const controller = useRef<AbortController | null>(null);
  const id = useId();
  async function perform(
    suffix = "",
    init: RequestInit = {},
    onSuccess?: (
      result: Awaited<ReturnType<typeof collaboratorResponse>>,
    ) => void,
  ) {
    if (uncertain && init.method) return;
    // Ref closes the double-click gap before React renders disabled controls.
    if (controller.current && !controller.current.signal.aborted) return;
    const active = new AbortController();
    controller.current = active;
    setBusy(true);
    setError("");
    try {
      const result = await collaboratorResponse(
        await requestCollaborators(runtimeId, region, suffix, {
          ...init,
          signal: active.signal,
        }),
      );
      if (active.signal.aborted) return;
      if (onSuccess) onSuccess(result);
      else if (result && "items" in result) {
        setItems(result.items);
        setLoaded(true);
        setUncertain(false);
      }
    } catch (reason: unknown) {
      const unknown =
        !!init.method &&
        (!(reason instanceof CollaboratorApiError) || reason.status >= 500);
      if (!active.signal.aborted) {
        if (unknown) setUncertain(true);
        setError(
          unknown
            ? "uncertain"
            : reason instanceof CollaboratorApiError
              ? reason.status === 404
                ? suffix
                  ? "missing"
                  : "unsupported"
                : [401, 403].includes(reason.status)
                  ? "forbidden"
                  : reason.status === 409
                    ? "conflict"
                    : reason.status === 422
                      ? "invalid"
                      : "failed"
              : "failed",
        );
      }
    } finally {
      if (controller.current === active) {
        controller.current = null;
        if (!active.signal.aborted) setBusy(false);
      }
    }
  }
  useEffect(() => {
    void perform();
    return () => {
      controller.current?.abort();
    };
  }, [runtimeId, region]);
  function replace(item: Collaborator) {
    setItems((current) => [
      ...current.filter((row) => row.id !== item.id),
      item,
    ]);
  }
  function closeEditor() {
    setEditing(null);
    setForm(blank());
    setShowSecret(false);
  }
  const canKeepCredential =
    editing &&
    editing !== "new" &&
    editing.credential_configured &&
    editing.auth_type === form.auth_type &&
    editing.header_name === form.header_name &&
    sameOrigin(editing.card_url, form.card_url);
  async function save() {
    const selected = editing;
    if (!selected) return;
    await perform(
      selected === "new" ? "" : `/${selected.id}`,
      {
        method: selected === "new" ? "POST" : "PATCH",
        body: JSON.stringify({
          ...form,
          secret:
            form.auth_type !== "none" && form.secret ? form.secret : undefined,
          ...(selected === "new" ? {} : { revision: selected.revision }),
        }),
      },
      (result) => {
        if (result && "id" in result) {
          replace(result);
          closeEditor();
        }
      },
    );
  }
  return (
    <div className="collaborators">
      <p className="collaborators-context">
        {runtimeId} | {region}
      </p>
      <div className="collaborators-actions">
        <Button
          variant="outline"
          size="compact"
          disabled={busy}
          onClick={() => {
            closeEditor();
            setRemoving(null);
            void perform();
          }}
        >
          {t("refresh")}
        </Button>
        <Button
          size="compact"
          disabled={busy || uncertain || !loaded || !!editing}
          onClick={() => {
            setForm(blank());
            setShowSecret(false);
            setEditing("new");
            setRemoving(null);
          }}
        >
          {t("add")}
        </Button>
      </div>
      {busy && <TextShimmer as="span">{t("loading")}</TextShimmer>}
      {error && <p role="alert">{t(error)}</p>}
      {loaded && !items.length && !error && <p>{t("empty")}</p>}
      {items.map((item) => (
        <section className="collaborators-item" key={item.id}>
          <strong>{item.name}</strong>
          <span>
            {t(item.enabled ? "enabled" : "disabled")} |{" "}
            {t(
              item.check.status === "failed"
                ? "check_failed"
                : item.check.status,
            )}
          </span>
          <span className="collaborators-url">{item.card_url}</span>
          {item.description && <p>{item.description}</p>}
          {item.check.reason && (
            <p role="status">
              {t(`reasons.${item.check.reason}`, {
                defaultValue: t("checkFailed"),
              })}
            </p>
          )}
          {item.check.card && (
            <>
              <p>{t("discoveryOnly")}</p>
              <p>
                {t("capabilities")}:{" "}
                {item.check.card.skills.map((skill) => skill.name).join(", ") ||
                  t("none")}
              </p>
            </>
          )}
          <div className="collaborators-actions">
            <Button
              variant="outline"
              size="compact"
              disabled={busy || uncertain || !!editing}
              onClick={() =>
                void perform(
                  `/${item.id}/check`,
                  {
                    method: "POST",
                    body: JSON.stringify({ revision: item.revision }),
                  },
                  (result) => {
                    if (result && "id" in result) replace(result);
                  },
                )
              }
            >
              {t("check")}
            </Button>
            <Button
              variant="ghost"
              size="compact"
              disabled={busy || uncertain || !!editing}
              onClick={() => {
                setEditing(item);
                setForm(configOf(item));
                setShowSecret(false);
                setRemoving(null);
              }}
            >
              {t("edit")}
            </Button>
            <Button
              variant="ghost"
              size="compact"
              disabled={busy || uncertain || !!editing}
              onClick={() => setRemoving(item)}
            >
              {t("remove")}
            </Button>
          </div>
          {removing?.id === item.id && (
            <div role="group" aria-label={t("removeConfirm")}>
              <p>{t("removeConfirm")}</p>
              <div className="collaborators-actions">
                <Button
                  disabled={busy || uncertain}
                  onClick={() =>
                    void perform(
                      `/${item.id}?revision=${item.revision}`,
                      { method: "DELETE" },
                      () => {
                        setItems((current) =>
                          current.filter((row) => row.id !== item.id),
                        );
                        setRemoving(null);
                      },
                    )
                  }
                >
                  {t("confirmRemove")}
                </Button>
                <Button
                  variant="ghost"
                  disabled={busy || uncertain}
                  onClick={() => setRemoving(null)}
                >
                  {t("cancel")}
                </Button>
              </div>
            </div>
          )}
        </section>
      ))}
      {editing && (
        <form
          className="collaborators-form"
          onSubmit={(event) => {
            event.preventDefault();
            void save();
          }}
          onKeyDown={(event) => {
            if (event.key === "Enter" && event.nativeEvent.isComposing)
              event.preventDefault();
          }}
        >
          <FormLabel htmlFor={`${id}-name`} required>
            {t("name")}
          </FormLabel>
          <InputWithTailIcon
            className="collaborators-input"
            tailIcon={null}
            id={`${id}-name`}
            value={form.name}
            required
            maxLength={128}
            disabled={busy || uncertain}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
          <FormLabel htmlFor={`${id}-description`}>
            {t("description")}
          </FormLabel>
          <Textarea
            className="collaborators-field"
            id={`${id}-description`}
            value={form.description}
            maxLength={2000}
            disabled={busy || uncertain}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
          />
          <FormLabel htmlFor={`${id}-url`} required>
            {t("cardUrl")}
          </FormLabel>
          <InputWithTailIcon
            className="collaborators-input"
            tailIcon={null}
            type="url"
            pattern="https://.*"
            id={`${id}-url`}
            value={form.card_url}
            required
            maxLength={2048}
            disabled={busy || uncertain}
            placeholder="https://agent.example/.well-known/agent-card.json"
            onChange={(e) => setForm({ ...form, card_url: e.target.value })}
          />
          <FormLabel htmlFor={`${id}-auth`}>{t("authentication")}</FormLabel>
          <Select
            className="collaborators-field"
            id={`${id}-auth`}
            aria-label={t("authentication")}
            value={form.auth_type}
            disabled={busy || uncertain}
            options={[
              { value: "none", label: t("none") },
              { value: "bearer", label: "Bearer Token" },
              { value: "api_key", label: "API Key" },
            ]}
            onChange={(e) => {
              setShowSecret(false);
              setForm({
                ...form,
                auth_type: e.target.value as CollaboratorConfig["auth_type"],
                secret: "",
                header_name: e.target.value === "api_key" ? "X-API-Key" : "",
              });
            }}
          />
          {form.auth_type !== "none" && (
            <>
              <FormLabel htmlFor={`${id}-secret`} required={!canKeepCredential}>
                {t("secret")}
              </FormLabel>
              <div className="collaborators-secret-row">
                <InputWithTailIcon
                  className="collaborators-input"
                  tailIcon={null}
                  id={`${id}-secret`}
                  type={showSecret ? "text" : "password"}
                  autoComplete="new-password"
                  spellCheck={false}
                  value={form.secret}
                  maxLength={8192}
                  required={!canKeepCredential}
                  disabled={busy || uncertain}
                  aria-describedby={`${id}-secret-help`}
                  placeholder={canKeepCredential ? t("keepSecret") : undefined}
                  onChange={(e) => setForm({ ...form, secret: e.target.value })}
                />
                <Button
                  type="button"
                  variant="outline"
                  size="compact"
                  disabled={busy || uncertain}
                  aria-controls={`${id}-secret`}
                  aria-pressed={showSecret}
                  onClick={() => setShowSecret((value) => !value)}
                >
                  {t(showSecret ? "hideSecret" : "showSecret")}
                </Button>
              </div>
              <p id={`${id}-secret-help`} className="collaborators-help">
                {t(canKeepCredential ? "savedSecretHelp" : "secretHelp")}
              </p>
            </>
          )}
          {form.auth_type === "api_key" && (
            <>
              <FormLabel htmlFor={`${id}-header`} required>
                {t("header")}
              </FormLabel>
              <InputWithTailIcon
                className="collaborators-input"
                tailIcon={null}
                id={`${id}-header`}
                value={form.header_name}
                required
                maxLength={64}
                disabled={busy || uncertain}
                onChange={(e) =>
                  setForm({ ...form, header_name: e.target.value })
                }
              />
            </>
          )}
          <Checkbox
            label={t("enabled")}
            aria-describedby={`${id}-enabled-help`}
            checked={form.enabled}
            disabled={busy || uncertain}
            onChange={(e) => setForm({ ...form, enabled: e.target.checked })}
          />
          <p id={`${id}-enabled-help`} className="collaborators-help">
            {t("enabledHelp")}
          </p>
          <div className="collaborators-actions">
            <Button type="submit" disabled={busy || uncertain}>
              {t("save")}
            </Button>
            <Button
              variant="ghost"
              disabled={busy || uncertain}
              onClick={closeEditor}
            >
              {t("cancel")}
            </Button>
          </div>
        </form>
      )}
    </div>
  );
}
