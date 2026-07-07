import { useEffect, useState } from "react";
import { ArrowRight, Github, LogIn } from "lucide-react";
import { fetchProviders, loginTo, USERNAME_RE, type Provider } from "../adk/identity";

function providerIcon(id: string) {
  if (id.toLowerCase() === "github") return <Github className="icon" />;
  return <LogIn className="icon" />;
}

export interface LoginPageProps {
  /** Chosen username for the no-SSO local mode. */
  onUsername: (name: string) => void;
}

export function LoginPage({ onUsername }: LoginPageProps) {
  const [providers, setProviders] = useState<Provider[] | null>(null);
  const [name, setName] = useState("");

  useEffect(() => {
    fetchProviders().then(setProviders);
  }, []);

  const valid = USERNAME_RE.test(name);
  const submit = () => {
    if (valid) onUsername(name);
  };

  return (
    <div className="login">
      <header className="login-top">
        <span className="login-brand">VeADK Web</span>
      </header>

      <main className="login-main">
        <div className="login-card">
          <h1 className="login-title">
            VeADK 提供
            <br />
            企业级 Agent 解决方案
          </h1>

          {providers === null ? null : providers.length > 0 ? (
            <>
              <p className="login-sub">登录以继续使用 VeADK Web</p>
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
        </div>
      </main>

      <footer className="login-footer">© 2026 VeADK. All rights reserved.</footer>
    </div>
  );
}
