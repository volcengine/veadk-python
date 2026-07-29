import {
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type DragEvent,
} from "react";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  Cloud,
  FileCheck2,
  Files,
  PackageOpen,
  ShieldCheck,
} from "lucide-react";
import { parseDocument } from "yaml";
import { CodeBrowserDialog } from "../ui/CodeBrowserDialog";
import type { AgentProject, ProjectFile } from "./project";
import { unzip, type ZipEntry } from "./skills/zip";
import "./CodePackageCreate.css";
import "./LegacyMigrationCreate.css";

const MAX_ARCHIVE_BYTES = 50 * 1024 * 1024;
const MAX_DIFY_BYTES = 5 * 1024 * 1024;
const MAX_PROJECT_FILES = 800;

type MigrationFramework =
  | "langgraph"
  | "langchain"
  | "adk"
  | "strands"
  | "agentcore"
  | "dify"
  | "any";

type InputKind = "project" | "yaml";

interface FrameworkDefinition {
  id: MigrationFramework;
  label: string;
  inputKind: InputKind;
  mode: "structured" | "sandbox";
  description: string;
  entryPlaceholder?: string;
  steps: [string, string, string];
}

const FRAMEWORKS: FrameworkDefinition[] = [
  {
    id: "langgraph",
    label: "LangGraph",
    inputKind: "project",
    mode: "structured",
    description: "保留现有 Graph 与状态定义，生成 AgentKit 服务入口和运行配置。",
    entryPlaceholder: "graph.py:agent",
    steps: ["解析 Graph 与状态", "生成 AgentKit 适配层", "校验流式事件与入口"],
  },
  {
    id: "langchain",
    label: "LangChain",
    inputKind: "project",
    mode: "structured",
    description: "包装现有 Agent 或 Runnable，并补齐 AgentKit 的会话与服务接口。",
    entryPlaceholder: "agent.py:agent",
    steps: ["识别 Agent / Runnable", "生成调用适配层", "校验输入与响应"],
  },
  {
    id: "adk",
    label: "Google ADK",
    inputKind: "project",
    mode: "structured",
    description: "复用现有 root_agent，转换为可由 AgentKit Runtime 托管的工程。",
    entryPlaceholder: "agent.py:root_agent",
    steps: ["识别 root_agent", "生成 AgentKit 服务层", "校验依赖与启动入口"],
  },
  {
    id: "strands",
    label: "Strands",
    inputKind: "project",
    mode: "structured",
    description: "包装 Strands Agent 构建函数，生成 AgentKit Runtime 所需结构。",
    entryPlaceholder: "agent.py:build_agent",
    steps: ["定位 Agent 构建函数", "生成运行适配层", "校验模型与工具依赖"],
  },
  {
    id: "agentcore",
    label: "AgentCore",
    inputKind: "project",
    mode: "structured",
    description: "迁移 AgentCore 应用入口，保留原有业务逻辑并补齐 AgentKit 配置。",
    entryPlaceholder: "deploy/agentcore/app.py:app",
    steps: ["解析应用入口", "生成 AgentKit 工程", "校验模型与环境变量"],
  },
  {
    id: "dify",
    label: "Dify",
    inputKind: "yaml",
    mode: "sandbox",
    description: "读取 Dify DSL，在隔离的远程 Sandbox 中分析节点并生成 AgentKit 工程。",
    steps: ["解析 Dify YAML", "启动远程 Sandbox", "生成并回传 AgentKit 工程"],
  },
  {
    id: "any",
    label: "通用项目",
    inputKind: "project",
    mode: "sandbox",
    description: "对其他 Agent 工程进行 Agentic 分析，在远程 Sandbox 中完成迁移。",
    steps: ["扫描项目结构", "启动远程 Sandbox", "生成并回传 AgentKit 工程"],
  },
];

interface LegacyMigrationCreateProps {
  onBack: () => void;
}

interface UploadedSource {
  kind: InputKind;
  name: string;
  project?: AgentProject;
  yaml?: string;
}

function cleanProjectEntries(entries: ZipEntry[]): ProjectFile[] {
  const cleaned = entries.flatMap((entry) => {
    const path = entry.name.replace(/\\/g, "/").replace(/^\.\//, "");
    if (!path || path.endsWith("/") || path.startsWith("/") || path.includes("\0")) return [];
    const parts = path.split("/");
    if (parts.some((part) => !part || part === "." || part === "..")) return [];
    if (parts[0] === "__MACOSX" || parts[parts.length - 1] === ".DS_Store") return [];
    return [{ path, content: entry.text }];
  });
  if (cleaned.length === 0) throw new Error("压缩包中没有可迁移的文件。");
  const roots = new Set(cleaned.map((file) => file.path.split("/")[0]));
  return roots.size === 1 && cleaned.every((file) => file.path.includes("/"))
    ? cleaned.map((file) => ({ ...file, path: file.path.split("/").slice(1).join("/") }))
    : cleaned;
}

function projectName(fileName: string): string {
  return fileName.replace(/\.zip$/i, "").replace(/[^A-Za-z0-9_-]+/g, "-") || "migrated-agent";
}

export function LegacyMigrationCreate({ onBack }: LegacyMigrationCreateProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [frameworkId, setFrameworkId] = useState<MigrationFramework>("langgraph");
  const [source, setSource] = useState<UploadedSource | null>(null);
  const [entry, setEntry] = useState("graph.py:agent");
  const [dragging, setDragging] = useState(false);
  const [reading, setReading] = useState(false);
  const [error, setError] = useState("");
  const [browserOpen, setBrowserOpen] = useState(false);
  const [checked, setChecked] = useState(false);
  const framework = useMemo(
    () => FRAMEWORKS.find((item) => item.id === frameworkId) ?? FRAMEWORKS[0],
    [frameworkId],
  );
  const activeSource = source?.kind === framework.inputKind ? source : null;
  const ready = Boolean(activeSource && (framework.mode === "sandbox" || entry.trim()));

  async function loadSource(file: File) {
    setError("");
    setChecked(false);
    const expectsYaml = framework.inputKind === "yaml";
    if (expectsYaml && !/\.ya?ml$/i.test(file.name)) {
      setError("Dify 迁移请选择 .yaml 或 .yml 格式的 DSL 文件。");
      return;
    }
    if (!expectsYaml && !file.name.toLowerCase().endsWith(".zip")) {
      setError("项目工程请选择 .zip 格式的压缩包。");
      return;
    }
    if (file.size > (expectsYaml ? MAX_DIFY_BYTES : MAX_ARCHIVE_BYTES)) {
      setError(expectsYaml ? "Dify YAML 不能超过 5 MB。" : "项目工程不能超过 50 MB。");
      return;
    }

    setReading(true);
    try {
      if (expectsYaml) {
        const yaml = await file.text();
        const document = parseDocument(yaml);
        if (document.errors.length > 0 || !yaml.trim()) {
          throw new Error("YAML 内容无法解析，请检查 Dify DSL。");
        }
        setSource({ kind: "yaml", name: file.name, yaml });
      } else {
        const entries = await unzip(new Uint8Array(await file.arrayBuffer()), {
          maxEntries: MAX_PROJECT_FILES,
          maxUncompressedBytes: MAX_ARCHIVE_BYTES,
        });
        const files = cleanProjectEntries(entries);
        setSource({
          kind: "project",
          name: file.name,
          project: { name: projectName(file.name), files },
        });
      }
    } catch (cause) {
      setSource(null);
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setReading(false);
    }
  }

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.currentTarget.files?.[0];
    event.currentTarget.value = "";
    if (file) void loadSource(file);
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    const file = event.dataTransfer.files?.[0];
    if (file) void loadSource(file);
  }

  const sourceDetail = activeSource?.project
    ? `已识别 ${activeSource.project.files.length} 个文件，点击可重新上传`
    : activeSource?.yaml
      ? "Dify DSL 已通过 YAML 格式检查，点击可重新上传"
      : framework.inputKind === "yaml"
        ? "点击或拖拽上传 Dify DSL，支持 .yaml / .yml，最大 5 MB"
        : "点击或拖拽上传完整项目，支持 .zip 格式，最大 50 MB";

  return (
    <div className="migration-create">
      <div className="migration-container">
        <button type="button" className="migration-back" onClick={onBack}>
          <ArrowLeft aria-hidden />
          返回创建方式
        </button>

        <header className="migration-heading">
          <div>
            <p className="migration-kicker">AgentKit CLI Migration</p>
            <h1>从存量系统迁移</h1>
            <p>选择原项目框架，保留已有业务逻辑并转换为 AgentKit 工程。</p>
          </div>
          <span className="migration-support-count">支持 7 种来源</span>
        </header>

        <div className="migration-tabs" role="tablist" aria-label="迁移框架">
          {FRAMEWORKS.map((item) => (
            <button
              key={item.id}
              type="button"
              role="tab"
              aria-selected={framework.id === item.id}
              className={framework.id === item.id ? "is-active" : ""}
              onClick={() => {
                setFrameworkId(item.id);
                setEntry(item.entryPlaceholder ?? "");
                setChecked(false);
                setError("");
              }}
            >
              {item.label}
            </button>
          ))}
        </div>

        <section className="migration-workspace" aria-label={`${framework.label} 迁移配置`}>
          <div className="migration-source">
            <div className="migration-section-title">
              <span>1</span>
              <div>
                <h2>{framework.inputKind === "yaml" ? "上传 Dify DSL" : "上传项目工程"}</h2>
                <p>{framework.inputKind === "yaml" ? "导出应用 DSL 后直接上传 YAML" : "请保留项目源码与依赖文件的完整目录结构"}</p>
              </div>
            </div>

            <div
              className={`package-dropzone migration-dropzone${dragging ? " is-dragging" : ""}${activeSource ? " is-ready" : ""}`}
              onDragEnter={(event) => {
                event.preventDefault();
                setDragging(true);
              }}
              onDragOver={(event) => event.preventDefault()}
              onDragLeave={(event) => {
                if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDragging(false);
              }}
              onDrop={handleDrop}
              onClick={() => !reading && inputRef.current?.click()}
              onKeyDown={(event) => {
                if (!reading && (event.key === "Enter" || event.key === " ")) {
                  event.preventDefault();
                  inputRef.current?.click();
                }
              }}
              role="button"
              tabIndex={reading ? -1 : 0}
              aria-label={activeSource ? "重新上传迁移来源" : "上传迁移来源"}
              aria-disabled={reading}
            >
              <span className="migration-upload-icon">
                {activeSource ? <FileCheck2 aria-hidden /> : <PackageOpen aria-hidden />}
              </span>
              <strong>{reading ? "正在读取…" : activeSource?.name ?? (framework.inputKind === "yaml" ? "上传 YAML" : "上传项目 ZIP")}</strong>
              <span>{sourceDetail}</span>
              {activeSource?.project && (
                <div className="package-upload-actions">
                  <button
                    type="button"
                    className="package-upload-secondary"
                    onClick={(event) => {
                      event.stopPropagation();
                      setBrowserOpen(true);
                    }}
                  >
                    查看文件
                  </button>
                </div>
              )}
              <input
                ref={inputRef}
                type="file"
                accept={framework.inputKind === "yaml" ? ".yaml,.yml,text/yaml" : ".zip,application/zip"}
                aria-label="选择迁移来源文件"
                onChange={handleFileChange}
              />
            </div>
            {error && <div className="package-create-error" role="alert">{error}</div>}

            {framework.mode === "structured" && (
              <label className="migration-entry-field">
                <span>入口对象</span>
                <input
                  value={entry}
                  onChange={(event) => {
                    setEntry(event.target.value);
                    setChecked(false);
                  }}
                  placeholder={framework.entryPlaceholder}
                  aria-label="迁移入口对象"
                />
                <small>填写 Python 文件与对象名，例如 {framework.entryPlaceholder}</small>
              </label>
            )}
          </div>

          <aside className="migration-plan">
            <div className="migration-plan-head">
              <span>{framework.mode === "sandbox" ? <Cloud aria-hidden /> : <Files aria-hidden />}</span>
              <div>
                <p>{framework.mode === "sandbox" ? "Agentic 迁移" : "结构化迁移"}</p>
                <h2>{framework.label}</h2>
              </div>
            </div>
            <p className="migration-description">{framework.description}</p>

            <div className="migration-flow" aria-label="迁移流程">
              {framework.steps.map((step, index) => (
                <div key={step} className="migration-flow-step">
                  <span>{index + 1}</span>
                  <p>{step}</p>
                  {index < framework.steps.length - 1 && <ArrowRight aria-hidden />}
                </div>
              ))}
            </div>

            {framework.mode === "sandbox" ? (
              <div className="migration-sandbox-note">
                <ShieldCheck aria-hidden />
                <div>
                  <strong>隔离环境执行</strong>
                  <p>迁移任务将在临时远程 Sandbox 中运行，完成后回传生成工程，环境随任务结束释放。</p>
                </div>
              </div>
            ) : (
              <div className="migration-adapter-note">
                <Check aria-hidden />
                <span>保留原工程，仅新增 AgentKit 适配与运行配置</span>
              </div>
            )}

            <button
              type="button"
              className="migration-check"
              disabled={!ready || reading}
              onClick={() => setChecked(true)}
            >
              {checked ? "迁移配置已就绪" : "检查迁移配置"}
            </button>
            <p className="migration-check-hint">
              {checked
                ? framework.mode === "sandbox"
                  ? "下一步将创建远程 Sandbox 迁移任务。"
                  : "下一步将生成 AgentKit 适配工程并执行导入校验。"
                : "上传来源并完成必填项后检查配置。"}
            </p>
          </aside>
        </section>
      </div>

      {activeSource?.project && (
        <CodeBrowserDialog
          project={activeSource.project}
          open={browserOpen}
          onClose={() => setBrowserOpen(false)}
          onChange={(project) => setSource({ ...activeSource, project })}
        />
      )}
    </div>
  );
}
