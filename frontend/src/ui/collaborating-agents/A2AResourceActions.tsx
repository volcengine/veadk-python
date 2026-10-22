import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { ModalButton } from "../../components/composites/ModalButton";
import { Button } from "../../components/primitives";
import { requestA2aCenterAgent, deleteA2aCenterSpace } from "../../adk/client";
import {
  centerAgentDetail,
  deletedResource,
  type CenterAgentDetail,
  type RegistryItem,
} from "../../adk/a2aSpace";
import { CollaboratorApiError } from "../../adk/collaboratingAgents";
import { TextShimmer } from "../text-shimmer/TextShimmer";

type Scope = { runtimeId: string; region: string; spaceId: string };
type MutationProps = {
  disabled: boolean;
  onBusy: (busy: boolean) => void;
  onUncertain: () => void;
  onDone: () => void;
};
function MutationDialog({
  label,
  title,
  message,
  confirm,
  disabled,
  request,
  onBusy,
  onUncertain,
  onDone,
  help,
}: MutationProps & {
  label: string;
  title: string;
  message: string;
  confirm: string;
  request: (signal: AbortSignal) => Promise<Response>;
  help?: string;
}) {
  const { t } = useTranslation("collaboratingAgents");
  const [open, setOpen] = useState(false);
  const [sending, setSending] = useState(false);
  const [unknown, setUnknown] = useState(false);
  const [error, setError] = useState("");
  const pending = useRef<AbortController | null>(null);
  const errorElement = useRef<HTMLParagraphElement>(null);
  useEffect(() => () => pending.current?.abort(), []);
  useEffect(() => {
    if (error) errorElement.current?.focus();
  }, [error]);
  function close() {
    if (pending.current) {
      pending.current.abort();
      pending.current = null;
      onUncertain();
      onBusy(false);
      setSending(false);
    }
    setOpen(false);
  }
  async function submit() {
    if (!open || pending.current || unknown) return;
    const controller = new AbortController();
    pending.current = controller;
    setSending(true);
    onBusy(true);
    setError("");
    try {
      await request(controller.signal).then(deletedResource);
      if (!controller.signal.aborted) {
        setOpen(false);
        onDone();
      }
    } catch (reason: unknown) {
      if (!controller.signal.aborted) {
        const unconfirmed =
          !(reason instanceof CollaboratorApiError) ||
          (reason.status >= 500 && reason.reason !== "read_failed");
        if (unconfirmed) {
          setUnknown(true);
          onUncertain();
        }
        const key =
          reason instanceof CollaboratorApiError ? reason.reason : undefined;
        setError(
          key === "read_failed"
            ? "actions.preflightFailed"
            : key === "runtime_auth_failed"
              ? "actions.runtimeAuthFailed"
              : unconfirmed
                ? "actions.uncertain"
                : key === "space_bound"
                  ? "spaceDeletion.bound"
                  : key === "space_not_empty"
                    ? "spaceDeletion.nonempty"
                    : reason instanceof CollaboratorApiError &&
                        [401, 403].includes(reason.status)
                      ? "actions.forbidden"
                      : "actions.rejected",
        );
      }
    } finally {
      if (!controller.signal.aborted) {
        pending.current = null;
        setSending(false);
        onBusy(false);
      }
    }
  }
  return (
    <>
      <ModalButton
        label={label}
        title={title}
        open={open}
        topGlow={false}
        buttonProps={{
          variant: "ghost",
          size: "compact",
          disabled,
          title: help,
        }}
        onOpenChange={(value) => {
          if (!value) close();
          else {
            setError("");
            setUnknown(false);
            setOpen(true);
          }
        }}
        closeLabel={t("close")}
        onClose={close}
        footer={
          <>
            <Button variant="outline" onClick={close}>
              {t("cancel")}
            </Button>
            <Button
              disabled={!open || sending || unknown}
              onClick={() => void submit()}
            >
              {confirm}
            </Button>
          </>
        }
      >
        <p>{message}</p>
        {sending && <TextShimmer as="span">{t("loading")}</TextShimmer>}
        {error && (
          <p role="alert" tabIndex={-1} ref={errorElement}>
            {t(error)}
          </p>
        )}
      </ModalButton>
      {help && <span className="collaborators-help">{help}</span>}
    </>
  );
}

export function A2AMemberActions({
  runtimeId,
  region,
  spaceId,
  item,
  ...mutation
}: Scope & MutationProps & { item: RegistryItem }) {
  const { t } = useTranslation("collaboratingAgents");
  const [open, setOpen] = useState(false);
  const [detail, setDetail] = useState<CenterAgentDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    setDetail(null);
    setError(false);
    setLoading(true);
    void requestA2aCenterAgent(runtimeId, region, spaceId, item.Id, {
      signal: controller.signal,
    })
      .then((response) => centerAgentDetail(response, item.Id))
      .then((result) => {
        if (!controller.signal.aborted) setDetail(result);
      })
      .catch(() => {
        if (!controller.signal.aborted) setError(true);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [open, runtimeId, region, spaceId, item.Id, retry]);
  const rows = detail
    ? [
        [t("name"), detail.name],
        [
          t("member.status"),
          t(
            detail.status === "running"
              ? "member.registered"
              : detail.status === "failed"
                ? "member.failed"
                : "member.unknownStatus",
          ),
        ],
        [
          t("registration.source"),
          detail.source === "Runtime"
            ? t("registration.runtime")
            : t("registration.standard"),
        ],
        [t("member.version"), detail.defaultVersion],
        [t("spaceCreation.project"), detail.projectName],
        [t("registration.runtimeId"), detail.runtimeId],
        [
          t("registration.network"),
          detail.networkType
            ? t(`registration.${detail.networkType}`)
            : undefined,
        ],
        [t("registration.importType"), detail.importType],
        [
          t("member.serviceAddress"),
          detail.serviceAddress || t("member.addressUnavailable"),
        ],
      ]
    : [];
  return (
    <div className="collaborators-actions">
      <ModalButton
        label={t("member.view")}
        title={item.Name}
        topGlow={false}
        open={open}
        onOpenChange={setOpen}
        buttonProps={{
          variant: "ghost",
          size: "compact",
          disabled: mutation.disabled,
        }}
        closeLabel={t("close")}
        footer={null}
      >
        {loading && <TextShimmer as="span">{t("loading")}</TextShimmer>}
        {error && (
          <div>
            <p role="alert">{t("member.loadFailed")}</p>
            <Button
              variant="outline"
              onClick={() => setRetry((value) => value + 1)}
            >
              {t("refresh")}
            </Button>
          </div>
        )}
        {detail && (
          <>
            <dl className="collaborators-detail">
              {rows
                .filter(([, value]) => value)
                .map(([label, value]) => (
                  <div key={label}>
                    <dt>{label}</dt>
                    <dd>{value}</dd>
                  </div>
                ))}
            </dl>
            <section
              className="collaborators-skill-section"
              aria-label={t("member.skills")}
            >
              <h4>{t("member.skills")}</h4>
              {detail.skills === null ? (
                <p>{t("member.skillsUnavailable")}</p>
              ) : detail.skills.length === 0 ? (
                <p>{t("member.noSkills")}</p>
              ) : (
                <ul className="collaborators-skill-list">
                  {detail.skills.map((skill) => (
                    <li key={skill.id}>
                      <strong>{skill.name}</strong>
                      {skill.description && <p>{skill.description}</p>}
                      {skill.tags.length > 0 && (
                        <p>
                          {t("member.tags")}: {skill.tags.join(" | ")}
                        </p>
                      )}
                      {skill.examples.length > 0 && (
                        <>
                          <p>{t("member.examples")}</p>
                          <ul>
                            {skill.examples.map((example, exampleIndex) => (
                              <li key={`${exampleIndex}-${example}`}>
                                {example}
                              </li>
                            ))}
                          </ul>
                        </>
                      )}
                    </li>
                  ))}
                </ul>
              )}
              {detail.skillsTruncated && <p>{t("member.skillsTruncated")}</p>}
            </section>
          </>
        )}
      </ModalButton>
      <MutationDialog
        {...mutation}
        label={t("member.unregister")}
        title={`${t("member.unregister")} ${item.Name}`}
        message={t("member.unregisterHelp")}
        confirm={t("member.confirmUnregister")}
        request={(signal) =>
          requestA2aCenterAgent(runtimeId, region, spaceId, item.Id, {
            method: "DELETE",
            signal,
          })
        }
      />
    </div>
  );
}

export function A2ASpaceDeletion({
  runtimeId,
  region,
  spaceId,
  name,
  blocked,
  ...mutation
}: Scope &
  MutationProps & {
    name: string;
    blocked?: "bound" | "nonempty" | "loading";
  }) {
  const { t } = useTranslation("collaboratingAgents");
  return (
    <MutationDialog
      {...mutation}
      disabled={mutation.disabled || !!blocked}
      help={blocked ? t(`spaceDeletion.${blocked}`) : undefined}
      label={t("spaceDeletion.open")}
      title={`${t("spaceDeletion.open")} ${name}`}
      message={t("spaceDeletion.help")}
      confirm={t("spaceDeletion.confirm")}
      request={(signal) =>
        deleteA2aCenterSpace(runtimeId, region, spaceId, signal)
      }
    />
  );
}
