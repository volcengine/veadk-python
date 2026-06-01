import { useEffect, useState } from "react";
import { Github, LogIn } from "lucide-react";
import { fetchProviders, loginTo, type Provider } from "../adk/identity";

function providerIcon(id: string) {
  if (id.toLowerCase() === "github") return <Github className="icon" />;
  return <LogIn className="icon" />;
}

export interface LoginPageProps {
  /** Fallback when the server reports no explicit providers. */
  onLogin: () => void;
}

/** Branded sign-in landing page (LobeHub-style). Renders a button per SSO
 *  provider the server has configured; clicking starts that provider's flow. */
export function LoginPage({ onLogin }: LoginPageProps) {
  const [providers, setProviders] = useState<Provider[] | null>(null);

  useEffect(() => {
    fetchProviders().then(setProviders);
  }, []);

  return (
    <div className="login">
      <header className="login-top">
        <span className="login-brand">VeADK Web</span>
      </header>

      <main className="login-main">
        <div className="login-card">
          <h1 className="login-title">
            会成长的
            <br />
            智能体伙伴
          </h1>
          <p className="login-sub">登录以继续使用 VeADK Web</p>

          <div className="login-providers">
            {providers && providers.length > 0 ? (
              providers.map((p) => (
                <button key={p.id} className="login-btn" onClick={() => loginTo(p.loginUrl)}>
                  {providerIcon(p.id)}
                  <span>使用 {p.label} 登录</span>
                </button>
              ))
            ) : (
              <button className="login-btn" onClick={onLogin}>
                <LogIn className="icon" />
                <span>登录 / 注册</span>
              </button>
            )}
          </div>

          <p className="login-legal">登录即表示你已阅读并同意服务条款与隐私政策</p>
        </div>
      </main>

      <footer className="login-footer">© 2026 VeADK. All rights reserved.</footer>
    </div>
  );
}
