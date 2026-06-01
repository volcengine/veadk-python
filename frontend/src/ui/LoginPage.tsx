import { ArrowRight } from "lucide-react";

export interface LoginPageProps {
  onLogin: () => void;
}

/** Branded sign-in landing page (LobeHub-style). The single button starts the
 *  OAuth2 flow; the identity provider presents the actual login options. */
export function LoginPage({ onLogin }: LoginPageProps) {
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

          <button className="login-btn" onClick={onLogin}>
            <span>登录 / 注册</span>
            <ArrowRight className="icon" />
          </button>

          <p className="login-legal">登录即表示你已阅读并同意服务条款与隐私政策</p>
        </div>
      </main>

      <footer className="login-footer">© {`${2026}`} VeADK. All rights reserved.</footer>
    </div>
  );
}
