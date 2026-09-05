import { useEffect, useRef, useState } from "react";
import { ArrowRight, Github, LogIn } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { SiteBranding } from "../adk/client";
import { fetchProviders, loginTo, USERNAME_RE, type Provider } from "../adk/identity";
import byteplusLogo from "../assets/byteplus.svg";
import defaultSiteLogo from "../assets/logo.svg";
import { TextShimmer } from "./text-shimmer/TextShimmer";

const PROVIDER_LEGAL_URL = {
  volcengine: "https://docs.volcengine.com/docs/86681/1925174?lang=zh",
  byteplus: "https://docs.byteplus.com/en/docs/legal",
};

function providerIcon(id: string) {
  if (id.toLowerCase() === "github") return <Github className="icon" />;
  return <LogIn className="icon" />;
}

export interface LoginPageProps {
  branding: SiteBranding;
  cloudProvider: "volcengine" | "byteplus";
  /** Chosen username for the no-SSO local mode. */
  onUsername: (name: string) => void;
}

export function LoginPage({ branding, cloudProvider, onUsername }: LoginPageProps) {
  const { t } = useTranslation("shell");
  const [providers, setProviders] = useState<Provider[] | null>(null);
  const [providerError, setProviderError] = useState("");
  const [providerAttempt, setProviderAttempt] = useState(0);
  const [name, setName] = useState("");
  const nameInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let active = true;
    setProviders(null);
    setProviderError("");
    fetchProviders()
      .then((nextProviders) => {
        if (active) setProviders(nextProviders);
      })
      .catch((error) => {
        if (active) {
          setProviderError(error instanceof Error ? error.message : String(error));
        }
      });
    return () => {
      active = false;
    };
  }, [providerAttempt]);

  const showUsernameLogin = providers !== null && providers.length === 0;

  useEffect(() => {
    if (showUsernameLogin) nameInputRef.current?.focus();
  }, [showUsernameLogin]);

  const valid = USERNAME_RE.test(name);
  const fallbackLogo = cloudProvider === "byteplus" ? byteplusLogo : defaultSiteLogo;
  const submit = () => {
    if (valid) onUsername(name);
  };

  return (
    <div className="login">
      <header className="login-top">
        <span className="login-brand">
          <img
            className="login-brand-logo"
            src={branding.logoUrl || fallbackLogo}
            width={20}
            height={20}
            alt=""
            aria-hidden
          />
          {branding.title}
        </span>
      </header>

      <main className="login-main">
        <div className="login-card">
          <TextShimmer as="h1" className="login-title" duration={4.8} spread={22}>
            {branding.title}
          </TextShimmer>

          {providerError ? (
            <div className="login-provider-error" role="alert">
              <p>{providerError}</p>
              <button type="button" onClick={() => setProviderAttempt((attempt) => attempt + 1)}>
                {t("login.retry")}
              </button>
            </div>
          ) : providers === null ? null : providers.length > 0 ? (
            <>
              <p className="login-sub">{t("login.signInToContinue")}</p>
              <div className="login-providers">
                {providers.map((p) => (
                  <button key={p.id} className="login-btn" onClick={() => loginTo(p.loginUrl)}>
                    {providerIcon(p.id)}
                    <span>
                      {t("login.signInWith", {
                        provider:
                          p.id === "veidentity"
                            ? t(`login.identityProvider.${cloudProvider}`)
                            : p.label,
                      })}
                    </span>
                  </button>
                ))}
              </div>
            </>
          ) : (
            <>
              <p className="login-sub">{t("login.enterUsername")}</p>
              <form
                className="login-name"
                onSubmit={(e) => {
                  e.preventDefault();
                  submit();
                }}
              >
                <input
                  ref={nameInputRef}
                  className="login-name-input"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder={t("login.usernamePlaceholder")}
                  maxLength={16}
                />
                <button
                  type="submit"
                  className="login-name-go"
                  disabled={!valid}
                  aria-label={t("login.enter")}
                >
                  <ArrowRight className="icon" />
                </button>
              </form>
              {/* Always rendered so the error appearing doesn't shift the input;
                  the line's height is reserved via CSS min-height. */}
              <p className="login-hint" aria-live="polite">
                {name && !valid ? t("login.usernameInvalid") : ""}
              </p>
            </>
          )}

          <p className="login-powered">{t(`login.powered.${cloudProvider}`)}</p>
          <p className="login-legal">
            {t("login.legalPrefix")}{" "}
            <a
              href={PROVIDER_LEGAL_URL[cloudProvider]}
              target="_blank"
              rel="noreferrer"
            >
              {t("login.terms")}
            </a>
          </p>
        </div>
      </main>

      <footer className="login-footer">{t("login.copyright", { year: 2026 })}</footer>
    </div>
  );
}
