import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { useTranslation } from "react-i18next";

import {
  cancelFeishuBotSetup,
  createFeishuBotSetup,
  getFeishuBotSetup,
  type FeishuBotSetupSession,
} from "../adk/feishuBotSetup";
import feishuLogo from "../assets/feishu-logo.svg";
import {
  FeishuCheckIcon,
  FeishuEyeIcon,
  FeishuEyeOffIcon,
  FeishuQrCodeIcon,
  FeishuRefreshIcon,
  FeishuSpinnerIcon,
} from "./FeishuDeploymentIcons";
import "./FeishuDeploymentCard.css";

type ConfigurationMode = "automatic" | "manual";

interface FeishuDeploymentCardProps {
  enabled: boolean;
  updating?: boolean;
  disabled?: boolean;
  agentName?: string;
  appId: string;
  appSecret: string;
  appIdConfigured?: boolean;
  appSecretConfigured?: boolean;
  onToggle: () => void | Promise<void>;
  onCredentialsChange: (appId: string, appSecret: string) => void;
}

const POLL_INTERVAL_MS = 1_500;

function formatCountdown(expiresAt?: string) {
  if (!expiresAt) return "10:00";
  const seconds = Math.max(
    0,
    Math.ceil((Date.parse(expiresAt) - Date.now()) / 1000),
  );
  return `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}

export function FeishuDeploymentCard({
  enabled,
  updating = false,
  disabled = false,
  agentName,
  appId,
  appSecret,
  appIdConfigured = false,
  appSecretConfigured = false,
  onToggle,
  onCredentialsChange,
}: FeishuDeploymentCardProps) {
  const { t } = useTranslation("ui");
  const [mode, setMode] = useState<ConfigurationMode>("automatic");
  const [session, setSession] = useState<FeishuBotSetupSession | null>(null);
  const [requesting, setRequesting] = useState(false);
  const [error, setError] = useState("");
  const [showSecret, setShowSecret] = useState(false);
  const [, setClock] = useState(0);
  const frontButtonRef = useRef<HTMLButtonElement | null>(null);
  const sessionRef = useRef<FeishuBotSetupSession | null>(null);
  const automaticTabRef = useRef<HTMLButtonElement | null>(null);
  const manualTabRef = useRef<HTMLButtonElement | null>(null);
  const automaticTabId = useId();
  const manualTabId = useId();
  const automaticPanelId = useId();
  const manualPanelId = useId();

  useEffect(() => {
    sessionRef.current = session;
  }, [session]);

  useEffect(
    () => () => {
      const activeSession = sessionRef.current;
      if (activeSession?.status === "waiting") {
        void cancelFeishuBotSetup(activeSession.id).catch(() => undefined);
      }
    },
    [],
  );

  useEffect(() => {
    if (!enabled) return;
    const frame = window.requestAnimationFrame(() => {
      (mode === "automatic" ? automaticTabRef : manualTabRef).current?.focus();
    });
    return () => window.cancelAnimationFrame(frame);
  }, [enabled]);

  useEffect(() => {
    if (!enabled || session?.status !== "waiting") return;
    const timer = window.setInterval(async () => {
      setClock((current) => current + 1);
      try {
        const next = await getFeishuBotSetup(session.id);
        setSession(next);
        if (next.status === "success" && next.credentials) {
          onCredentialsChange(
            next.credentials.appId,
            next.credentials.appSecret,
          );
          setShowSecret(false);
        }
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : String(cause));
      }
    }, POLL_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [enabled, onCredentialsChange, session?.id, session?.status]);

  const selectMode = (nextMode: ConfigurationMode) => {
    setMode(nextMode);
    window.requestAnimationFrame(() => {
      (nextMode === "automatic"
        ? automaticTabRef
        : manualTabRef
      ).current?.focus();
    });
  };

  const handleTabKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    selectMode(mode === "automatic" ? "manual" : "automatic");
  };

  const generateQrCode = async () => {
    setRequesting(true);
    setError("");
    try {
      if (session?.status === "waiting") {
        await cancelFeishuBotSetup(session.id).catch(() => undefined);
      }
      setSession(
        await createFeishuBotSetup({ agentName: agentName || "Agent" }),
      );
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setRequesting(false);
    }
  };

  const closeCard = async () => {
    if (session?.status === "waiting")
      void cancelFeishuBotSetup(session.id).catch(() => undefined);
    setSession(null);
    setError("");
    await onToggle();
    window.requestAnimationFrame(() => frontButtonRef.current?.focus());
  };

  const automaticState = session?.status ?? "idle";

  return (
    <div className={`fdc-card${enabled ? " is-open" : ""}`}>
      <div className="fdc-card-inner">
        <button
          ref={frontButtonRef}
          type="button"
          className="fdc-face fdc-front"
          aria-pressed={enabled}
          aria-hidden={enabled}
          tabIndex={enabled ? -1 : 0}
          disabled={enabled || disabled || updating}
          onClick={() => void onToggle()}
        >
          <span className="fdc-logo">
            <img src={feishuLogo} alt="" />
          </span>
          <span className="fdc-front-copy">
            <strong>{t("feishuDeployment.name")}</strong>
            <small>
              {updating
                ? t("feishuDeployment.enabling")
                : t("feishuDeployment.description")}
            </small>
          </span>
        </button>

        <section
          className="fdc-face fdc-back"
          aria-label={t("feishuDeployment.configuration")}
          aria-hidden={!enabled}
          onKeyDown={(event) => {
            if (event.key === "Escape") {
              event.preventDefault();
              void closeCard();
            }
          }}
        >
          <div className="fdc-toolbar">
            <div className="fdc-tabs" role="tablist" aria-label={t("feishuDeployment.configurationMode")}>
              <button
                ref={automaticTabRef}
                id={automaticTabId}
                type="button"
                role="tab"
                aria-selected={mode === "automatic"}
                aria-controls={automaticPanelId}
                tabIndex={enabled && mode === "automatic" ? 0 : -1}
                onClick={() => setMode("automatic")}
                onKeyDown={handleTabKeyDown}
              >
                {t("feishuDeployment.automatic")}
              </button>
              <button
                ref={manualTabRef}
                id={manualTabId}
                type="button"
                role="tab"
                aria-selected={mode === "manual"}
                aria-controls={manualPanelId}
                tabIndex={enabled && mode === "manual" ? 0 : -1}
                onClick={() => setMode("manual")}
                onKeyDown={handleTabKeyDown}
              >
                {t("feishuDeployment.manual")}
              </button>
            </div>
            <button
              type="button"
              className="fdc-cancel"
              onClick={() => void closeCard()}
              disabled={!enabled || updating}
              tabIndex={enabled ? 0 : -1}
            >
              {updating ? t("feishuDeployment.cancelling") : t("common.cancel")}
            </button>
          </div>

          <div className="fdc-content">
            <div
              id={automaticPanelId}
              role="tabpanel"
              aria-labelledby={automaticTabId}
              hidden={mode !== "automatic"}
            >
              {automaticState === "idle" && (
                <div className="fdc-compact-state">
                  <span className="fdc-state-icon" aria-hidden="true">
                    <FeishuQrCodeIcon />
                  </span>
                  <span className="fdc-state-copy">
                    <strong>{t("feishuDeployment.scanToCreate")}</strong>
                    <small>{t("feishuDeployment.scanDescription")}</small>
                  </span>
                  <button
                    type="button"
                    className="fdc-primary"
                    tabIndex={enabled ? 0 : -1}
                    onClick={() => void generateQrCode()}
                    disabled={!enabled || requesting}
                  >
                    {requesting ? (
                      <>
                        <FeishuSpinnerIcon className="fdc-spinner" />
                        {t("common.generating")}
                      </>
                    ) : (
                      t("feishuDeployment.generateQrCode")
                    )}
                  </button>
                </div>
              )}
              {automaticState === "waiting" && session?.qrCodeDataUrl && (
                <div className="fdc-waiting">
                  <div className="fdc-qr-surface">
                    <img
                      src={session.qrCodeDataUrl}
                      alt={t("feishuDeployment.qrCodeAlt")}
                    />
                  </div>
                  <div className="fdc-waiting-copy">
                    <strong>{t("feishuDeployment.scanToConfirm")}</strong>
                    <small>{t("feishuDeployment.expiresIn", { time: formatCountdown(session.expiresAt) })}</small>
                    <button
                      type="button"
                      className="fdc-secondary"
                      tabIndex={enabled ? 0 : -1}
                      onClick={() => void generateQrCode()}
                      disabled={!enabled || requesting}
                    >
                      <FeishuRefreshIcon />
                      {t("common.refresh")}
                    </button>
                  </div>
                </div>
              )}
              {automaticState === "success" && (
                <div className="fdc-compact-state" role="status">
                  <span className="fdc-success-icon">
                    <FeishuCheckIcon />
                  </span>
                  <span className="fdc-state-copy">
                    <strong>{t("feishuDeployment.created")}</strong>
                    <small>{t("feishuDeployment.credentialsFilled")}</small>
                  </span>
                  <button
                    type="button"
                    className="fdc-secondary"
                    onClick={() => setMode("manual")}
                  >
                    {t("common.view")}
                  </button>
                </div>
              )}
              {(automaticState === "failed" ||
                automaticState === "expired") && (
                <div className="fdc-compact-state">
                  <span className="fdc-state-copy">
                    <strong>
                      {automaticState === "expired"
                        ? t("feishuDeployment.qrCodeExpired")
                        : t("feishuDeployment.automaticFailed")}
                    </strong>
                    <small>{session?.message || t("feishuDeployment.regenerateQrCode")}</small>
                  </span>
                  <button
                    type="button"
                    className="fdc-primary"
                    tabIndex={enabled ? 0 : -1}
                    onClick={() => void generateQrCode()}
                    disabled={!enabled || requesting}
                  >
                    {t("common.retry")}
                  </button>
                </div>
              )}
              {error && (
                <p className="fdc-error" role="alert">
                  {error}
                </p>
              )}
            </div>

            <div
              id={manualPanelId}
              role="tabpanel"
              aria-labelledby={manualTabId}
              hidden={mode !== "manual"}
            >
              <CredentialFields
                appId={appId}
                appSecret={appSecret}
                appIdConfigured={appIdConfigured}
                appSecretConfigured={appSecretConfigured}
                showSecret={showSecret}
                interactive={enabled}
                onShowSecretChange={setShowSecret}
                onCredentialsChange={onCredentialsChange}
              />
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}

interface CredentialFieldsProps {
  appId: string;
  appSecret: string;
  appIdConfigured?: boolean;
  appSecretConfigured?: boolean;
  showSecret: boolean;
  readOnly?: boolean;
  interactive: boolean;
  onShowSecretChange: (show: boolean) => void;
  onCredentialsChange: (appId: string, appSecret: string) => void;
}

function CredentialFields({
  appId,
  appSecret,
  appIdConfigured = false,
  appSecretConfigured = false,
  showSecret,
  readOnly = false,
  interactive,
  onShowSecretChange,
  onCredentialsChange,
}: CredentialFieldsProps) {
  const { t } = useTranslation("ui");
  return (
    <div className="fdc-fields">
      <label>
        <span>App ID</span>
        <input
          value={appId}
          readOnly={readOnly}
          disabled={!interactive}
          placeholder={
            appIdConfigured ? t("feishuDeployment.configuredPlaceholder") : "cli_xxxxxxxxxxxxxxxx"
          }
          autoComplete="off"
          onChange={(event) =>
            onCredentialsChange(event.target.value, appSecret)
          }
        />
      </label>
      <label>
        <span>App Secret</span>
        <span className="fdc-secret-field">
          <input
            type={showSecret ? "text" : "password"}
            value={appSecret}
            readOnly={readOnly}
            disabled={!interactive}
            placeholder={
              appSecretConfigured ? t("feishuDeployment.configuredPlaceholder") : t("feishuDeployment.appSecretPlaceholder")
            }
            autoComplete="off"
            onChange={(event) => onCredentialsChange(appId, event.target.value)}
          />
          <button
            type="button"
            aria-label={showSecret ? t("feishuDeployment.hideSecret") : t("feishuDeployment.showSecret")}
            onClick={() => onShowSecretChange(!showSecret)}
            tabIndex={interactive ? 0 : -1}
          >
            {showSecret ? <FeishuEyeOffIcon /> : <FeishuEyeIcon />}
          </button>
        </span>
      </label>
    </div>
  );
}
