import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { createServer } from "vite";

const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const sidebarSource = readFileSync(new URL("../src/ui/Sidebar.tsx", import.meta.url), "utf8");
const environmentSource = readFileSync(
  new URL("../src/ui/EnvironmentCenter.tsx", import.meta.url),
  "utf8",
);
const environmentStyles = readFileSync(
  new URL("../src/ui/EnvironmentCenter.css", import.meta.url),
  "utf8",
);
const resourceCollectionStyles = readFileSync(
  new URL("../src/ui/ResourceCollection.css", import.meta.url),
  "utf8",
);
const dockerfileUploadSource = readFileSync(
  new URL("../src/ui/environmentDockerfileUpload.ts", import.meta.url),
  "utf8",
);
const clientSource = readFileSync(
  new URL("../src/adk/client.ts", import.meta.url),
  "utf8",
);
const resourceCardSource = readFileSync(
  new URL("../src/ui/LibraryResourceCard.tsx", import.meta.url),
  "utf8",
);
const packageOptionSource = readFileSync(
  new URL("../src/ui/StudioPackageOption.tsx", import.meta.url),
  "utf8",
);
const packageOptionStyles = readFileSync(
  new URL("../src/ui/StudioPackageOption.css", import.meta.url),
  "utf8",
);
const deploymentResourcesSource = readFileSync(
  new URL("../src/ui/DeploymentResources.tsx", import.meta.url),
  "utf8",
);
const buildProgressSource = readFileSync(
  new URL("../src/ui/StudioBuildProgress.tsx", import.meta.url),
  "utf8",
);
const buildProgressStyles = readFileSync(
  new URL("../src/ui/StudioBuildProgress.css", import.meta.url),
  "utf8",
);
const buildLogSource = readFileSync(
  new URL("../src/ui/studioBuildLog.ts", import.meta.url),
  "utf8",
);
const manifestSource = readFileSync(
  new URL("../src/ui/environmentManifest.ts", import.meta.url),
  "utf8",
);
const environmentModelSource = readFileSync(
  new URL("../src/ui/environmentModel.ts", import.meta.url),
  "utf8",
);

test("keeps Environment available without a standalone sidebar item", () => {
  assert.doesNotMatch(sidebarSource, /onEnvironment: \(\) => void/);
  assert.doesNotMatch(sidebarSource, /onClick=\{onEnvironment\}/);
  assert.doesNotMatch(sidebarSource, /aria-label="环境"/);
  assert.match(appSource, /import \{ EnvironmentCenter \}/);
  assert.match(appSource, /environmentView\s*\? "environments"/);
  assert.match(appSource, /environmentView \? \([\s\S]*?<EnvironmentCenter cloudProvider=\{cloudProvider\} \/>/);
});

test("uses Apps SDK UI controls and shared Studio patterns", () => {
  assert.match(environmentSource, /@openai\/apps-sdk-ui\/components\/Button/);
  assert.doesNotMatch(environmentSource, /@openai\/apps-sdk-ui\/components\/Checkbox/);
  assert.match(environmentSource, /@openai\/apps-sdk-ui\/components\/Input/);
  assert.match(environmentSource, /@openai\/apps-sdk-ui\/components\/Select/);
  assert.match(environmentSource, /@openai\/apps-sdk-ui\/components\/Textarea/);
  assert.match(environmentSource, /<ResourcePageShell className="environment-center"/);
  assert.match(environmentSource, /<ResourcePageHeader/);
  assert.match(environmentSource, /<ResourceToolbar className="environment-toolbar">/);
  assert.match(environmentSource, /<ResourceSearch/);
  assert.match(environmentSource, /<ResourceResults/);
  assert.match(environmentSource, /<ResourceGrid>/);
  assert.match(environmentSource, /<ResourceCreateCard/);
  assert.match(environmentSource, /<LibraryResourceCard/);
  assert.match(environmentSource, /<StudioPackageOption/);
  assert.doesNotMatch(environmentSource, /自定义环境编辑内容/);
  assert.doesNotMatch(environmentSource, /自动生成<\/Badge>/);
  assert.match(resourceCardSource, /<ResourceCardRevealAction/);
  assert.match(packageOptionSource, /<button[\s\S]*?aria-pressed=\{selected\}[\s\S]*?onClick=\{\(\) => onChange\(!selected\)\}/);
  assert.match(packageOptionStyles, /min-height: 54px/);
  assert.match(packageOptionStyles, /\.studio-package-option\.is-selected[\s\S]*?border-color: transparent[\s\S]*?background: hsl\(var\(--muted\)/);
});

test("covers environment categories, editor feedback, and responsive layout", () => {
  assert.match(environmentSource, /aria-label=\{t\("environmentCenter\.baseConfiguration"\)\}/);
  assert.match(environmentModelSource, /AIO Sandbox/);
  assert.match(environmentModelSource, /Ubuntu/);
  assert.match(environmentSource, /<span>\{t\("environmentCenter\.baseEnvironment"\)\}<RequiredMark \/><\/span>[\s\S]*?<Select/);
  assert.match(environmentSource, /<span>\{t\("environmentCenter\.pythonVersion"\)\}<RequiredMark \/><\/span>[\s\S]*?<Select/);
  assert.doesNotMatch(environmentSource, />执行环境<\/h2>/);
  assert.match(environmentSource, /\{t\("environmentCenter\.skills"\)\}<\/h2>/);
  assert.match(environmentSource, /className="environment-skill-grid"[\s\S]*?name="VeADK"[\s\S]*?selected=\{veadkSelected\}[\s\S]*?onChange=\{setVeadkSelected\}/);
  assert.match(environmentSource, /const \[veadkSelected, setVeadkSelected\] = useState\(false\)/);
  assert.match(environmentSource, /<SkillSourcePicker/);
  assert.match(environmentSource, /selected=\{draft\.selectedSkills\}/);
  assert.match(environmentSource, /showSelectedCount=\{false\}/);
  assert.match(environmentStyles, /\.environment-skill-grid[\s\S]*?grid-template-columns: repeat\(2, minmax\(0, 1fr\)\)/);
  assert.match(environmentStyles, /\.environment-skill-grid \.cw-skill-add[\s\S]*?min-height: 54px/);
  assert.match(environmentStyles, /\.environment-skill-grid \.cw-selected-skill-row[\s\S]*?border-color: transparent[\s\S]*?background: hsl\(var\(--muted\)/);
  assert.match(environmentSource, /ENVIRONMENT_CATEGORIES\.map/);
  assert.match(environmentSource, /aria-label=\{t\("environmentCenter\.dockerfileContent"\)\}/);
  assert.match(environmentSource, /role="status" aria-live="polite"/);
  assert.match(environmentSource, /StudioConfirmDialog/);
  assert.match(environmentStyles, /@media \(max-width: 560px\)/);
  assert.match(environmentStyles, /grid-template-columns: minmax\(0, 1fr\)/);
  assert.match(environmentSource, /<ResourceDetailLayout/);
  assert.match(environmentStyles, /\.environment-form[\s\S]*?width: min\(100%, 920px\)/);
  assert.match(environmentStyles, /--environment-dockerfile-editor-max-height: 404px/);
  assert.match(environmentStyles, /\.environment-dockerfile-editor\.has-fixed-base[\s\S]*?--environment-dockerfile-editor-max-height: 384px/);
  assert.match(environmentStyles, /\.environment-upload__editor[\s\S]*?min-height: 0[\s\S]*?max-height: var\(--environment-dockerfile-editor-max-height\)[\s\S]*?overflow: hidden/);
  assert.match(environmentStyles, /\.environment-upload__editor \.cm-scroller[\s\S]*?overflow: auto/);
  assert.match(environmentStyles, /--environment-dockerfile-gutter-width: 48px/);
  assert.match(environmentStyles, /\.environment-upload__editor \.cm-gutters[\s\S]*?width: var\(--environment-dockerfile-gutter-width\)/);
  assert.match(environmentStyles, /\.environment-upload__editor \.cm-foldGutter[\s\S]*?display: none !important/);
  assert.match(environmentStyles, /\.environment-dockerfile-from[\s\S]*?min-height: 28px/);
  assert.match(environmentStyles, /\.environment-dockerfile-from__line[\s\S]*?padding: 5px 11px 3px 5px/);
  assert.match(environmentStyles, /\.environment-dockerfile-from code[\s\S]*?padding: 5px 10px 3px 5px/);
  assert.match(environmentStyles, /\.environment-upload__action[\s\S]*?font-size: 12px/);
});

test("offers form-based creation modes and an editable custom Dockerfile", () => {
  assert.match(environmentSource, /type EnvironmentCreationMethod = "custom" \| "dockerfile" \| "git" \| "image"/);
  assert.match(environmentSource, /<span>\{t\("environmentCenter\.creationMethod"\)\}<RequiredMark \/><\/span>[\s\S]*?<Select/);
  assert.match(environmentSource, /value: "custom", label: t\("environmentCenter\.creation\.custom\.label"\)/);
  assert.match(environmentSource, /value: "dockerfile", label: t\("environmentCenter\.creation\.dockerfile\.label"\)/);
  assert.doesNotMatch(environmentSource, /aria-label="Dockerfile 文件"/);
  assert.doesNotMatch(environmentSource, /复制 Dockerfile/);
  assert.doesNotMatch(environmentSource, /恢复模板/);
  assert.doesNotMatch(environmentSource, /使用 AgentKit 基础环境/);
  assert.match(environmentSource, /<span>\{t\("environmentCenter\.presetEnvironment"\)\}<\/span>[\s\S]*?<Select/);
  assert.match(environmentSource, /const dockerfileTemplate = hasDockerfilePresetEnvironment[\s\S]*?composeDockerfile\(selectedBaseImage, ""\)[\s\S]*?: ""/);
  assert.match(environmentSource, /const dockerfileEditorValue = hasDockerfilePresetEnvironment[\s\S]*?dockerfileBody\(uploadedDockerfile\)[\s\S]*?: uploadedDockerfile/);
  assert.match(environmentSource, /hasDockerfilePresetEnvironment[\s\S]*?validateDockerfileBody\(dockerfileEditorValue, selectedBaseImage, t\)[\s\S]*?validateDockerfileUpload\(uploadedDockerfile, undefined, t\)/);
  assert.doesNotMatch(environmentSource, /uploadedDockerfile \|\| dockerfileTemplate/);
  assert.match(environmentSource, /t\("environmentCenter\.upload"\)/);
  assert.match(environmentSource, /t\("environmentCenter\.reset"\)/);
  assert.match(environmentSource, /readDockerfileUpload/);
  assert.match(environmentSource, /value: "none", label: t\("common\.none"\)/);
  assert.match(environmentSource, /environment-dockerfile-base-environment[\s\S]*?value=\{dockerfilePresetEnvironment\}/);
  assert.match(environmentSource, /hasDockerfilePresetEnvironment \? \(\s*<div className="environment-dockerfile-from"/);
  assert.doesNotMatch(environmentSource, /aria-label="Dockerfile 基础镜像"[\s\S]*?<input/);
  assert.match(environmentSource, /value=\{dockerfileEditorValue\}/);
  assert.match(environmentSource, /lineNumberStart=\{hasDockerfilePresetEnvironment \? 2 : 1\}/);
  assert.match(environmentSource, /height="auto"/);
  assert.match(environmentSource, /maxHeight="var\(--environment-dockerfile-editor-max-height\)"/);
  assert.doesNotMatch(environmentSource, /environment-dockerfile-base-image/);
  assert.match(environmentSource, /label: "AIO Sandbox"/);
  assert.match(environmentSource, /label: "Codex Sandbox"/);
  assert.doesNotMatch(environmentSource, /AGENTKIT_DOCKERFILE_BASE_OPTIONS[\s\S]*?label: "Ubuntu"/);
  assert.match(environmentModelSource, /enterprise-public-cn-beijing\.cr\.volces\.com\/vefaas-public\/codexenv:1\.1\.0/);
  assert.match(environmentModelSource, /enterprise-public-ap-southeast-1\.cr\.volces\.com\/vefaas-public\/codexenv:1\.1\.0/);
  assert.match(environmentSource, /<h3>Dockerfile<RequiredMark \/><\/h3>/);
  assert.match(environmentSource, /className="environment-dockerfile-from"/);
  assert.match(environmentSource, /<span className="environment-dockerfile-from__keyword">FROM<\/span>/);
  assert.match(environmentSource, /<CodeEditor[\s\S]*?path="Dockerfile"/);
  assert.match(environmentSource, /validateDockerfileBody/);
  assert.match(environmentSource, /<\/div>\s*\{uploadError \? <p className="environment-upload__error environment-upload__error--below"/);
  assert.match(environmentStyles, /\.environment-form-grid/);
  assert.doesNotMatch(environmentSource, /SegmentedControl/);
  assert.match(environmentSource, /<span>\{t\("environmentCenter\.repository\.type"\)\}<RequiredMark \/><\/span>[\s\S]*?<Select/);
  assert.match(environmentSource, /<span>\{t\("environmentCenter\.region"\)\}<RequiredMark \/><\/span>[\s\S]*?<Select/);
  assert.match(environmentSource, /optionClassName="environment-select-option"/);
  assert.match(environmentStyles, /\.environment-select-trigger[\s\S]*?font-size: 13px[\s\S]*?font-weight: 400/);
  assert.match(environmentStyles, /\.environment-select-option > div > div \+ div[\s\S]*?font-size: 11\.5px[\s\S]*?font-weight: 400/);
  assert.match(environmentStyles, /\.environment-configuration[\s\S]*?border-top: 1px dashed hsl\(var\(--border\)\)/);
  assert.match(environmentStyles, /\.environment-upload[\s\S]*?border-top: 1px dashed hsl\(var\(--border\)\)/);
  assert.match(environmentStyles, /\.environment-source-section[\s\S]*?border-top: 1px dashed hsl\(var\(--border\)\)/);
  assert.match(environmentSource, /t\("environmentCenter\.name"\)[\s\S]*?<RequiredMark \/>/);
  assert.match(environmentSource, /t\("environmentCenter\.git\.address"\)[\s\S]*?<RequiredMark \/>/);
  assert.doesNotMatch(environmentSource, /placeholder="例如：/);
  assert.match(environmentStyles, /\.environment-repository-fields \.pp-resource-field > span:first-child::after[\s\S]*?content: "\*"/);
  assert.doesNotMatch(environmentSource, /environment-source-section__header/);
  assert.match(environmentStyles, /\.environment-field[\s\S]*?font-size: 14px[\s\S]*?font-weight: 500/);
  assert.match(environmentStyles, /\.environment-field[\s\S]*?align-items: center/);
  assert.match(environmentStyles, /\.environment-field > span:first-child[\s\S]*?white-space: nowrap/);
  assert.match(environmentSource, /<span>\{t\("environmentCenter\.git\.ref"\)\}<\/span>/);
  assert.doesNotMatch(environmentSource, /Branch、Tag 或 Commit（可选）/);
});

test("starts optional icon packages unselected", async () => {
  const server = await createServer({
    appType: "custom",
    logLevel: "silent",
    optimizeDeps: { noDiscovery: true },
    server: { middlewareMode: true },
  });
  try {
    const model = await server.ssrLoadModule("/src/ui/environmentModel.ts");
    assert.deepEqual(model.EMPTY_ENVIRONMENT_DRAFT.optionIds, []);
  } finally {
    await server.close();
  }
});

test("supports public Git builds with automatic Dockerfile inspection", () => {
  assert.match(environmentSource, /value: "git", label: t\("environmentCenter\.creation\.git\.label"\)/);
  assert.match(environmentSource, /inspectEnvironmentRepository/);
  assert.match(environmentSource, /description: t\("environmentCenter\.creation\.git\.description"\)/);
  assert.match(environmentSource, /window\.setTimeout\(\(\) => void inspectRepository\(\), 600\)/);
  assert.match(environmentSource, /autoAttemptedKeyRef/);
  assert.match(environmentSource, /message\.split\("\\n原始响应：", 1\)/);
  assert.match(environmentStyles, /@media \(max-width: 640px\)[\s\S]*?\.environment-source-error[\s\S]*?flex-direction: column/);
  assert.match(environmentSource, /t\("environmentCenter\.git\.inspecting"\)/);
  assert.match(environmentSource, /t\("environmentCenter\.git\.noDockerfile"\)/);
  assert.match(environmentSource, /onDockerfilePathChange\(result\.dockerfiles\.length === 1/);
  assert.match(environmentSource, /<DeploymentSelect[\s\S]*?ariaLabel=\{t\("environmentCenter\.git\.selectDockerfile"\)\}/);
  assert.match(environmentSource, /t\("environmentCenter\.repository\.managedHint"\)/);
  assert.match(environmentSource, /containerRepository: creationMethod === "git"/);
  assert.match(clientSource, /POST \/web\/v3\/environment-repositories\/inspect|"\/web\/v3\/environment-repositories\/inspect"/);
  assert.match(clientSource, /method: "POST"/);
  assert.match(clientSource, /dockerfiles\.every\(\(item\) => typeof item === "string"\)/);
});

test("binds an existing image through region-aware CR resource selectors", () => {
  assert.match(environmentSource, /value: "image", label: t\("environmentCenter\.creation\.image\.label"\)/);
  assert.match(environmentSource, /id="environment-region"/);
  assert.match(environmentSource, /<ContainerRepositorySelector/);
  assert.match(environmentSource, /t\("environmentCenter\.existingImage\.reference"\)/);
  assert.match(environmentSource, /imageSource: creationMethod === "image"/);
  assert.match(environmentSource, /if \(input\.imageSource\)[\s\S]*?return;/);
  assert.match(environmentSource, /const cpUrl = environment\.imageSource[\s\S]*?undefined/);
  assert.match(environmentSource, /build && !environment\.imageSource && !ACTIVE_BUILD_STATUSES/);
  assert.match(deploymentResourcesSource, /export function ContainerRepositorySelector/);
  assert.match(deploymentResourcesSource, /kind: "cr-registry"/);
  assert.match(deploymentResourcesSource, /kind: "cr-namespace"/);
  assert.match(deploymentResourcesSource, /kind: "cr-repository"/);
  assert.match(deploymentResourcesSource, /registry: resource\.name,[\s\S]*?namespace: "",[\s\S]*?repository: ""/);
  assert.match(environmentSource, /className="environment-form-grid environment-git-fields"/);
  assert.match(environmentStyles, /\.environment-repository-fields[\s\S]*?grid-template-columns: minmax\(0, 1fr\)/);
});

test("exports and imports environments with share codes", async () => {
  assert.match(clientSource, /\/web\/v3\/environments\/\$\{encodeURIComponent\(environmentId\)\}\/share-code/);
  assert.match(clientSource, /"\/web\/v3\/environment-share-codes\/inspect"/);
  assert.match(clientSource, /"\/web\/v3\/environment-share-codes\/import"/);
  assert.match(clientSource, /shareCodes/);
  assert.match(clientSource, /status === "created" \|\| candidate\.status === "duplicate" \|\| candidate\.status === "failed"/);

  assert.match(clientSource, /export function parseEnvironmentShareCodes/);
  assert.match(clientSource, /split\(\/\[,，\\n\\r\]\+\/\)/);
  assert.match(clientSource, /new Set<string>\(\)/);
  assert.match(environmentSource, /t\("environmentCenter\.import\.tooMany"/);
  assert.match(environmentSource, /t\("environmentCenter\.share\.action"\)/);
  assert.match(clientSource, /clipboard\.writeText/);
  assert.match(environmentSource, /t\("environmentCenter\.share\.copied"\)/);
  assert.match(environmentSource, /state === "copied"[\s\S]*?environmentCenter\.share\.copied[\s\S]*?shareCode \? \(/);
  assert.match(environmentSource, /aria-label=\{t\("environmentCenter\.share\.fullCode"\)\}/);
  assert.match(environmentSource, /t\("environmentCenter\.share\.copiedHint"\)/);
  assert.match(environmentSource, /t\("environmentCenter\.share\.copyFailedHint"\)/);
  assert.match(environmentSource, /t\("environmentCenter\.share\.safety"\)/);
  assert.match(environmentSource, /readOnly/);
  assert.match(environmentSource, /t\("common\.retry"\)/);
  assert.match(environmentSource, /aria-label=\{t\("environmentCenter\.import\.title"\)\}/);
  assert.match(environmentSource, /t\("environmentCenter\.import\.multipleHint"\)/);
  assert.match(environmentSource, /t\("environmentCenter\.import\.found", \{/);
  assert.match(environmentSource, /navigator\.clipboard\.readText/);
  assert.match(environmentSource, /startsWith\("akenv:\/\/"\)/);
  assert.match(environmentSource, /promptedClipboardShareTexts/);
  assert.match(environmentSource, /window\.addEventListener\("focus", handleFocus\)/);
  assert.match(environmentSource, /document\.addEventListener\("visibilitychange", handleVisibilityChange\)/);
  assert.match(environmentSource, /window\.addEventListener\("paste", handlePaste\)/);
  assert.match(environmentSource, /openClipboardImport\(text, true\)/);
  assert.match(environmentSource, /t\("environmentCenter\.clipboardUnsupported"\)/);
  assert.match(environmentSource, /t\("environmentCenter\.clipboardReadError"\)/);
  assert.match(environmentSource, /clipboardReadPermissionDenied/);
  assert.match(environmentSource, /className="environment-clipboard-notice" role="alert"/);
  assert.match(environmentSource, /t\("environmentCenter\.manualImport"\)/);
  assert.match(environmentSource, /item\.status === "failed"/);
  assert.match(environmentSource, /readyToImport = phase === "ready"[\s\S]*?validInspections\.length > 0/);
  assert.match(environmentSource, /const importedById = new Map<string, StudioEnvironment>/);
  assert.match(environmentSource, /importedById\.set\(item\.environment\.id, item\.environment\)/);
  assert.match(environmentStyles, /\.environment-share-dialog/);
  assert.match(environmentStyles, /@media \(max-width: 560px\)[\s\S]*?\.environment-share-dialog/);
  assert.match(environmentStyles, /\.environment-clipboard-notice/);

  const server = await createServer({
    appType: "custom",
    logLevel: "silent",
    optimizeDeps: { noDiscovery: true },
    server: { middlewareMode: true },
  });
  try {
    const module = await server.ssrLoadModule("/src/adk/client.ts");
    assert.deepEqual(
      module.parseEnvironmentShareCodes(" akenv://one，akenv://two\nakenv://one, ,akenv://three "),
      ["akenv://one", "akenv://two", "akenv://three"],
    );
    await assert.rejects(
      module.writeEnvironmentShareCode("akenv://one", null),
      /This browser does not support writing to the clipboard/,
    );
    await assert.rejects(
      module.writeEnvironmentShareCode("akenv://one", {
        writeText: async () => { throw new Error("denied"); },
      }),
      /Unable to write to the clipboard/,
    );
  } finally {
    await server.close();
  }
});

test("keeps environment deletion discoverable from the editor", () => {
  assert.match(environmentSource, /onDelete\?: \(\) => void/);
  assert.match(environmentSource, /color="danger" variant="ghost"[\s\S]*?>\s*\{t\("common\.delete"\)\}\s*<\/Button>/);
  assert.match(environmentSource, /onDelete=\{editingEnvironment \? \(\) => setDeleteTarget\(editingEnvironment\)/);
  assert.match(environmentSource, /const deleteDialog = deleteTarget \? \(/);
  assert.match(environmentSource, /deleteEnvironment\(target\.id\)/);
  assert.match(environmentSource, /setView\(\{ kind: "list" \}\)/);
});

test("validates Dockerfile uploads before the environment is created", async () => {
  const server = await createServer({
    appType: "custom",
    logLevel: "silent",
    optimizeDeps: { noDiscovery: true },
    server: { middlewareMode: true },
  });
  try {
    const upload = await server.ssrLoadModule("/src/ui/environmentDockerfileUpload.ts");
    assert.equal(upload.validateDockerfileUpload("", 0), "Dockerfile 内容不能为空。");
    assert.equal(
      upload.validateDockerfileUpload("RUN echo hello", 14),
      "Dockerfile 缺少 FROM 指令。",
    );
    assert.equal(
      upload.validateDockerfileUpload("FROM ubuntu:24.04", upload.MAX_DOCKERFILE_BYTES + 1),
      "Dockerfile 不能超过 128 KiB。",
    );
    assert.equal(upload.validateDockerfileUpload("# syntax=docker/dockerfile:1\nFROM ubuntu:24.04"), "");
    assert.equal(upload.normalizeDockerfileContent("\uFEFFFROM ubuntu:24.04\r\n"), "FROM ubuntu:24.04\n");
    assert.equal(upload.dockerfileBaseImage("FROM node:22\nRUN node --version"), "node:22");
    assert.equal(upload.dockerfileBody("FROM node:22\n\nRUN node --version"), "RUN node --version");
    assert.equal(upload.composeDockerfile("node:22", "RUN node --version"), "FROM node:22\nRUN node --version");
    assert.equal(
      upload.validateDockerfileBody("RUN echo ok\nFROM alpine", "node:22"),
      "基础镜像已固定在第一行，请删除 Dockerfile 正文中的 FROM 指令。",
    );
    assert.match(dockerfileUploadSource, /file\.text\(\)/);
  } finally {
    await server.close();
  }
});

test("persists environments and starts image builds through the Studio API", () => {
  assert.match(environmentSource, /listEnvironments/);
  assert.match(environmentSource, /createEnvironment/);
  assert.match(environmentSource, /updateEnvironment/);
  assert.match(environmentSource, /deleteEnvironment/);
  assert.match(environmentSource, /buildEnvironment/);
  assert.match(environmentSource, /TextShimmer/);
  assert.match(environmentSource, /t\("common\.reload"\)/);
  assert.match(environmentSource, /t\("environmentCenter\.buildDetails\.rebuild"\)/);
  assert.doesNotMatch(environmentSource, /INITIAL_ENVIRONMENTS/);
  assert.match(clientSource, /"\/web\/v3\/environments"/);
  assert.match(clientSource, /\/web\/v3\/environments\/\$\{encodeURIComponent\(environmentId\)\}/);
  assert.match(clientSource, /\/web\/v3\/environments\/\$\{encodeURIComponent\(environmentId\)\}\/build/);
  assert.match(clientSource, /"\/web\/v3\/environment-resources"/);
  assert.doesNotMatch(clientSource, /["`]\/web\/environments/);
  assert.doesNotMatch(clientSource, /["`]\/web\/environment-(?:repositories|resources|share-codes)/);
});

test("shows live build steps and redacted log snapshots in a responsive detail dialog", () => {
  assert.match(environmentSource, /getEnvironmentBuild/);
  assert.match(environmentSource, /includeLogs: true/);
  assert.match(environmentSource, /BUILD_LOG_REFRESH_INTERVAL_MS = 3_000/);
  assert.match(environmentSource, /window\.setTimeout\(refresh, BUILD_LOG_REFRESH_INTERVAL_MS\)/);
  assert.match(environmentSource, /<StudioBuildProgress/);
  assert.match(environmentSource, /t\("environmentCenter\.buildDetails\.title"\)/);
  assert.match(environmentSource, /t\("environmentCenter\.buildDetails\.elapsed"\)/);
  assert.match(environmentSource, /t\("environmentCenter\.buildDetails\.openCodePipeline"\)/);
  assert.match(clientSource, /\?includeLogs=true/);
  assert.match(buildProgressSource, /navigator\.clipboard\.writeText\(log\)/);
  assert.match(buildProgressSource, /highlightBashLog\(log\)/);
  assert.match(buildProgressSource, /shouldFollowBuildLog\(event\.currentTarget\)/);
  assert.match(buildProgressSource, /dangerouslySetInnerHTML/);
  assert.match(buildProgressSource, /t\("studioBuildProgress\.waiting"\)/);
  assert.match(buildLogSource, /highlight\.js\/lib\/languages\/bash/);
  assert.match(buildProgressStyles, /overflow: auto/);
  assert.match(environmentStyles, /\.environment-build-dialog__body[\s\S]*?overflow: hidden/);
  assert.match(buildProgressStyles, /@media \(max-width: 640px\)/);
  assert.match(environmentStyles, /max-height: 92dvh/);
});

test("opens a version-bound environment manifest beside the primary card action", async () => {
  assert.match(resourceCardSource, /auxiliaryAction/);
  assert.match(resourceCardSource, /className="library-resource-card__auxiliary-action"/);
  assert.match(environmentSource, /import \{ ArrowRotateCw, FileCode \} from "@openai\/apps-sdk-ui\/components\/Icon"/);
  assert.match(environmentSource, /icon: <FileCode \/>/);
  assert.match(environmentSource, /t\("environmentCenter\.manifest\.view"\)/);
  assert.match(environmentSource, /t\("environmentCenter\.manifest\.unavailable"\)/);
  assert.match(environmentSource, /<EnvironmentManifestDialog/);
  assert.match(environmentSource, /<CodeEditor[\s\S]*?path="environment\.yaml"[\s\S]*?readOnly/);
  assert.match(environmentSource, /navigator\.clipboard\.writeText\(manifestYaml\)/);
  assert.match(clientSource, /\/manifest/);
  assert.match(environmentStyles, /\.environment-manifest-dialog__editor/);
  assert.match(environmentStyles, /\.environment-card \.library-resource-card__auxiliary-action\s*\{[\s\S]*?border-color: transparent;[\s\S]*?background: transparent;/);
  assert.match(environmentStyles, /\.environment-card \.library-resource-card__auxiliary-action:hover:not\(:disabled\)[\s\S]*?background: hsl\(var\(--muted\) \/ 0\.72\)/);
  assert.match(resourceCollectionStyles, /@media \(hover: none\), \(pointer: coarse\)/);

  const server = await createServer({
    appType: "custom",
    logLevel: "silent",
    optimizeDeps: { noDiscovery: true },
    server: { middlewareMode: true },
  });
  try {
    const manifest = await server.ssrLoadModule("/src/ui/environmentManifest.ts");
    const yaml = manifest.formatEnvironmentManifest({
      apiVersion: "agentkit.studio/v3",
      kind: "Environment",
      metadata: {
        id: "env-1",
        name: "Browser tools",
        version: "20260831T010203Z-a1b2c3d4",
        description: "Browser automation",
      },
      spec: {
        image: "registry.example/browser:latest",
        baseEnvironment: "ubuntu",
        baseImage: "ubuntu:24.04",
        operatingSystem: "ubuntu-24.04",
        language: "python-3.12",
        executionRuntime: "veadk",
        packages: ["playwright", "chromium"],
        capabilities: [],
        skills: [],
      },
      status: {
        phase: "available",
        createdAt: "2026-08-31T01:02:03Z",
        updatedAt: "2026-08-31T01:05:03Z",
      },
    });
    assert.match(yaml, /^apiVersion: agentkit\.studio\/v3$/m);
    assert.match(yaml, /^kind: Environment$/m);
    assert.match(yaml, /^  image: registry\.example\/browser:latest$/m);
    assert.match(yaml, /^    - playwright$/m);
  } finally {
    await server.close();
  }
  assert.match(manifestSource, /stringify\(manifest/);
});

test("accepts legacy and Codex Sandbox environment manifests", async () => {
  const server = await createServer({
    appType: "custom",
    logLevel: "silent",
    optimizeDeps: { noDiscovery: true },
    server: { middlewareMode: true },
  });
  try {
    const client = await server.ssrLoadModule("/src/adk/client.ts");
    const formatter = await server.ssrLoadModule(
      "/src/ui/environmentManifest.ts",
    );
    const manifest = {
      apiVersion: "agentkit.studio/v3",
      kind: "Environment",
      metadata: {
        id: "env-codex",
        name: "Codex Sandbox",
        version: "20260902T010203Z-a1b2c3d4",
        description: "Codex development environment",
      },
      spec: {
        image: "registry.example/codex:latest",
        baseEnvironment: "codex-sandbox",
        baseImage: "registry.example/codexenv:1.1.0",
        operatingSystem: "ubuntu-22.04",
        language: "python-3.12",
        executionRuntime: "veadk",
        packages: [],
        capabilities: ["shell-exec"],
        skills: [],
      },
      status: {
        phase: "available",
        toolId: "tool-codex",
        toolStatus: "ready",
        createdAt: "2026-09-02T01:02:03Z",
        updatedAt: "2026-09-02T01:05:03Z",
      },
    };

    const codexManifest = client.parseEnvironmentManifest(manifest);
    assert.equal(codexManifest.spec.baseEnvironment, "codex-sandbox");
    assert.match(
      formatter.formatEnvironmentManifest(codexManifest),
      /^  baseEnvironment: codex-sandbox$/m,
    );

    const legacyManifest = client.parseEnvironmentManifest({
      ...manifest,
      apiVersion: "agentkit.studio/v1alpha1",
      metadata: { ...manifest.metadata, id: "env-aio", name: "AIO Sandbox" },
      spec: { ...manifest.spec, baseEnvironment: "aio-sandbox" },
    });
    assert.equal(legacyManifest.spec.baseEnvironment, "aio-sandbox");
  } finally {
    await server.close();
  }
});

test("keeps environment card metadata focused on its update time", () => {
  const cardSource = environmentSource.slice(
    environmentSource.indexOf("{visibleEnvironments.map"),
    environmentSource.indexOf("</ResourceGrid>", environmentSource.indexOf("{visibleEnvironments.map")),
  );
  assert.match(cardSource, /metadata=\{\[[\s\S]*?label: t\("workspace\.updated"\)/);
  assert.match(cardSource, /value: environmentUpdatedAt\(environment\.updatedAt, i18n\.resolvedLanguage \?\? i18n\.language\)/);
  assert.match(cardSource, /title: environmentUpdatedAtTitle\(environment\.updatedAt, i18n\.resolvedLanguage \?\? i18n\.language\)/);
  assert.match(environmentSource, /return formatRelativeTimeLabel\(value, Date\.now\(\), locale\)/);
  assert.match(environmentSource, /dateStyle: "medium"/);
  assert.match(environmentSource, /timeStyle: "medium"/);
  assert.doesNotMatch(
    environmentStyles,
    /\.environment-card \.resource-card__metadata > div:last-child\s*\{[\s\S]*?display:\s*none/,
  );
  assert.doesNotMatch(cardSource, /label: "基础环境"|label: "语言"|label: "工作区"/);
});

test("uses AIO Sandbox as the default base environment and preserves its runtime", async () => {
  const server = await createServer({
    appType: "custom",
    logLevel: "silent",
    optimizeDeps: { noDiscovery: true },
    server: { middlewareMode: true },
  });
  try {
    const model = await server.ssrLoadModule("/src/ui/environmentModel.ts");
    assert.equal(model.EMPTY_ENVIRONMENT_DRAFT.baseEnvironment, "aio-sandbox");
    const dockerfile = model.buildEnvironmentDockerfile(model.EMPTY_ENVIRONMENT_DRAFT);
    assert.match(dockerfile, /^ARG AIO_BASE_IMAGE=agentkit-cli-2107625663-cn-beijing\.cr\.volces\.com\/agentkit\/agent-native-requirements-aio:0\.2\.1-20260831$/m);
    assert.match(dockerfile, /^FROM --platform=\$\{AIO_BASE_PLATFORM\} \$\{AIO_BASE_IMAGE\}$/m);
    assert.match(dockerfile, /BASH_VENV_PATH=\/opt\/veadk-environment\/\.venv/);
    assert.match(dockerfile, /^EXPOSE 8080$/m);
    assert.doesNotMatch(dockerfile, /^CMD /m);
    assert.doesNotMatch(dockerfile, /^ENTRYPOINT /m);
  } finally {
    await server.close();
  }
});

test("highlights Bash logs and follows only while the reader stays near the bottom", async () => {
  const server = await createServer({
    appType: "custom",
    logLevel: "silent",
    optimizeDeps: { noDiscovery: true },
    server: { middlewareMode: true },
  });
  try {
    const buildLog = await server.ssrLoadModule("/src/ui/studioBuildLog.ts");
    assert.equal(buildLog.shouldFollowBuildLog({
      scrollHeight: 1000,
      scrollTop: 730,
      clientHeight: 240,
    }), true);
    assert.equal(buildLog.shouldFollowBuildLog({
      scrollHeight: 1000,
      scrollTop: 600,
      clientHeight: 240,
    }), false);
    assert.match(buildLog.highlightBashLog("apt-get update && echo ready"), /hljs-built_in/);
    assert.match(buildLog.highlightBashLog("echo '<script>'"), /&lt;script&gt;/);
  } finally {
    await server.close();
  }
});

test("generates a Dockerfile from language and selected tools", async () => {
  const server = await createServer({
    appType: "custom",
    logLevel: "silent",
    optimizeDeps: { noDiscovery: true },
    server: { middlewareMode: true },
  });
  try {
    const model = await server.ssrLoadModule("/src/ui/environmentModel.ts");
    const dockerfile = model.buildEnvironmentDockerfile({
      name: "Browser environment",
      description: "",
      operatingSystem: "ubuntu-22.04",
      language: "python-3.12",
      optionIds: ["lark-cli", "pandoc", "playwright", "chromium"],
    });
    assert.match(dockerfile, /^# Operating system: Ubuntu 22\.04$/m);
    assert.match(dockerfile, /^FROM ubuntu:22\.04$/m);
    assert.match(dockerfile, /^# Python 3\.12$/m);
    assert.match(dockerfile, /^# VeADK$/m);
    assert.doesNotMatch(dockerfile, /[\u3400-\u9fff]/u);
    assert.match(dockerfile, /python -m pip install --upgrade veadk-python/);
    assert.match(dockerfile, /PIP_DEFAULT_TIMEOUT=300/);
    assert.match(dockerfile, /PIP_RETRIES=10/);
    assert.match(dockerfile, /PIP_INDEX_URL=https:\/\/pypi\.org\/simple/);
    assert.match(dockerfile, /PYTHON_SOURCE_BASE_URL=https:\/\/www\.python\.org\/ftp\/python/);
    assert.match(dockerfile, /PLAYWRIGHT_DOWNLOAD_HOST=https:\/\/cdn\.playwright\.dev/);
    assert.match(dockerfile, /ARG APT_MIRROR_URL=http:\/\/archive\.ubuntu\.com\/ubuntu/);
    assert.match(dockerfile, /Acquire::Retries \"5\"/);
    assert.match(dockerfile, /Acquire::ForceIPv4 \"true\"/);
    assert.equal(dockerfile.match(/apt-get update/g)?.length, 1);
    assert.equal(dockerfile.match(/apt-get install -y --no-install-recommends/g)?.length, 1);
    assert.match(dockerfile, /Python-3\.12\.11\.tgz/);
    assert.match(dockerfile, /\.\/configure --prefix=\/opt\/python/);
    assert.doesNotMatch(dockerfile, /astral\.sh|github\.com\/astral-sh/);
    assert.match(dockerfile, /pandoc/);
    assert.match(dockerfile, /chromium/);
    assert.match(dockerfile, /lark-cli/);
    assert.match(dockerfile, /python -m playwright install chromium/);
    assert.doesNotMatch(dockerfile, /playwright install --with-deps/);
    assert.match(dockerfile, /^# lark-cli$/m);
    assert.match(dockerfile, /^# Playwright$/m);
  } finally {
    await server.close();
  }
});

test("changes the base image with the selected operating system", async () => {
  const server = await createServer({
    appType: "custom",
    logLevel: "silent",
    optimizeDeps: { noDiscovery: true },
    server: { middlewareMode: true },
  });
  try {
    const model = await server.ssrLoadModule("/src/ui/environmentModel.ts");
    const dockerfile = model.buildEnvironmentDockerfile({
      name: "Ubuntu environment",
      description: "",
      operatingSystem: "ubuntu-24.04",
      language: "python-3.10",
      optionIds: [],
    });
    assert.match(dockerfile, /^# Operating system: Ubuntu 24\.04$/m);
    assert.match(dockerfile, /^FROM ubuntu:24\.04$/m);
    assert.match(dockerfile, /^# Python 3\.10$/m);
  } finally {
    await server.close();
  }
});

test("uses reliable GitHub CLI and browser recipes without duplicate Chromium installs", async () => {
  const server = await createServer({
    appType: "custom",
    logLevel: "silent",
    optimizeDeps: { noDiscovery: true },
    server: { middlewareMode: true },
  });
  try {
    const model = await server.ssrLoadModule("/src/ui/environmentModel.ts");
    const dockerfile = model.buildEnvironmentDockerfile({
      name: "Toolchain",
      description: "",
      operatingSystem: "ubuntu-24.04",
      language: "python-3.12",
      optionIds: ["opencli", "github-cli", "playwright", "chromium"],
    });
    assert.match(dockerfile, /^    gh \\$/m);
    assert.match(dockerfile, /ENV PLAYWRIGHT_BROWSERS_PATH=\/ms-playwright/);
    assert.equal(
      dockerfile.match(/python -m pip install --upgrade playwright/g)?.length,
      1,
    );
    assert.equal(
      dockerfile.match(/python -m playwright install chromium/g)?.length,
      1,
    );
    assert.equal(dockerfile.match(/apt-get update/g)?.length, 1);
    assert.equal(dockerfile.match(/apt-get install -y --no-install-recommends/g)?.length, 1);
    assert.match(dockerfile, /^    libasound2t64 \\$/m);
    assert.match(dockerfile, /npm install --global @jackwener\/opencli@1\.8\.7/);
  } finally {
    await server.close();
  }
});

test("generates every supported OS and Python combination with per-tool comments", async () => {
  const server = await createServer({
    appType: "custom",
    logLevel: "silent",
    optimizeDeps: { noDiscovery: true },
    server: { middlewareMode: true },
  });
  try {
    const model = await server.ssrLoadModule("/src/ui/environmentModel.ts");
    for (const operatingSystem of model.ENVIRONMENT_OPERATING_SYSTEMS) {
      for (const language of model.ENVIRONMENT_LANGUAGES) {
        const optionIds = model.ENVIRONMENT_CATEGORIES.flatMap((category) =>
          category.options.map((option) => option.id),
        );
        const dockerfile = model.buildEnvironmentDockerfile({
          name: "matrix",
          description: "",
          operatingSystem: operatingSystem.id,
          language: language.id,
          optionIds,
        });
        assert.match(dockerfile, new RegExp(`^FROM ${operatingSystem.image.replace(".", "\\.")}$`, "m"));
        assert.match(dockerfile, new RegExp(`^# Python ${language.id.replace("python-", "").replace(".", "\\.")}$`, "m"));
        assert.equal(dockerfile.match(/apt-get update/g)?.length, 1);
        assert.equal(dockerfile.match(/apt-get install -y --no-install-recommends/g)?.length, 1);
        for (const category of model.ENVIRONMENT_CATEGORIES) {
          for (const option of category.options) {
            assert.match(dockerfile, new RegExp(`^# ${option.label.replace(/[.*+?^${}()|[\\]\\]/g, "\\$&")}$`, "m"));
          }
        }
      }
    }
  } finally {
    await server.close();
  }
});
