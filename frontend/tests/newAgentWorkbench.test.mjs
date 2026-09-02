import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const customCreateSource = readFileSync(
  new URL("../src/create/CustomCreate.tsx", import.meta.url),
  "utf8",
);
const appSource = readFileSync(
  new URL("../src/App.tsx", import.meta.url),
  "utf8",
);
const workbenchSource = readFileSync(
  new URL("../src/create/NewAgentWorkbench.tsx", import.meta.url),
  "utf8",
);
const workbenchStyles = readFileSync(
  new URL("../src/create/NewAgentWorkbench.css", import.meta.url),
  "utf8",
);
const catalogSource = readFileSync(
  new URL("../src/create/veadkCatalog.ts", import.meta.url),
  "utf8",
);
const modePickerSource = readFileSync(
  new URL("../src/create/AgentCreationModePicker.tsx", import.meta.url),
  "utf8",
);
const modePickerStyles = readFileSync(
  new URL("../src/create/AgentCreationModePicker.css", import.meta.url),
  "utf8",
);
const skillSourcePickerSource = readFileSync(
  new URL("../src/ui/SkillSourcePicker.tsx", import.meta.url),
  "utf8",
);
const globalStyles = readFileSync(
  new URL("../src/styles.css", import.meta.url),
  "utf8",
);

test("the app-level create entry asks for a mode before either creation flow", () => {
  assert.match(
    customCreateSource,
    /const isVulcanCreation =\s*createMode === "custom" && freshCreationSurface === "vulcan"/,
  );
  assert.match(
    customCreateSource,
    /usesNewAgentWorkbench = isVulcanCreation[\s\S]*?<NewAgentWorkbench/,
  );
  assert.doesNotMatch(customCreateSource, /<AgentCreationModePicker/);
  assert.match(
    appSource,
    /showAddMenu && addMenuSurface === "entry"[\s\S]*?<AgentCreationModePicker/,
  );
  assert.match(
    appSource,
    /onSelectVulcan=\{\(\) => \{[\s\S]*?setCustomCreationSurface\("vulcan"\)[\s\S]*?setCreateView\("custom"\)/,
  );
  assert.match(
    appSource,
    /onSelectTraditional=\{\(\) => \{[\s\S]*?setAddMenuSurface\("traditional"\)/,
  );
  assert.match(appSource, /showAddMenu \? \([\s\S]*?<StackCards/);
  assert.match(
    appSource,
    /setCustomCreationSurface\("traditional"\)[\s\S]*?setCreateView\("custom"\)/,
  );
  assert.match(appSource, /freshCreationSurface=\{customCreationSurface\}/);
  assert.doesNotMatch(workbenchSource, /className="cw-/);
});

test("workspace drafts restore the creation mode they were saved with", () => {
  assert.match(
    appSource,
    /saveWorkspaceDraft\([\s\S]*?customCreationSurface === "vulcan" \? "quick" : "traditional"/,
  );
  assert.match(
    appSource,
    /setCustomCreationSurface\(\s*workspaceAgentCreationMode\(item\) === "quick"\s*\? "vulcan"\s*: "traditional"/,
  );
});

test("deployment tasks carry the workspace draft id into the library", () => {
  assert.match(customCreateSource, /workspaceDraftId\?: string/);
  assert.match(
    customCreateSource,
    /const taskBase = \{[\s\S]*?\.\.\.\(workspaceDraftId \? \{ draftId: workspaceDraftId \} : \{\}\)/,
  );
  assert.match(appSource, /workspaceDraftId=\{editingDraftId \|\| undefined\}/);
});

test("quick Runtime updates keep the existing target and use update semantics", () => {
  assert.match(
    customCreateSource,
    /if \(!deploymentTarget\) \{[\s\S]*?checkRuntimeNameAvailability/,
  );
  assert.match(
    customCreateSource,
    /isRuntimeUpdate=\{Boolean\(deploymentTarget\)\}/,
  );
  assert.match(workbenchSource, /isRuntimeUpdate\?: boolean/);
  assert.match(
    workbenchSource,
    /disabled=\{deploying \|\| isRuntimeUpdate\}/,
  );
  assert.match(workbenchSource, /\? "更新并发布"[\s\S]*?: "部署"/);
});

test("creation mode picker has exactly the quick and traditional cards", () => {
  assert.match(modePickerSource, />\s*以不同模式构建您的智能体\s*</);
  assert.match(modePickerSource, />\s*快速模式\s*</);
  assert.match(modePickerSource, />\s*传统模式\s*</);
  assert.equal(
    modePickerSource.match(/className="agent-creation-mode-picker__card"/g)
      ?.length,
    2,
  );
  assert.match(modePickerSource, /@openai\/apps-sdk-ui\/components\/Button/);
  assert.match(
    modePickerSource,
    /import \{ ResourceIdentityMark \} from "\.\.\/ui\/ResourceCollection"/,
  );
  assert.equal(modePickerSource.match(/<ResourceIdentityMark/g)?.length, 2);
  assert.equal(
    modePickerSource.match(/className="agent-creation-mode-picker__avatar/g)
      ?.length,
    2,
  );
  assert.equal(
    modePickerSource.match(/className="agent-creation-mode-picker__features"/g)
      ?.length,
    2,
  );
  assert.equal(modePickerSource.match(/<span>特性<\/span>/g)?.length, 2);
  assert.match(modePickerSource, />\s*动态派生子智能体自主完成任务\s*</);
  assert.match(modePickerSource, />\s*高度自定义您的智能体结构\s*</);
  assert.match(modePickerSource, />\s*动态派生子智能体\s*</);
  assert.match(modePickerSource, />\s*可视化配置\s*</);
  const vulcanCard = modePickerSource.slice(
    modePickerSource.indexOf("selectMode(onSelectVulcan)"),
    modePickerSource.indexOf("selectMode(onSelectTraditional)"),
  );
  const traditionalCard = modePickerSource.slice(
    modePickerSource.indexOf("selectMode(onSelectTraditional)"),
  );
  assert.equal(vulcanCard.match(/<FeatureIcon/g)?.length, 6);
  assert.equal(traditionalCard.match(/<FeatureIcon/g)?.length, 5);
  assert.match(modePickerSource, />\s*按需调用技能\s*</);
  assert.match(modePickerSource, />\s*任务过程可追踪\s*</);
  assert.match(modePickerSource, />\s*存量智能体迁移\s*</);
  assert.match(modePickerSource, />\s*实时调试\s*</);
  assert.match(modePickerSource, />\s*可选性能优化\s*</);
  assert.match(modePickerSource, />\s*精细参数控制\s*</);
  assert.doesNotMatch(
    modePickerSource,
    /purple|violet|gradient|className="cw-/i,
  );
  assert.match(
    modePickerStyles,
    /\.agent-creation-mode-picker__feature-grid\s*\{[\s\S]*?grid-template-rows:\s*repeat\(4, minmax\(32px, auto\)\)/,
  );
  assert.match(modePickerStyles, /width:\s*min\(768px, 100%\)/);
  assert.match(
    modePickerStyles,
    /\.agent-creation-mode-picker__options\s*\{[\s\S]*?grid-template-columns:\s*repeat\(2, 365px\);[\s\S]*?justify-content:\s*center;/,
  );
  assert.match(modePickerStyles, /height:\s*auto/);
  assert.doesNotMatch(modePickerStyles, /height:\s*299px/);
  assert.match(modePickerStyles, /border-radius:\s*16px/);
  assert.match(modePickerStyles, /box-shadow:\s*0 0 0 1px/);
  assert.match(modePickerStyles, /padding:\s*20px/);
  assert.match(modePickerStyles, /width:\s*40px;\s*\n\s*height:\s*40px/);
  assert.match(modePickerStyles, /border-radius:\s*10px/);
  assert.match(
    modePickerStyles,
    /\.agent-creation-mode-picker__card:hover\s*\{[\s\S]*?background:\s*transparent/,
  );
  assert.match(
    modePickerStyles,
    /\.agent-creation-mode-picker__card:active\s*\{[\s\S]*?background:\s*transparent/,
  );
  assert.match(modePickerStyles, /@media \(max-width: 640px\)/);
  assert.doesNotMatch(modePickerStyles, /position:\s*fixed/);
  assert.match(
    modePickerStyles,
    /\.agent-creation-mode-picker__header h1\s*\{[\s\S]*?font-size:\s*22px/,
  );
  assert.match(
    modePickerStyles,
    /\.agent-creation-mode-picker__header p\s*\{[\s\S]*?font-size:\s*16px/,
  );
  assert.doesNotMatch(
    modePickerStyles,
    /#[0-9a-f]{3,8}|gradient|purple|violet/i,
  );
});

test("creation entry and quick-mode workbench fade as complete pages", () => {
  assert.match(modePickerSource, /motion, useReducedMotion/);
  assert.match(modePickerSource, /<motion\.main/);
  assert.match(modePickerSource, /initial=\{reduceMotion \? false : \{ opacity: 0 \}\}/);
  assert.match(modePickerSource, /animate=\{\{ opacity: isLeaving \? 0 : 1 \}\}/);
  assert.match(modePickerSource, /duration: isLeaving \? 0\.12 : 0\.18/);
  assert.match(modePickerSource, /onAnimationComplete=\{finishTransition\}/);
  assert.match(modePickerStyles, /\.agent-creation-mode-picker\.is-leaving\s*\{[\s\S]*?pointer-events:\s*none/);

  assert.match(workbenchSource, /AnimatePresence, motion, useReducedMotion/);
  assert.match(workbenchSource, /<motion\.div[\s\S]*?className=\{`new-agent-workbench/);
  assert.match(workbenchSource, /initial=\{reduceMotion \? false : \{ opacity: 0 \}\}/);
  assert.match(workbenchSource, /animate=\{\{ opacity: isLeaving \? 0 : 1 \}\}/);
  assert.match(workbenchSource, /duration: isLeaving \? 0\.12 : 0\.18/);
  assert.match(workbenchSource, /onAnimationComplete=\{finishPageTransition\}/);
  assert.match(workbenchStyles, /\.new-agent-workbench\.is-leaving\s*\{[\s\S]*?pointer-events:\s*none/);
});

test("studio shell uses ElevenLabs-like sidebar neutrals and a white main canvas", () => {
  assert.match(globalStyles, /--canvas:\s*0 0% 100%/);
  assert.match(globalStyles, /--sidebar:\s*0 0% 98%/);
  assert.match(globalStyles, /--sidebar-item-hover:\s*0 0% 0% \/ 0\.043/);
  assert.match(globalStyles, /--sidebar-foreground:\s*240 5\.9% 10%/);
  assert.match(globalStyles, /--sidebar-item-foreground:\s*240 5\.3% 26\.1%/);
  assert.match(globalStyles, /--sidebar-section-title:\s*240 5\.3% 26\.1%/);
  assert.match(
    globalStyles,
    /\.new-chat\s*\{[\s\S]*?color:\s*hsl\(var\(--sidebar-item-foreground\)\)/,
  );
  assert.match(
    globalStyles,
    /\.new-chat\.is-active\s*\{[\s\S]*?color:\s*hsl\(var\(--sidebar-foreground\)\)/,
  );
});

test("workbench uses native Apps SDK UI controls", () => {
  for (const component of ["Button", "Input", "Select", "Textarea", "Switch"]) {
    assert.match(
      workbenchSource,
      new RegExp(`@openai/apps-sdk-ui/components/${component}`),
    );
  }
  assert.match(workbenchSource, /@openai\/apps-sdk-ui\/components\/Icon/);
});

test("workbench keeps the main-branch model fields and skill dialog on the first step", () => {
  assert.match(workbenchSource, /label: "智能体"/);
  assert.match(workbenchSource, /label: "执行环境"/);
  assert.match(workbenchSource, /label: "部署偏好"/);
  assert.match(
    workbenchSource,
    /className="new-agent-workbench__model-field-label">\s*模型来源\s*</,
  );
  assert.match(
    workbenchSource,
    />\s*API Key\s*<span className="new-agent-workbench__required">\*<\/span>/,
  );
  assert.match(
    workbenchSource,
    />\s*模型名称\s*<span className="new-agent-workbench__required">\*<\/span>/,
  );
  assert.match(workbenchSource, /服务商 Provider/);
  assert.match(workbenchSource, /API Base/);
  assert.match(workbenchSource, />技能</);
  assert.match(
    workbenchSource,
    /className="new-agent-workbench__model-group-label">\s*模型\s*</,
  );
  assert.match(
    workbenchStyles,
    /\.new-agent-workbench__model-group-label\s*\{[\s\S]*?font-size:\s*14px[\s\S]*?font-weight:\s*500/,
  );
  assert.match(
    workbenchStyles,
    /\.new-agent-workbench__model-field-label\s*\{[\s\S]*?color:\s*hsl\(var\(--muted-foreground\)\)[\s\S]*?font-size:\s*12px[\s\S]*?font-weight:\s*400/,
  );
  assert.match(workbenchSource, /OptionView=\{ModelSelectOptionView\}/);
  assert.match(
    workbenchSource,
    /searchPredicate=\{modelSelectSearchPredicate\}/,
  );
  assert.match(workbenchSource, /metadata: model\.vendorName/);
  assert.match(workbenchSource, /`\$\{model\.id\} \| \$\{model\.vendorName\}`/);
  assert.doesNotMatch(
    workbenchSource,
    /agentKitLogo|byteplusLogo|model-option-logo/,
  );
  assert.doesNotMatch(workbenchStyles, /model-option-logo/);
  assert.match(
    workbenchStyles,
    /\.new-agent-workbench__model-option-label\s*\{[\s\S]*?font-weight:\s*400/,
  );
  assert.match(
    workbenchStyles,
    /\.new-agent-workbench__model-option-metadata\s*\{[\s\S]*?color:\s*hsl\(var\(--muted-foreground\)\)[\s\S]*?font-weight:\s*400/,
  );
  assert.match(
    workbenchStyles,
    /\.new-agent-workbench__select-option\s*>\s*div\s*>\s*div:nth-child\(2\)\s*\{[\s\S]*?color:\s*hsl\(var\(--muted-foreground\)\)[\s\S]*?font-size:\s*12px[\s\S]*?font-weight:\s*400/,
  );
  assert.ok(
    (
      workbenchSource.match(/optionClassName=\{SELECT_OPTION_CLASS_NAME\}/g) ??
      []
    ).length >= 5,
  );
  assert.match(
    workbenchSource,
    /optionClassName=\{`\$\{SELECT_OPTION_CLASS_NAME\} new-agent-workbench__model-option`\}/,
  );
  assert.match(
    workbenchStyles,
    /\.new-agent-workbench \.cw-skill-add\s*\{[\s\S]*?min-height:\s*44px[\s\S]*?font-size:\s*13px[\s\S]*?font-weight:\s*400/,
  );
  const agentStep =
    workbenchSource.match(
      /\{step === "agent" \? \(([\s\S]*?)\{step === "environment" \? \(/,
    )?.[1] ?? "";
  const environmentStep =
    workbenchSource.match(
      /\{step === "environment" \? \(([\s\S]*?)\{step === "deployment" \? \(/,
    )?.[1] ?? "";
  assert.match(agentStep, /<NativeModelPicker/);
  assert.match(agentStep, /<SkillSourcePicker/);
  assert.match(workbenchSource, /addLabel="添加技能"/);
  assert.match(workbenchSource, /showSelectedCount=\{false\}/);
  assert.doesNotMatch(workbenchSource, /function LocalSkillsField/);
  assert.match(environmentStep, /<CloudEnvironmentConfigurator/);
  assert.doesNotMatch(environmentStep, /<NativeModelPicker|<LocalSkillsField/);
  assert.match(
    customCreateSource,
    /onCloudEnvironmentChange=\{updateCloudEnvironment\}/,
  );
  assert.doesNotMatch(workbenchSource, />工具</);
  assert.doesNotMatch(workbenchSource, />知识库</);
  assert.doesNotMatch(
    workbenchSource,
    />短期记忆|>长期记忆|>子智能体|>子 Agent/,
  );
});

test("quick-mode next action stays disabled while model data is loading", () => {
  assert.match(
    workbenchSource,
    /onLoadingChange:\s*\(loading: boolean\) => void/,
  );
  assert.match(
    workbenchSource,
    /onLoadingChange\([\s\S]*?source === "ark"[\s\S]*?loadingKeys[\s\S]*?loadingModels[\s\S]*?loadedModelsForApiKeyId !== apiKeyId/,
  );
  assert.match(
    workbenchSource,
    /const \[modelDataLoading, setModelDataLoading\] = useState\(true\)/,
  );
  assert.match(workbenchSource, /onLoadingChange=\{setModelDataLoading\}/);
  assert.match(
    workbenchSource,
    /disabled=\{[\s\S]*?deploying \|\| \(step === "agent" && modelDataLoading\)[\s\S]*?\}/,
  );
});

test("quick-mode selected skills keep long descriptions inside the form", () => {
  assert.match(
    workbenchStyles,
    /\.new-agent-workbench \.cw-skillspane,[\s\S]*?\.new-agent-workbench \.cw-selected-skill-row\s*\{[\s\S]*?width:\s*100%[\s\S]*?min-width:\s*0[\s\S]*?max-width:\s*100%[\s\S]*?box-sizing:\s*border-box/,
  );
  assert.match(
    skillSourcePickerSource,
    /className="cw-selected-skill-detail"[\s\S]*?tabIndex=\{0\}[\s\S]*?title=\{detail\}/,
  );
});

test("fresh Vulcan creation defaults to assistant and uses Google ADK name validation", () => {
  assert.match(
    customCreateSource,
    /const creationDraft = isFreshVulcanCreation[\s\S]*?name:[\s\S]*?:\s*"assistant"/,
  );
  assert.match(
    customCreateSource,
    /isFreshVulcanCreation[\s\S]*?dynamicAgentDelegation:\s*true/,
  );
  assert.doesNotMatch(
    workbenchSource,
    /CreateAgentToolset|collect_resources|create_agents|内置能力/,
  );
  assert.match(
    workbenchSource,
    /import \{ agentNameProblem \} from "\.\/agentNameValidation";/,
  );
  assert.match(
    workbenchSource,
    /const nameProblem = agentNameProblem\(draft\.name\)/,
  );
  assert.match(
    workbenchSource,
    /const showNameError = showAgentErrors \|\| nameValidationTouched/,
  );
  assert.match(workbenchSource, /invalid=\{showNameError && nameInvalid\}/);
  assert.match(
    workbenchSource,
    /onBlur=\{\(\) => setNameValidationTouched\(true\)\}/,
  );
  assert.match(
    workbenchSource,
    /onChange=\{\(event\) => \{[\s\S]*?setNameValidationTouched\(true\)[\s\S]*?onDraftPatch\(\{ name: event\.currentTarget\.value \}\)/,
  );
  assert.match(workbenchSource, /\{nameProblem\}/);
});

test("inline agent validation keeps the compact destructive style", () => {
  assert.match(
    workbenchStyles,
    /\.new-agent-workbench__error,\s*\.new-agent-workbench__field > \.new-agent-workbench__error\s*\{[\s\S]*?color:\s*hsl\(var\(--destructive\)\);[\s\S]*?font-size:\s*12px;/,
  );
});

test("Vulcan creation is a fixed-size three-step wizard", () => {
  assert.match(
    workbenchSource,
    /type WizardStep = "agent" \| "environment" \| "deployment"/,
  );
  assert.match(workbenchSource, /title: "基本信息"/);
  assert.match(workbenchSource, /title: "配置执行环境"/);
  assert.match(workbenchSource, /title: "部署偏好"/);
  assert.match(workbenchSource, /description: "定义 AgentKit 云上参数"/);
  assert.match(workbenchSource, /className="new-agent-workbench__panel"/);
  assert.match(workbenchSource, /className="new-agent-workbench__panel-frame"/);
  assert.match(workbenchSource, /className="new-agent-workbench__actions"/);
  assert.match(workbenchSource, /className="new-agent-workbench__footer"/);
  assert.match(workbenchSource, /className="new-agent-workbench__progress"/);
  assert.match(
    workbenchSource,
    /<AnimatePresence mode="wait" initial=\{false\}>/,
  );
  assert.match(workbenchSource, /exit=\{\{ opacity: 0 \}\}/);
  assert.match(workbenchSource, /key=\{`heading-\$\{step\}`\}/);
  assert.match(workbenchSource, /key=\{`actions-\$\{step\}`\}/);
  assert.match(workbenchSource, /new ResizeObserver\(updatePanelFades\)/);
  assert.match(workbenchSource, /new MutationObserver\(updatePanelFades\)/);
  assert.match(workbenchSource, /new-agent-workbench__scroll-fade is-top/);
  assert.match(workbenchSource, /new-agent-workbench__scroll-fade is-bottom/);
  assert.match(
    workbenchSource,
    /panel\.scrollTo\(\{ top: 0, behavior: "auto" \}\)/,
  );
  assert.match(workbenchStyles, /height:\s*min\(760px, 100%\)/);
  assert.match(workbenchStyles, /overflow-y:\s*auto/);
  assert.match(
    workbenchStyles,
    /\.new-agent-workbench__scroll-fade\.is-top\s*\{[\s\S]*?linear-gradient\(to bottom/,
  );
  assert.match(
    workbenchStyles,
    /\.new-agent-workbench__scroll-fade\.is-bottom\s*\{[\s\S]*?linear-gradient\(to top/,
  );
  assert.match(
    workbenchStyles,
    /grid-template-rows:\s*auto minmax\(0, 1fr\) auto/,
  );
  assert.match(
    workbenchSource,
    /className="new-agent-workbench__heading"[\s\S]*?className="new-agent-workbench__panel"/,
  );
  assert.match(workbenchStyles, /width:\s*6px;\s*\n\s*height:\s*6px/);
  assert.match(
    workbenchStyles,
    /li\.is-active > span\s*\{\s*\n\s*width:\s*20px/,
  );
  assert.match(
    workbenchStyles,
    /\.new-agent-workbench__progress\s*\{[\s\S]*?gap:\s*8px/,
  );
  assert.doesNotMatch(
    workbenchStyles,
    /\.new-agent-workbench__footer\s*\{[\s\S]*?border-top/,
  );
  assert.match(workbenchSource, /<ChevronLeft aria-hidden \/>/);
  assert.ok(
    (workbenchSource.match(/className="new-agent-workbench__required"/g) ?? [])
      .length >= 6,
  );
  assert.match(
    workbenchStyles,
    /\.new-agent-workbench__heading h1\s*\{[\s\S]*?font-size:\s*22px/,
  );
  assert.match(
    workbenchStyles,
    /\.new-agent-workbench__heading p\s*\{[\s\S]*?font-size:\s*16px/,
  );
  assert.doesNotMatch(workbenchSource, /description: "[^"]*。"/);
  assert.match(
    workbenchStyles,
    /\.new-agent-workbench__actions\s*\{[\s\S]*?justify-content:\s*space-between/,
  );
  assert.doesNotMatch(workbenchStyles, /position:\s*fixed/);
  assert.match(
    workbenchStyles,
    /\.new-agent-workbench__footer-inner\s*\{[\s\S]*?justify-content:\s*center/,
  );
  assert.match(
    workbenchStyles,
    /\.new-agent-workbench__field\s*\{[\s\S]*?gap:\s*4px/,
  );
  assert.match(
    workbenchStyles,
    /\.new-agent-workbench__field\s*\{[\s\S]*?font-weight:\s*500/,
  );
  assert.match(workbenchStyles, /--control-font-size-lg:\s*0\.875rem/);
  assert.match(
    workbenchStyles,
    /--input-outline-border-color:\s*hsl\(var\(--foreground\) \/ 0\.1\)/,
  );
  assert.match(
    workbenchStyles,
    /--input-outline-border-color-hover:\s*hsl\(var\(--foreground\) \/ 0\.18\)/,
  );
  assert.match(
    workbenchStyles,
    /--input-outline-border-color-focus:\s*hsl\(var\(--foreground\)\)/,
  );
  assert.doesNotMatch(workbenchStyles, /box-shadow:\s*0 0 0 (?:1\.5|2)px/);
  assert.ok((workbenchSource.match(/size="xl"/g) ?? []).length >= 10);
  assert.ok((workbenchSource.match(/gutterSize="md"/g) ?? []).length >= 8);
  assert.ok(
    (
      workbenchSource.match(
        /triggerClassName="new-agent-workbench__select-trigger"/g,
      ) ?? []
    ).length >= 4,
  );
  assert.match(
    workbenchSource,
    /<CloudEnvironmentConfigurator[\s\S]*?controlSize="xl"/,
  );
  assert.match(
    workbenchSource,
    /<CloudEnvironmentConfigurator[\s\S]*?controlClassName="new-agent-workbench__select-trigger"/,
  );
  assert.match(
    workbenchStyles,
    /\.new-agent-workbench__select-trigger\s*\{[\s\S]*?font-weight:\s*400[\s\S]*?padding-inline:\s*12px/,
  );
});

test("Vulcan workbench is white and omits navigation and debugging", () => {
  assert.match(
    workbenchStyles,
    /\.new-agent-workbench\s*\{[\s\S]*?background:\s*hsl\(var\(--background\)\)/,
  );
  assert.doesNotMatch(
    workbenchSource,
    /new-agent-workbench__header|new-agent-workbench__debugger/,
  );
  assert.doesNotMatch(
    workbenchSource,
    /DebugSession|debugInput|onStartDebug|onSendDebug|onOpenTrace/,
  );
  assert.doesNotMatch(
    customCreateSource,
    /<NewAgentWorkbench[\s\S]*?debugEnabled=/,
  );
  assert.doesNotMatch(
    customCreateSource,
    /if \(!usesNewAgentWorkbench\)[\s\S]*?setDebugVariants/,
  );
  assert.doesNotMatch(
    workbenchSource,
    />\s*对话调试\s*<|<CompactComposer|<Blocks/,
  );
});

test("final step exposes deployment progress and error feedback", () => {
  assert.match(workbenchSource, /onDeploy/);
  assert.match(workbenchSource, /deploying/);
  assert.match(workbenchSource, /deployStage/);
  assert.match(workbenchSource, /deployError/);
  assert.match(workbenchSource, /role="alert"/);
  for (const label of [
    "会话存储",
    "实例设置",
    "评测集",
    "资源配置",
    "环境变量",
  ]) {
    assert.match(workbenchSource, new RegExp(label));
  }
  assert.doesNotMatch(workbenchSource, />\s*访问鉴权\s*</);
  assert.match(workbenchSource, />\s*鉴权方式\s*</);
  assert.doesNotMatch(
    workbenchSource,
    /new-agent-workbench__section-title">\s*网络\s*</,
  );
  assert.match(workbenchSource, />\s*网络模式\s*</);
  assert.match(
    workbenchSource,
    /sessionStorage: "in-memory" \| "persistent"/,
  );
  assert.match(
    workbenchSource,
    /SESSION_STORAGE_BACKEND_IDS = \[[\s\S]*?"local"[\s\S]*?"sqlite"[\s\S]*?"mysql"[\s\S]*?"postgresql"/,
  );
  assert.match(
    workbenchSource,
    /backend === "local" \? "in-memory" : "persistent"/,
  );
  assert.match(workbenchSource, /options=\{STM_BACKENDS\.map/);
  assert.match(workbenchSource, /option\.id === "local"\s*\? "In-memory 临时存储"\s*:\s*option\.label/);
  assert.doesNotMatch(
    workbenchSource,
    /options=\{STM_BACKENDS\.map\([\s\S]*?description:\s*option\.desc/,
  );
  assert.doesNotMatch(workbenchSource, />\s*消息渠道\s*</);
  assert.doesNotMatch(workbenchSource, /aria-label="启用飞书"/);
  assert.match(
    workbenchSource,
    /shortTerm: option\.value !== "local"[\s\S]*?shortTermBackend: option\.value/,
  );
  assert.match(
    workbenchSource,
    /setMaxInstance\(sessionStorage === "in-memory" \? "1" : "5"\)/,
  );
  assert.match(
    workbenchSource,
    /onDeploy\(\{[\s\S]*?sessionStorage,[\s\S]*?sessionBackend,/,
  );
  assert.match(
    workbenchSource,
    /className="new-agent-workbench__instance-fields"[\s\S]*?className="new-agent-workbench__model-field-label">\s*最小实例数[\s\S]*?className="new-agent-workbench__model-field-label">\s*最大实例数/,
  );
  assert.match(
    workbenchSource,
    /role="table"[\s\S]*?aria-label="环境变量"[\s\S]*?role="columnheader">名称[\s\S]*?role="columnheader">值[\s\S]*?role="columnheader">操作/,
  );
  assert.match(
    workbenchStyles,
    /\.new-agent-workbench__env-table-head,[\s\S]*?\.new-agent-workbench__env-row\s*\{[\s\S]*?grid-template-columns:/,
  );
  assert.match(
    customCreateSource,
    /authentication: deploymentOptions\.authentication/,
  );
  assert.match(
    customCreateSource,
    /minInstance: deploymentOptions\.minInstance/,
  );
  assert.match(
    customCreateSource,
    /maxInstance: deploymentOptions\.maxInstance/,
  );
  assert.match(
    customCreateSource,
    /sessionStorage: deploymentOptions\.sessionStorage/,
  );
  assert.match(
    customCreateSource,
    /shortTerm: deploymentOptions\.sessionBackend !== "local"[\s\S]*?shortTermBackend: deploymentOptions\.sessionBackend/,
  );
  assert.match(
    customCreateSource,
    /firstMissingRuntimeEnv\(activeEnvSpecs, allEnvValues\)/,
  );
  assert.match(
    customCreateSource,
    /generateAgentProject\([\s\S]*?codegenDraft\(deploymentDraft\)[\s\S]*?\)/,
  );
  assert.match(customCreateSource, /resources: deploymentOptions\.resources/);
});

test("quick-mode session backends reuse the main-branch short-term memory catalog", () => {
  for (const label of ["本地内存", "SQLite 文件", "MySQL", "PostgreSQL"]) {
    assert.match(catalogSource, new RegExp(label));
  }
  for (const key of [
    "DATABASE_MYSQL_HOST",
    "DATABASE_MYSQL_USER",
    "DATABASE_MYSQL_PASSWORD",
    "DATABASE_MYSQL_DATABASE",
    "DATABASE_POSTGRESQL_HOST",
    "DATABASE_POSTGRESQL_PORT",
    "DATABASE_POSTGRESQL_USER",
    "DATABASE_POSTGRESQL_PASSWORD",
    "DATABASE_POSTGRESQL_DATABASE",
  ]) {
    assert.match(catalogSource, new RegExp(key));
  }
  assert.match(workbenchSource, /sessionEnvSpecs\.map/);
  assert.match(workbenchSource, /locked/);
});

test("deployment helper and environment variable copy use their intended text roles", () => {
  assert.match(
    workbenchSource,
    /className="new-agent-workbench__helper-text">\s*为避免多实例间会话丢失/,
  );
  assert.match(
    workbenchStyles,
    /\.new-agent-workbench__helper-text\s*\{[\s\S]*?color:\s*hsl\(var\(--muted-foreground\)\);[\s\S]*?font-size:\s*12px;[\s\S]*?font-weight:\s*400;[\s\S]*?line-height:\s*16px;/,
  );
  assert.match(
    workbenchStyles,
    /\.new-agent-workbench__env-head > button,[\s\S]*?\.new-agent-workbench__empty-row\s*\{[\s\S]*?font-size:\s*14px;[\s\S]*?line-height:\s*20px;/,
  );
  assert.match(workbenchSource, /<span role="cell">无<\/span>/);
  assert.doesNotMatch(workbenchSource, /此后端无需额外运行参数/);
});
