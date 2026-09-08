import {
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
  type DragEvent,
} from "react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import { parse } from "yaml";
import { deployAgentkitProject, type DeployStage } from "../adk/client";
import {
  defaultCloudRegion,
  type CloudProvider,
} from "../adk/cloudProvider";
import {
  ProjectPreview,
  type DeployResult,
  type DeploymentTaskUpdate,
} from "../ui/ProjectPreview";
import { CodeBrowserDialog } from "../ui/CodeBrowserDialog";
import type { AgentProject, ProjectFile } from "./project";
import type { NetworkConfig } from "./types";
import { unzip, type ZipEntry } from "./skills/zip";
import { createT } from "./i18n";
import "./CodePackageCreate.css";

const MAX_PACKAGE_BYTES = 50 * 1024 * 1024;
const MAX_PROJECT_FILES = 800;
const EMPTY_PACKAGE_PROJECT: AgentProject = { name: "code_package", files: [] };

interface CodePackageCreateProps {
  onBack: () => void;
  onAgentAdded?: (agentId: string, agentName: string) => void;
  onDeploymentTaskChange?: (task: DeploymentTaskUpdate) => void;
  onDeploymentStarted?: (task: DeploymentTaskUpdate) => void;
  onDeploymentComplete?: (result: DeployResult) => void | Promise<void>;
  initialDeployRegion?: string;
  cloudProvider?: CloudProvider;
}

function packageProjectName(fileName: string): string {
  const base = fileName.replace(/\.zip$/i, "").trim();
  let name = base.replace(/[^A-Za-z0-9_]+/g, "_").replace(/^_+|_+$/g, "");
  if (!name) name = "uploaded_agent";
  if (!/^[A-Za-z_]/.test(name)) name = `agent_${name}`;
  if (name === "user") name = "uploaded_agent";
  return name.slice(0, 64);
}

type CreateTranslator = TFunction<"create">;

function defaultPackageTranslation(
  key: string,
  values?: Record<string, unknown>,
): string {
  return createT(key, values);
}

function cleanEntryPath(
  name: string,
  t: CreateTranslator | typeof defaultPackageTranslation = defaultPackageTranslation,
): string | null {
  const path = name.replace(/\\/g, "/").replace(/^\.\//, "");
  if (!path || path.endsWith("/")) return null;
  if (path.startsWith("/") || path.includes("\0")) {
    throw new Error(t("codePackage.errors.invalidPath", { name }));
  }
  const parts = path.split("/");
  if (parts.some((part) => !part || part === "." || part === "..")) {
    throw new Error(t("codePackage.errors.invalidPath", { name }));
  }
  if (parts[0] === "__MACOSX" || parts[parts.length - 1] === ".DS_Store") return null;
  return parts.join("/");
}

/** Convert ZIP entries into the text-file project shape used by AgentKit deploy. */
export function normalizePackageEntries(
  entries: ZipEntry[],
  t: CreateTranslator | typeof defaultPackageTranslation = defaultPackageTranslation,
): ProjectFile[] {
  const cleaned = entries.flatMap((entry) => {
    const path = cleanEntryPath(entry.name, t);
    return path ? [{ path, content: entry.text }] : [];
  });
  if (cleaned.length === 0) throw new Error(t("codePackage.errors.empty"));
  if (cleaned.length > MAX_PROJECT_FILES) {
    throw new Error(t("codePackage.errors.tooManyFiles", { count: MAX_PROJECT_FILES }));
  }

  const firstSegments = new Set(cleaned.map((file) => file.path.split("/")[0]));
  const hasSingleRoot =
    firstSegments.size === 1 && cleaned.every((file) => file.path.includes("/"));
  const files = hasSingleRoot
    ? cleaned.map((file) => ({ ...file, path: file.path.split("/").slice(1).join("/") }))
    : cleaned;

  const paths = new Set<string>();
  for (const file of files) {
    if (paths.has(file.path)) throw new Error(t("codePackage.errors.duplicateFile", { path: file.path }));
    paths.add(file.path);
  }
  resolvePackageEntryPoint(files, t);
  return files;
}

export function resolvePackageEntryPoint(
  files: ProjectFile[],
  t: CreateTranslator | typeof defaultPackageTranslation = defaultPackageTranslation,
): string {
  const paths = new Set(files.map((file) => file.path));
  const manifest = files.find((file) => file.path === "agentkit.yaml");
  let entryPoint = "app.py";
  if (manifest) {
    let value: unknown;
    try {
      value = parse(manifest.content);
    } catch (cause) {
      throw new Error(
        t("codePackage.errors.manifestParse", { detail: cause instanceof Error ? cause.message : String(cause) }),
      );
    }
    if (value !== null && (typeof value !== "object" || Array.isArray(value))) {
      throw new Error(t("codePackage.errors.manifestRoot"));
    }
    const common =
      value && typeof value === "object" && !Array.isArray(value)
        ? (value as Record<string, unknown>).common
        : undefined;
    if (
      common !== undefined &&
      (common === null || typeof common !== "object" || Array.isArray(common))
    ) {
      throw new Error(t("codePackage.errors.manifestCommon"));
    }
    const configured =
      common && typeof common === "object" && !Array.isArray(common)
        ? (common as Record<string, unknown>).entry_point
        : undefined;
    if (configured !== undefined) {
      if (typeof configured !== "string") {
        throw new Error(t("codePackage.errors.entryPointType"));
      }
      const cleaned = cleanEntryPath(configured, t);
      if (!cleaned) {
        throw new Error(t("codePackage.errors.entryPointInvalid"));
      }
      entryPoint = cleaned;
    }
  }
  if (!paths.has(entryPoint)) {
    if (manifest && entryPoint !== "app.py") {
      throw new Error(t("codePackage.errors.entryPointMissing", { entryPoint }));
    }
    throw new Error(
      t("codePackage.errors.defaultEntryPointMissing"),
    );
  }
  return entryPoint;
}

export function CodePackageCreate({
  onBack,
  onAgentAdded,
  onDeploymentTaskChange,
  onDeploymentStarted,
  onDeploymentComplete,
  cloudProvider = "volcengine",
  initialDeployRegion = defaultCloudRegion(cloudProvider),
}: CodePackageCreateProps) {
  const { t } = useTranslation("create");
  const inputRef = useRef<HTMLInputElement>(null);
  const loadRunRef = useRef(0);
  const [project, setProject] = useState<AgentProject | null>(null);
  const [uploadedFileName, setUploadedFileName] = useState("");
  const [browserOpen, setBrowserOpen] = useState(false);
  const [reading, setReading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState("");
  const [deployRegion, setDeployRegion] = useState(initialDeployRegion);
  const [network, setNetwork] = useState<NetworkConfig | undefined>();

  useEffect(
    () => () => {
      loadRunRef.current += 1;
    },
    [],
  );

  async function loadPackage(file: File) {
    const run = ++loadRunRef.current;
    setError("");
    if (!file.name.toLowerCase().endsWith(".zip")) {
      setError(t("codePackage.errors.invalidFormat"));
      return;
    }
    if (file.size > MAX_PACKAGE_BYTES) {
      setError(t("codePackage.errors.tooLarge"));
      return;
    }

    setReading(true);
    try {
      const entries = await unzip(new Uint8Array(await file.arrayBuffer()), {
        maxEntries: MAX_PROJECT_FILES,
        maxUncompressedBytes: MAX_PACKAGE_BYTES,
      });
      const files = normalizePackageEntries(entries, t);
      if (run !== loadRunRef.current) return;
      setUploadedFileName(file.name);
      setProject({ name: packageProjectName(file.name), files });
    } catch (cause) {
      if (run !== loadRunRef.current) return;
      setUploadedFileName("");
      setProject(null);
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      if (run === loadRunRef.current) setReading(false);
    }
  }

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.currentTarget.files?.[0];
    event.currentTarget.value = "";
    if (file) void loadPackage(file);
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    const file = event.dataTransfer.files?.[0];
    if (file) void loadPackage(file);
  }

  async function handleDeploy(
    nextProject: AgentProject,
    onStage?: (stage: DeployStage) => void,
    options?: Parameters<typeof deployAgentkitProject>[3],
  ) {
    const runtimeNetwork =
      network && network.mode !== "public"
        ? {
            mode: network.mode,
            vpc_id: network.vpcId,
            subnet_ids: network.subnetIds,
            enable_shared_internet_access: network.enableSharedInternetAccess,
          }
        : undefined;
    return deployAgentkitProject(
      nextProject.name,
      nextProject.files,
      { region: deployRegion, projectName: "default", network: runtimeNetwork },
      { ...options, onStage },
    );
  }

  return (
    <div className="package-create package-create-preview">
      <ProjectPreview
        cloudProvider={cloudProvider}
        project={project ?? EMPTY_PACKAGE_PROJECT}
        agentName={project?.name || t("codePackage.name")}
        onChange={project ? setProject : undefined}
        onDeploy={handleDeploy}
        onAgentAdded={onAgentAdded}
        onDeploymentTaskChange={onDeploymentTaskChange}
        onDeploymentStarted={onDeploymentStarted}
        onDeploymentComplete={onDeploymentComplete}
        network={network}
        onNetworkChange={setNetwork}
        deployRegion={deployRegion}
        onDeployRegionChange={setDeployRegion}
        deploymentTelemetry={{
          source: "code_package",
          createMode: "code_package",
          aiAssisted: false,
        }}
        onBack={onBack}
        backLabel={t("codePackage.back")}
        deployDisabled={!project || reading}
        deployDisabledReason={reading ? t("codePackage.reading") : !project ? t("codePackage.uploadFirst") : undefined}
        deploymentPrimaryPane={
          <section className="package-source-pane" aria-label={t("codePackage.uploadAriaLabel")}>
            <div className="package-source-label">{t("codePackage.name")}</div>
            <div
              className={`package-dropzone${dragging ? " is-dragging" : ""}${project ? " is-ready" : ""}`}
              onDragEnter={(event) => {
                event.preventDefault();
                setDragging(true);
              }}
              onDragOver={(event) => event.preventDefault()}
              onDragLeave={(event) => {
                if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
                  setDragging(false);
                }
              }}
              onDrop={handleDrop}
              onClick={() => {
                if (!reading) inputRef.current?.click();
              }}
              onKeyDown={(event) => {
                if (!reading && (event.key === "Enter" || event.key === " ")) {
                  event.preventDefault();
                  inputRef.current?.click();
                }
              }}
              role="button"
              tabIndex={reading ? -1 : 0}
              aria-label={project ? t("codePackage.reupload") : t("codePackage.upload")}
              aria-disabled={reading}
            >
              <strong>
                {reading
                  ? t("codePackage.readingEllipsis")
                  : project
                    ? uploadedFileName
                    : t("codePackage.uploadPrompt")}
              </strong>
              <span>
                {project
                  ? t("codePackage.filesRecognized", { count: project.files.length })
                  : t("codePackage.dropHint")}
              </span>
              <div className="package-upload-actions">
                {project && (
                  <button
                    type="button"
                    className="package-upload-secondary"
                    onClick={(event) => {
                      event.stopPropagation();
                      setBrowserOpen(true);
                    }}
                    onKeyDown={(event) => event.stopPropagation()}
                  >
                    {t("codePackage.viewFiles")}
                  </button>
                )}
              </div>
              <input
                ref={inputRef}
                type="file"
                accept=".zip,application/zip"
                aria-label={t("codePackage.chooseFile")}
                onChange={handleFileChange}
              />
            </div>
            {error && <div className="package-create-error" role="alert">{error}</div>}
          </section>
        }
      />
      {project && (
        <CodeBrowserDialog
          project={project}
          open={browserOpen}
          onClose={() => setBrowserOpen(false)}
          onChange={setProject}
        />
      )}
    </div>
  );
}
