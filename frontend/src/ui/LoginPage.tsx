import { useEffect, useState } from "react";
import { ArrowRight, Github, LogIn } from "lucide-react";
import type { SiteBranding } from "../adk/client";
import { fetchProviders, loginTo, USERNAME_RE, type Provider } from "../adk/identity";
import defaultSiteLogo from "../assets/volcengine.svg";
import { TextShimmer } from "./text-shimmer/TextShimmer";

function providerIcon(id: string) {
  if (id.toLowerCase() === "github") return <Github className="icon" />;
  return <LogIn className="icon" />;
}

export interface LoginPageProps {
  branding: SiteBranding;
  /** Chosen username for the no-SSO local mode. */
  onUsername: (name: string) => void;
}

export function LoginPage({ branding, onUsername }: LoginPageProps) {
  const [providers, setProviders] = useState<Provider[] | null>(null);
  const [providerError, setProviderError] = useState("");
  const [providerAttempt, setProviderAttempt] = useState(0);
  const [name, setName] = useState("");

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

  const valid = USERNAME_RE.test(name);
  const submit = () => {
    if (valid) onUsername(name);
  };

  return (
    <div className="login">
      <header className="login-top">
        <span className="login-brand">
          <img
            className="login-brand-logo"
            src={branding.logoUrl || defaultSiteLogo}
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
                重试
              </button>
            </div>
          ) : providers === null ? null : providers.length > 0 ? (
            <>
              <p className="login-sub">登录以继续使用</p>
              <div className="login-providers">
                {providers.map((p) => (
                  <button key={p.id} className="login-btn" onClick={() => loginTo(p.loginUrl)}>
                    {providerIcon(p.id)}
                    <span>使用 {p.label} 登录</span>
                  </button>
                ))}
              </div>
            </>
          ) : (
            <>
              <p className="login-sub">输入一个用户名即可开始</p>
              <form
                className="login-name"
                onSubmit={(e) => {
                  e.preventDefault();
                  submit();
                }}
              >
                <input
                  className="login-name-input"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="用户名（字母 + 数字，最多 16 位）"
                  maxLength={16}
                  autoFocus
                />
                <button
                  type="submit"
                  className="login-name-go"
                  disabled={!valid}
                  aria-label="进入"
                >
                  <ArrowRight className="icon" />
                </button>
              </form>
              {/* Always rendered so the error appearing doesn't shift the input;
                  the line's height is reserved via CSS min-height. */}
              <p className="login-hint" aria-live="polite">
                {name && !valid ? "只能包含大小写字母和数字，最多 16 位。" : ""}
              </p>
            </>
          )}

          <p className="login-legal">继续即表示你已阅读并同意服务条款与隐私政策</p>
          <p className="login-powered">火山引擎 AgentKit 提供企业级 Agent 解决方案</p>
        </div>
      </main>

      <footer className="login-footer">© 2026 VeADK. All rights reserved.</footer>
    </div>
  );
}
