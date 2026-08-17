import { lazy, Suspense, useEffect, useId, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Badge } from "@openai/apps-sdk-ui/components/Badge";
import { Button } from "@openai/apps-sdk-ui/components/Button";
import { Minus, PlusSm12px } from "@openai/apps-sdk-ui/components/Icon";

import feishuLogo from "../assets/feishu-logo.svg";
import pandocLogo from "../assets/pandoc-logo.svg";
import {
  MAX_CLOUD_DOCKERFILE_LENGTH,
  type CloudCliToolId,
  type CloudEnvironmentConfig,
} from "../create/types";
import type { CloudProvider } from "../adk/cloudProvider";
import { buildCloudEnvironmentDockerfile } from "./cloudEnvironmentDockerfile";
import {
  CloseCloudEnvironmentIcon,
  EditCloudEnvironmentIcon,
} from "./icons/CloudCliToolIcon";
import { GitHubLogo } from "./GitHubLogo";
import { StudioConfirmDialog } from "./StudioConfirmDialog";
import "./CloudEnvironmentConfigurator.css";

const CodeEditor = lazy(() => import("./CodeEditor"));

const CLOUD_CLI_TOOLS: Array<{
  id: CloudCliToolId;
  category: "productivity" | "development";
  name: string;
  description: string;
}> = [
  {
    id: "lark-cli",
    category: "productivity",
    name: "Lark CLI",
    description: "在云端调用飞书开放平台开发与管理命令。",
  },
  {
    id: "github-cli",
    category: "development",
    name: "GitHub CLI",
    description: "在云端使用 GitHub 仓库、Issue 与 Pull Request 命令。",
  },
  {
    id: "pandoc",
    category: "productivity",
    name: "Pandoc",
    description: "转换 Markdown、HTML、Word 等文档格式。",
  },
];

const CLOUD_CLI_TOOL_CATEGORIES = [
  { id: "productivity", label: "效率" },
  { id: "development", label: "研发" },
] as const;

interface CloudEnvironmentConfiguratorProps {
  cloudProvider: CloudProvider;
  value: CloudEnvironmentConfig;
  onChange: (value: CloudEnvironmentConfig) => void;
  editorOpen: boolean;
  onEditorOpenChange: (open: boolean) => void;
  disabled?: boolean;
}

interface CloudEnvironmentAdvancedTriggerProps {
  customized: boolean;
  disabled?: boolean;
  onClick: () => void;
}

export function CloudEnvironmentAdvancedTrigger({
  customized,
  disabled = false,
  onClick,
}: CloudEnvironmentAdvancedTriggerProps) {
  return (
    <button
      type="button"
      className="cloud-env-footer-trigger"
      disabled={disabled}
      onClick={onClick}
    >
      <span className="cloud-env-footer-trigger-icon" aria-hidden="true">
        <EditCloudEnvironmentIcon />
      </span>
      <span className="cloud-env-footer-trigger-copy">
        <span>高阶配置</span>
        <small>编辑云端构建使用的 Dockerfile</small>
      </span>
      <Badge
        className="cloud-env-footer-trigger-badge"
        color={customized ? "info" : "secondary"}
        variant="soft"
        size="sm"
      >
        {customized ? "已自定义" : "自动生成"}
      </Badge>
      <EditCloudEnvironmentIcon className="cloud-env-footer-trigger-action" />
    </button>
  );
}

export function CloudEnvironmentConfigurator({
  cloudProvider,
  value,
  onChange,
  editorOpen,
  onEditorOpenChange,
  disabled = false,
}: CloudEnvironmentConfiguratorProps) {
  const providerName = cloudProvider === "byteplus" ? "BytePlus" : "火山引擎";
  const editorTitleId = useId();
  const editorDescriptionId = useId();
  const editorErrorId = useId();
  const [resetConfirmOpen, setResetConfirmOpen] = useState(false);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const generatedDockerfile = useMemo(
    () => buildCloudEnvironmentDockerfile(cloudProvider, value.cliTools),
    [cloudProvider, value.cliTools],
  );
  const customDockerfile = value.dockerfile;
  const dockerfile = customDockerfile ?? generatedDockerfile;
  const dockerfileError =
    customDockerfile !== undefined && !customDockerfile.trim()
      ? "Dockerfile 不能为空。请输入有效内容，或恢复自动生成。"
      : customDockerfile !== undefined &&
          customDockerfile.length > MAX_CLOUD_DOCKERFILE_LENGTH
        ? "Dockerfile 不能超过 64 KiB。请精简内容后重试。"
        : "";

  const toggleTool = (toolId: CloudCliToolId, checked: boolean) => {
    const selected = new Set(value.cliTools);
    if (checked) selected.add(toolId);
    else selected.delete(toolId);
    onChange({
      ...value,
      cliTools: CLOUD_CLI_TOOLS.map((tool) => tool.id).filter((id) =>
        selected.has(id),
      ),
    });
  };

  const updateDockerfile = (nextDockerfile: string) => {
    onChange({
      ...value,
      ...(nextDockerfile === generatedDockerfile
        ? { dockerfile: undefined }
        : { dockerfile: nextDockerfile }),
    });
  };

  const resetDockerfile = () => {
    onChange({ ...value, dockerfile: undefined });
    setResetConfirmOpen(false);
  };

  useEffect(() => {
    if (!editorOpen) return;
    const previousOverflow = document.body.style.overflow;
    const previousFocus =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    document.body.style.overflow = "hidden";
    closeButtonRef.current?.focus();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !resetConfirmOpen) {
        onEditorOpenChange(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleKeyDown);
      if (previousFocus?.isConnected) previousFocus.focus();
    };
  }, [editorOpen, onEditorOpenChange, resetConfirmOpen]);

  return (
    <>
      <section
        className="cloud-env-config"
        aria-label="云上环境工具配置"
      >
        <div className="cloud-env-categories">
          {CLOUD_CLI_TOOL_CATEGORIES.map((category) => (
            <section
              key={category.id}
              className="cloud-env-category"
              aria-labelledby={`cloud-env-category-${category.id}`}
            >
              <h2 id={`cloud-env-category-${category.id}`}>
                {category.label}
              </h2>
              <div className="cloud-env-tool-list">
                {CLOUD_CLI_TOOLS.filter(
                  (tool) => tool.category === category.id,
                ).map((tool) => {
                  const checked = value.cliTools.includes(tool.id);
                  return (
                    <div
                      key={tool.id}
                      className={`cloud-env-tool${checked ? " is-selected" : ""}`}
                    >
                      <span className="cloud-env-tool-icon">
                        {tool.id === "lark-cli" ? (
                          <img src={feishuLogo} alt="" aria-hidden="true" />
                        ) : tool.id === "github-cli" ? (
                          <GitHubLogo />
                        ) : (
                          <img src={pandocLogo} alt="" aria-hidden="true" />
                        )}
                      </span>
                      <span className="cloud-env-tool-content">
                        <strong>{tool.name}</strong>
                        <span className="cloud-env-tool-description">
                          {tool.description}
                        </span>
                      </span>
                      <Button
                        type="button"
                        className="cloud-env-tool-action"
                        color="secondary"
                        variant="ghost"
                        size="sm"
                        iconSize="sm"
                        uniform
                        aria-label={
                          checked ? `移除 ${tool.name}` : `安装 ${tool.name}`
                        }
                        aria-pressed={checked}
                        disabled={disabled}
                        onClick={() => toggleTool(tool.id, !checked)}
                      >
                        {checked ? (
                          <Minus />
                        ) : (
                          <PlusSm12px />
                        )}
                      </Button>
                    </div>
                  );
                })}
              </div>
            </section>
          ))}
        </div>

      </section>
      {editorOpen &&
        createPortal(
          <div
            className="cloud-env-dialog-backdrop"
            onMouseDown={(event) => {
              if (event.target === event.currentTarget && !resetConfirmOpen) {
                onEditorOpenChange(false);
              }
            }}
          >
            <section
              className="cloud-env-dialog"
              role="dialog"
              aria-modal="true"
              aria-labelledby={editorTitleId}
              aria-describedby={editorDescriptionId}
            >
              <header className="cloud-env-dialog-header">
                <div>
                  <h2 id={editorTitleId}>编辑 Dockerfile</h2>
                  <p id={editorDescriptionId}>
                    {providerName} AgentKit Runtime 云端构建配置
                  </p>
                </div>
                <div className="cloud-env-dialog-header-actions">
                  <Badge
                    color={customDockerfile === undefined ? "secondary" : "info"}
                    variant="soft"
                    size="sm"
                  >
                    {customDockerfile === undefined ? "自动生成" : "已自定义"}
                  </Badge>
                  <button
                    ref={closeButtonRef}
                    type="button"
                    className="cloud-env-dialog-close"
                    aria-label="关闭 Dockerfile 编辑器"
                    onClick={() => onEditorOpenChange(false)}
                  >
                    <CloseCloudEnvironmentIcon />
                  </button>
                </div>
              </header>
              <div className="cloud-env-dialog-body">
                <div className="cloud-env-dialog-toolbar">
                  <p>请勿在 Dockerfile 中写入访问密钥或其他凭据。</p>
                  {customDockerfile !== undefined && (
                    <Button
                      type="button"
                      color="secondary"
                      variant="ghost"
                      size="sm"
                      pill={false}
                      disabled={disabled}
                      onClick={() => setResetConfirmOpen(true)}
                    >
                      恢复自动生成
                    </Button>
                  )}
                </div>
                {customDockerfile !== undefined && (
                  <p className="cloud-env-custom-notice" role="status">
                    当前使用自定义内容。工具选择变化不会覆盖您的修改。
                  </p>
                )}
                <div
                  className={`cloud-env-editor${dockerfileError ? " is-invalid" : ""}`}
                  role="group"
                  aria-label="Dockerfile 编辑器"
                  aria-invalid={!!dockerfileError || undefined}
                  aria-describedby={dockerfileError ? editorErrorId : undefined}
                >
                  <Suspense fallback={<div className="cloud-env-editor-loading">正在加载编辑器...</div>}>
                    <CodeEditor
                      value={dockerfile}
                      path="Dockerfile"
                      readOnly={disabled}
                      onChange={updateDockerfile}
                    />
                  </Suspense>
                </div>
                {dockerfileError && (
                  <p id={editorErrorId} className="cloud-env-editor-error" role="alert">
                    {dockerfileError}
                  </p>
                )}
              </div>
              <footer className="cloud-env-dialog-footer">
                <Button
                  type="button"
                  color="primary"
                  variant="solid"
                  size="sm"
                  onClick={() => onEditorOpenChange(false)}
                >
                  完成
                </Button>
              </footer>
            </section>
          </div>,
          document.body,
        )}
      {resetConfirmOpen && (
        <StudioConfirmDialog
          title="恢复自动生成？"
          description="当前自定义内容将被替换为根据云厂商和工具选择生成的 Dockerfile。"
          confirmLabel="恢复自动生成"
          closeLabel="关闭恢复 Dockerfile 确认"
          onCancel={() => setResetConfirmOpen(false)}
          onConfirm={resetDockerfile}
        />
      )}
    </>
  );
}
