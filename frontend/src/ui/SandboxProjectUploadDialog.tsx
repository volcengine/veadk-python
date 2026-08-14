import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Check, Copy, RefreshCw, X } from "lucide-react";
import {
  CODEX_PROJECT_UPLOAD_AUTHORIZATION_TTL_SECONDS,
  sandboxClient,
  type CodexProjectUploadAuthorization,
} from "../adk/sandbox";
import "./SandboxProjectUploadDialog.css";

type CopyTarget = "install" | "upload" | "";

export interface SandboxProjectUploadDialogProps {
  open: boolean;
  onClose: () => void;
  onRefreshAgents: () => void;
}

function trimStudioUrl(value: string): string {
  return value.trim().replace(/\/+$/, "") || window.location.origin;
}

function codexUploadPrompt(authorization: CodexProjectUploadAuthorization): string {
  const studioUrl = trimStudioUrl(authorization.studioUrl);
  return [
    "请使用 codex-sandbox-upload skill 将当前项目上传到 Studio 云端 Codex Sandbox。",
    "",
    "参数：",
    "- repo: 当前工作目录",
    `- studio_url: ${studioUrl}`,
    `- authorization_code: ${authorization.authorizationCode}`,
    "",
    "上传完成后，请告诉我远端项目目录和恢复结果。",
  ].join("\n");
}

const INSTALL_COMMAND = [
  "codex skill install codex-sandbox-upload",
  'test -x "$HOME/.codex/skills/codex-sandbox-upload/scripts/upload_current_dir.sh"',
].join("\n");

function authorizationValidityLabel(): string {
  const hours = CODEX_PROJECT_UPLOAD_AUTHORIZATION_TTL_SECONDS / 3600;
  return Number.isInteger(hours) ? `${hours} 小时` : "1 小时";
}

export function SandboxProjectUploadDialog({
  open,
  onClose,
  onRefreshAgents,
}: SandboxProjectUploadDialogProps) {
  const dialogRef = useRef<HTMLElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const onCloseRef = useRef(onClose);
  const requestRef = useRef(0);
  const copyTimerRef = useRef<number | undefined>(undefined);
  const [authorization, setAuthorization] =
    useState<CodexProjectUploadAuthorization | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [copyTarget, setCopyTarget] = useState<CopyTarget>("");
  onCloseRef.current = onClose;

  const codexPrompt = useMemo(
    () => authorization ? codexUploadPrompt(authorization) : "",
    [authorization],
  );

  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    const requestId = ++requestRef.current;
    setAuthorization(null);
    setError("");
    setCopyTarget("");
    setLoading(true);
    void sandboxClient
      .createCodexProjectUploadAuthorization({ signal: controller.signal })
      .then((value) => {
        if (requestRef.current === requestId) setAuthorization(value);
      })
      .catch((cause) => {
        if ((cause as Error)?.name === "AbortError") return;
        if (requestRef.current === requestId) {
          setError(cause instanceof Error ? cause.message : String(cause));
        }
      })
      .finally(() => {
        if (requestRef.current === requestId) setLoading(false);
      });
    return () => {
      controller.abort();
    };
  }, [open]);

  useEffect(() => () => {
    if (copyTimerRef.current !== undefined) {
      window.clearTimeout(copyTimerRef.current);
    }
  }, []);

  useEffect(() => {
    if (!open) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const focusFrame = window.requestAnimationFrame(() => closeRef.current?.focus());
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onCloseRef.current();
        return;
      }
      if (event.key !== "Tab") return;
      const controls = dialogRef.current?.querySelectorAll<HTMLElement>(
        'button:not(:disabled), [tabindex]:not([tabindex="-1"])',
      );
      if (!controls?.length) return;
      const first = controls[0];
      const last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.cancelAnimationFrame(focusFrame);
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  if (!open) return null;

  async function copy(value: string, target: CopyTarget) {
    if (!value || copyTarget) return;
    setError("");
    setCopyTarget(target);
    try {
      if (!navigator.clipboard?.writeText) {
        throw new Error("当前浏览器不支持写入剪贴板。");
      }
      await navigator.clipboard.writeText(value);
      if (copyTimerRef.current !== undefined) {
        window.clearTimeout(copyTimerRef.current);
      }
      copyTimerRef.current = window.setTimeout(() => {
        setCopyTarget((current) => current === target ? "" : current);
        copyTimerRef.current = undefined;
      }, 1400);
    } catch (cause) {
      setCopyTarget("");
      setError(cause instanceof Error ? cause.message : String(cause));
    }
  }

  return createPortal(
    <div
      className="sandbox-project-upload-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section
        ref={dialogRef}
        className="sandbox-project-upload-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="sandbox-project-upload-title"
      >
        <header className="sandbox-project-upload-head">
          <div>
            <h2 id="sandbox-project-upload-title">迁移本地 Codex 项目</h2>
            <p>复制 Prompt 给本地 Codex，Codex 会调用上传 Skill 创建云端智能体。</p>
          </div>
          <button
            ref={closeRef}
            type="button"
            className="sandbox-project-upload-close"
            onClick={onClose}
            aria-label="关闭本地迁移引导"
          >
            <X />
          </button>
        </header>

        <div className="sandbox-project-upload-body">
          {error ? (
            <div className="sandbox-project-upload-error" role="alert">
              <span>{error}</span>
              <button
                type="button"
                onClick={() => {
                  setError("");
                  setAuthorization(null);
                  requestRef.current += 1;
                  setLoading(true);
                  void sandboxClient
                    .createCodexProjectUploadAuthorization()
                    .then(setAuthorization)
                    .catch((cause) =>
                      setError(cause instanceof Error ? cause.message : String(cause))
                    )
                    .finally(() => setLoading(false));
                }}
              >
                <RefreshCw />
                重试
              </button>
            </div>
          ) : null}

          <ol className="sandbox-project-upload-steps">
            <li>
              <span>1</span>
              <div>
                <strong>安装或更新上传 Skill</strong>
                <p>已安装 <code>codex-sandbox-upload</code> 时可跳过。</p>
              </div>
            </li>
            <li>
              <span>2</span>
              <div>
                <strong>把 Prompt 交给本地 Codex</strong>
                <p>Codex 会使用上传 Skill 迁移当前项目，完成后可刷新列表查看。</p>
              </div>
            </li>
          </ol>

          <section className="sandbox-project-upload-command">
            <div className="sandbox-project-upload-command-head">
              <span>安装 Skill</span>
              <button
                type="button"
                onClick={() => void copy(INSTALL_COMMAND, "install")}
                disabled={copyTarget !== ""}
              >
                {copyTarget === "install" ? <Check /> : <Copy />}
                {copyTarget === "install" ? "已复制" : "复制"}
              </button>
            </div>
            <pre tabIndex={0}><code>{INSTALL_COMMAND}</code></pre>
          </section>

          <section className="sandbox-project-upload-command">
            <div className="sandbox-project-upload-command-head">
              <div>
                <span>上传项目</span>
                <p>这是给本地 Codex 的 Prompt，复制后粘贴给 Codex 执行。</p>
              </div>
              <button
                type="button"
                onClick={() => void copy(codexPrompt, "upload")}
                disabled={!codexPrompt || loading || copyTarget !== ""}
              >
                {copyTarget === "upload" ? <Check /> : <Copy />}
                {copyTarget === "upload" ? "已复制" : "复制"}
              </button>
            </div>
            {loading ? (
              <div className="sandbox-project-upload-loading" role="status">
                <i aria-hidden="true" />正在生成授权码
              </div>
            ) : codexPrompt ? (
              <pre tabIndex={0}><code>{codexPrompt}</code></pre>
            ) : (
              <div className="sandbox-project-upload-loading">授权码尚未生成。</div>
            )}
          </section>

          {authorization ? (
            <dl className="sandbox-project-upload-meta">
              <div>
                <dt>Studio 地址</dt>
                <dd>{trimStudioUrl(authorization.studioUrl)}</dd>
              </div>
              <div>
                <dt>授权有效期</dt>
                <dd>{authorizationValidityLabel()}</dd>
              </div>
            </dl>
          ) : null}
        </div>

        <footer className="sandbox-project-upload-actions">
          <button type="button" onClick={onRefreshAgents}>
            刷新列表
          </button>
          <button type="button" className="is-primary" onClick={onClose}>
            完成
          </button>
        </footer>
      </section>
    </div>,
    document.body,
  );
}
