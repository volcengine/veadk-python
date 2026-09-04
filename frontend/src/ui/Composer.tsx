import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { ComponentType, SVGProps } from "react";
import {
  AtSign,
  Bot,
  Check,
  Copy,
  FileText,
  FileVideo2,
  ImageIcon,
  Loader2,
  MonitorPlay,
  Plus,
  Sparkles,
  X,
} from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useTranslation } from "react-i18next";
import type {
  AgentSkill,
  AgentTarget,
  Attachment,
  CloudRuntime,
  FrontendInvocation,
  RuntimeScope,
} from "../adk/client";
import type { CloudProvider } from "../adk/cloudProvider";
import type { RuntimeLogTarget } from "../adk/runtimeLogs";
import type { SessionTokenUsage } from "../adk/tokenUsage";
import { getVideoCapabilities, type VideoCapabilities } from "../adk/video";
import type { SandboxAgentResource } from "../adk/sandbox";
import { InvocationChips } from "./InvocationChips";
import { MediaGroup } from "./Media";
import { isImeCompositionEvent } from "./composerKeyboard";
import { ComposerSendIcon, ComposerStopIcon } from "./icons/ComposerIcons";
import { SandboxTerminalIcon } from "./icons/SandboxControlIcons";
import { NewChatModeSelector } from "./new-chat-modes/NewChatModeSelector";
import { NewChatAgentPicker } from "./new-chat-modes/NewChatAgentPicker";
import { NewChatSkillControls } from "./new-chat-modes/NewChatSkillControls";
import {
  NewChatInlineAssetInput,
  NewChatVideoControls,
} from "./new-chat-modes/NewChatVideoControls";
import { NewChatWorkspaceTabs } from "./new-chat-modes/NewChatWorkspaceTabs";
import { NewChatCompactSelect } from "./new-chat-modes/NewChatCompactSelect";
import {
  DEFAULT_NEW_CHAT_VIDEO_CONFIG,
  videoTaskModeOptions,
  type NewChatVideoConfig,
  type VideoTaskMode,
} from "./new-chat-modes/video-types";
import {
  isVideoTaskRunning,
  type VideoGenerationTask,
} from "./new-chat-modes/video-task";
import type {
  NewChatMode,
  NewChatSkillAction,
  NewChatSkillTarget,
  NewChatTask,
  NewChatWorkspaceMode,
} from "./new-chat-modes/types";
import { NEW_CHAT_TASK_TOOLS } from "./new-chat-modes/taskTools";
import { VideoGenerateIcon } from "./builtin-tools/icons";
import { TokenUsageIndicator } from "./TokenUsageIndicator";
import { RuntimeLogsDialog } from "./RuntimeLogsDialog";

interface CompletionTrigger {
  kind: "skill" | "agent";
  query: string;
  start: number;
  end: number;
}

type CompletionItem =
  { kind: "skill"; value: AgentSkill } | { kind: "agent"; value: AgentTarget };

const TASK_SHORTCUTS = [
  {
    value: "ppt",
    icon: MonitorPlay,
    prompts: [
      "composer.prompts.ppt.quarterlyReview",
      "composer.prompts.ppt.projectUpdate",
      "composer.prompts.ppt.solutionProposal",
      "composer.prompts.ppt.industryAnalysis",
    ],
  },
  {
    value: "image",
    icon: ImageIcon,
    prompts: [
      "composer.prompts.image.launchVisual",
      "composer.prompts.image.ecommercePoster",
      "composer.prompts.image.conceptRendering",
      "composer.prompts.image.socialGraphic",
    ],
  },
  {
    value: "video",
    icon: VideoGenerateIcon,
    prompts: [
      "composer.prompts.video.brandFilm",
      "composer.prompts.video.productLaunch",
      "composer.prompts.video.trainingVideo",
      "composer.prompts.video.eventTeaser",
    ],
  },
] as const satisfies ReadonlyArray<{
  value: NewChatTask;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  prompts: readonly string[];
}>;

export interface ComposerProps {
  cloudProvider: CloudProvider;
  sessionId: string;
  sessionInitializing?: boolean;
  appName: string;
  agentName: string;
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  onStop?: () => void;
  onVideoSubmit?: (
    prompt: string,
    config: NewChatVideoConfig,
    capabilities: VideoCapabilities,
  ) => void;
  videoTask?: VideoGenerationTask | null;
  onOpenVideoTask?: () => void;
  disabled: boolean; // not connected yet
  busy: boolean; // a turn is streaming
  showMeta: boolean;
  attachments: Attachment[];
  skills: AgentSkill[];
  agents: AgentTarget[];
  invocation: FrontendInvocation;
  capabilitiesLoading?: boolean;
  modelName: string;
  tokenUsage: SessionTokenUsage;
  systemTokenEstimate: number | null;
  allowAttachments?: boolean;
  onInvocationChange: (value: FrontendInvocation) => void;
  onAddFiles: (files: FileList | File[]) => void;
  onRemoveAttachment: (id: string) => void;
  newChatMode?: NewChatMode;
  newChatWorkspaceMode?: NewChatWorkspaceMode;
  newChatSkillAction?: NewChatSkillAction;
  newChatSkillTarget?: NewChatSkillTarget | null;
  skillCustomizationEnabled?: boolean;
  newChatTask?: NewChatTask | null;
  newChatLayout?: boolean;
  showWorkspaceTabs?: boolean;
  showModeSelector?: boolean;
  onWorkspaceModeChange?: (value: NewChatWorkspaceMode) => void;
  onSkillActionChange?: (value: NewChatSkillAction) => void;
  onSkillTargetChange?: (value: NewChatSkillTarget | null) => void;
  onModeChange?: (value: NewChatMode) => void;
  onTaskChange?: (value: NewChatTask | null) => void;
  temporaryEnabled?: boolean;
  deepseekHarnessEnabled?: boolean;
  harnessEnabled?: boolean;
  builtinTools?: readonly string[];
  showAgentPicker?: boolean;
  agentPickerDisabled?: boolean;
  selectedRuntimeId?: string;
  agentsSource?: "local" | "cloud";
  localApps?: string[];
  runtimeScope?: RuntimeScope;
  onSelectLocalApp?: (app: string) => Promise<void>;
  onSelectRuntime?: (runtime: CloudRuntime) => Promise<void>;
  onSelectSandboxSession?: (session: SandboxAgentResource) => Promise<void>;
  runtimeLogTarget?: RuntimeLogTarget;
}

export function Composer({
  cloudProvider,
  sessionId,
  sessionInitializing = false,
  appName,
  agentName,
  value,
  onChange,
  onSubmit,
  onStop,
  onVideoSubmit,
  videoTask = null,
  onOpenVideoTask,
  disabled,
  busy,
  showMeta,
  attachments,
  skills,
  agents,
  invocation,
  capabilitiesLoading = false,
  modelName,
  tokenUsage,
  systemTokenEstimate,
  allowAttachments = true,
  onInvocationChange,
  onAddFiles,
  onRemoveAttachment,
  newChatMode = "agent",
  newChatWorkspaceMode = "agent",
  newChatSkillAction = "create",
  newChatSkillTarget = null,
  skillCustomizationEnabled = false,
  newChatTask = null,
  newChatLayout = false,
  showWorkspaceTabs = false,
  showModeSelector = false,
  onWorkspaceModeChange,
  onSkillActionChange,
  onSkillTargetChange,
  onModeChange,
  onTaskChange,
  temporaryEnabled,
  deepseekHarnessEnabled,
  harnessEnabled = false,
  builtinTools = [],
  showAgentPicker = false,
  agentPickerDisabled = false,
  selectedRuntimeId = "",
  agentsSource = "cloud",
  localApps = [],
  runtimeScope = "mine",
  onSelectLocalApp,
  onSelectRuntime,
  onSelectSandboxSession,
  runtimeLogTarget,
}: ComposerProps) {
  const { t } = useTranslation("ui");
  const ref = useRef<HTMLTextAreaElement>(null);
  const imageInput = useRef<HTMLInputElement>(null);
  const documentInput = useRef<HTMLInputElement>(null);
  const videoInput = useRef<HTMLInputElement>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [trigger, setTrigger] = useState<CompletionTrigger | null>(null);
  const [activeIndex, setActiveIndex] = useState(0);
  const [sessionIdCopied, setSessionIdCopied] = useState(false);
  const [runtimeLogsOpen, setRuntimeLogsOpen] = useState(false);
  const [newChatVideoConfig, setNewChatVideoConfig] = useState(
    DEFAULT_NEW_CHAT_VIDEO_CONFIG,
  );
  const [videoCapabilities, setVideoCapabilities] =
    useState<VideoCapabilities | null>(null);
  const [videoCapabilitiesLoading, setVideoCapabilitiesLoading] =
    useState(false);
  const [videoCapabilitiesError, setVideoCapabilitiesError] = useState("");

  useEffect(() => {
    if (!newChatLayout || newChatWorkspaceMode !== "video") return;
    const controller = new AbortController();
    setVideoCapabilitiesLoading(true);
    setVideoCapabilitiesError("");
    void getVideoCapabilities(controller.signal)
      .then((capabilities) => {
        if (!controller.signal.aborted) setVideoCapabilities(capabilities);
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) {
          setVideoCapabilities(null);
          setVideoCapabilitiesError(
            cause instanceof Error ? cause.message : String(cause),
          );
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setVideoCapabilitiesLoading(false);
      });
    return () => controller.abort();
  }, [cloudProvider, newChatLayout, newChatWorkspaceMode]);

  useEffect(() => {
    if (
      !videoCapabilities?.supportedModes.length ||
      newChatVideoConfig.taskMode === "auto" ||
      videoCapabilities.supportedModes.includes(newChatVideoConfig.taskMode)
    )
      return;
    setNewChatVideoConfig((current) => ({
      ...current,
      taskMode: videoCapabilities.supportedModes[0],
    }));
  }, [newChatVideoConfig.taskMode, videoCapabilities]);

  async function copySessionId() {
    if (!sessionId) return;
    try {
      await navigator.clipboard.writeText(sessionId);
      setSessionIdCopied(true);
      setTimeout(() => setSessionIdCopied(false), 1500);
    } catch {
      setSessionIdCopied(false);
    }
  }

  // Auto-grow the textarea up to a max height, then scroll.
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [value]);

  const uploadPending = attachments.some(
    (attachment) => attachment.status !== "ready",
  );
  const videoMode = newChatLayout && newChatWorkspaceMode === "video";
  const videoModeOptions = videoTaskModeOptions();
  const requiredInlineAsset = !videoMode
    ? null
    : newChatVideoConfig.taskMode === "first_last_frame"
      ? {
          asset: newChatVideoConfig.firstFrame,
          kind: "image" as const,
          label: t("composer.firstFrame"),
        }
      : newChatVideoConfig.taskMode === "video_editing" ||
          newChatVideoConfig.taskMode === "video_extension"
        ? {
            asset: newChatVideoConfig.referenceVideo,
            kind: "video" as const,
            label:
              newChatVideoConfig.taskMode === "video_editing"
                ? t("composer.videoToEdit")
                : t("composer.baseVideo"),
          }
        : null;
  const videoTaskRunning = isVideoTaskRunning(videoTask);
  const canOpenVideoTask = videoMode && Boolean(videoTask) && !value.trim();
  const canStop = busy && Boolean(onStop);
  const canSend = videoMode
    ? videoTaskRunning ||
      canOpenVideoTask ||
      (!disabled &&
        !busy &&
        !uploadPending &&
        (!requiredInlineAsset || Boolean(requiredInlineAsset.asset)) &&
        Boolean(videoCapabilities) &&
        value.trim().length > 0)
    : !disabled &&
      !busy &&
      !uploadPending &&
      (value.trim().length > 0 || attachments.length > 0);

  function submitComposer() {
    if (videoMode) {
      if (videoTaskRunning || canOpenVideoTask) {
        onOpenVideoTask?.();
        return;
      }
      if (videoCapabilities && value.trim()) {
        onVideoSubmit?.(value.trim(), newChatVideoConfig, videoCapabilities);
      }
      return;
    }
    onSubmit();
  }
  const workspacePlaceholder =
    newChatWorkspaceMode === "skill"
      ? newChatSkillAction === "optimize"
        ? t("composer.optimizeSkillPlaceholder")
        : t("composer.createSkillPlaceholder")
      : newChatWorkspaceMode === "video"
        ? t("composer.createVideoPlaceholder")
        : t("composer.messageAgentPlaceholder", { name: agentName });
  const placeholderText =
    disabled && newChatWorkspaceMode === "agent"
      ? t("composer.selectAgentFirst")
      : disabled &&
          newChatWorkspaceMode === "skill" &&
          newChatSkillAction === "optimize" &&
          !newChatSkillTarget
        ? t("composer.selectSkillFirst")
        : workspacePlaceholder;

  const query = trigger?.query.toLocaleLowerCase() ?? "";
  const suggestions: CompletionItem[] =
    trigger?.kind === "skill"
      ? skills
          .filter(
            (skill) =>
              !invocation.skills.some(
                (selected) => selected.name === skill.name,
              ),
          )
          .filter((skill) =>
            `${skill.name} ${skill.description}`
              .toLocaleLowerCase()
              .includes(query),
          )
          .map((value) => ({ kind: "skill" as const, value }))
      : trigger?.kind === "agent"
        ? agents
            .filter((agent) =>
              `${agent.name} ${agent.description}`
                .toLocaleLowerCase()
                .includes(query),
            )
            .map((value) => ({ kind: "agent" as const, value }))
        : [];

  function pick(input: React.RefObject<HTMLInputElement | null>) {
    setMenuOpen(false);
    setTrigger(null);
    input.current?.click();
  }

  function applyTaskShortcut(task: (typeof TASK_SHORTCUTS)[number]) {
    onTaskChange?.(task.value);
    setMenuOpen(false);
    setTrigger(null);
    requestAnimationFrame(() => {
      ref.current?.focus();
      ref.current?.setSelectionRange(value.length, value.length);
    });
  }

  function applyTaskPrompt(prompt: string) {
    onChange(prompt);
    setMenuOpen(false);
    setTrigger(null);
    requestAnimationFrame(() => {
      ref.current?.focus();
      const placeholderStart = prompt.indexOf("【");
      const placeholderEnd = prompt.indexOf("】", placeholderStart + 1);
      if (placeholderStart >= 0 && placeholderEnd > placeholderStart) {
        ref.current?.setSelectionRange(placeholderStart + 1, placeholderEnd);
      } else {
        ref.current?.setSelectionRange(prompt.length, prompt.length);
      }
    });
  }

  function clearTask() {
    onTaskChange?.(null);
    onChange("");
    setMenuOpen(false);
    setTrigger(null);
    requestAnimationFrame(() => {
      ref.current?.focus();
      ref.current?.setSelectionRange(0, 0);
    });
  }

  const selectedTask = TASK_SHORTCUTS.find(
    (task) => task.value === newChatTask,
  );
  const availableTaskShortcuts = TASK_SHORTCUTS.filter((task) =>
    NEW_CHAT_TASK_TOOLS[task.value].every((tool) =>
      builtinTools.includes(tool),
    ),
  );

  function updateCompletion(nextValue: string, cursor: number) {
    const prefix = nextValue.slice(0, cursor);
    const match = /(^|\s)([/@])([^\s/@]*)$/.exec(prefix);
    if (!match) {
      setTrigger(null);
      return;
    }
    const tokenLength = match[2].length + match[3].length;
    const nextTrigger: CompletionTrigger = {
      kind: match[2] === "/" ? "skill" : "agent",
      query: match[3],
      start: cursor - tokenLength,
      end: cursor,
    };
    const completionChanged =
      !trigger ||
      trigger.kind !== nextTrigger.kind ||
      trigger.query !== nextTrigger.query ||
      trigger.start !== nextTrigger.start ||
      trigger.end !== nextTrigger.end;
    setTrigger(nextTrigger);
    if (completionChanged) setActiveIndex(0);
    setMenuOpen(false);
  }

  function choose(item: CompletionItem) {
    if (!trigger) return;
    const nextValue = value.slice(0, trigger.start) + value.slice(trigger.end);
    onChange(nextValue);
    if (item.kind === "skill") {
      onInvocationChange({
        ...invocation,
        skills: [...invocation.skills, item.value],
      });
    } else {
      onInvocationChange({ skills: [], targetAgent: item.value });
    }
    const cursor = trigger.start;
    setTrigger(null);
    requestAnimationFrame(() => {
      ref.current?.focus();
      ref.current?.setSelectionRange(cursor, cursor);
    });
  }

  function removeLastInvocation() {
    if (invocation.targetAgent) {
      onInvocationChange({ skills: [] });
      return;
    }
    if (invocation.skills.length > 0) {
      onInvocationChange({
        ...invocation,
        skills: invocation.skills.slice(0, -1),
      });
    }
  }

  function onInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    const selected = e.target.files ? Array.from(e.target.files) : [];
    if (selected.length) onAddFiles(selected);
    e.target.value = ""; // allow re-picking the same file
  }

  return (
    <div
      className={`composer${newChatLayout ? " composer--new-chat" : ""}${selectedTask ? ` composer--has-task composer--task-${selectedTask.value}` : ""}`}
    >
      <InvocationChips
        value={invocation}
        onRemoveSkill={(name) =>
          onInvocationChange({
            ...invocation,
            skills: invocation.skills.filter((skill) => skill.name !== name),
          })
        }
        onRemoveAgent={() => onInvocationChange({ skills: [] })}
      />
      {attachments.length > 0 && (
        <MediaGroup
          appName={appName}
          compact
          items={attachments}
          onRemove={onRemoveAttachment}
        />
      )}

      {newChatLayout && showWorkspaceTabs && onWorkspaceModeChange ? (
        <NewChatWorkspaceTabs
          value={newChatWorkspaceMode}
          onChange={onWorkspaceModeChange}
          disabled={busy}
          skillCustomizationEnabled={skillCustomizationEnabled}
        />
      ) : null}

      <div
        id={
          newChatLayout && showWorkspaceTabs
            ? "new-chat-workspace-panel"
            : undefined
        }
        className="composer-box"
        role={newChatLayout && showWorkspaceTabs ? "tabpanel" : undefined}
        aria-labelledby={
          newChatLayout && showWorkspaceTabs
            ? `new-chat-workspace-tab-${newChatWorkspaceMode}`
            : undefined
        }
      >
        {trigger ? (
          <div
            className="composer-command-menu"
            role="listbox"
            aria-label={trigger.kind === "skill" ? t("composer.availableSkills") : t("composer.availableSubagents")}
          >
            <div className="composer-command-head">
              {trigger.kind === "skill" ? <Sparkles /> : <AtSign />}
              <span>
                {trigger.kind === "skill" ? t("composer.invokeSkill") : t("composer.useSubagent")}
              </span>
              <kbd>{trigger.kind === "skill" ? "/" : "@"}</kbd>
            </div>
            {capabilitiesLoading ? (
              <div className="composer-command-empty">
                <Loader2 className="spin" /> {t("composer.loadingCapabilities")}
              </div>
            ) : suggestions.length === 0 ? (
              <div className="composer-command-empty">
                {trigger.kind === "skill"
                  ? t("composer.noMatchingSkills")
                  : t("composer.noMatchingSubagents")}
              </div>
            ) : (
              <div className="composer-command-list">
                {suggestions.map((item, index) => (
                  <button
                    type="button"
                    role="option"
                    aria-selected={index === activeIndex}
                    className={`composer-command-item${index === activeIndex ? " is-active" : ""}`}
                    key={`${item.kind}-${item.value.name}`}
                    onMouseDown={(event) => {
                      event.preventDefault();
                      choose(item);
                    }}
                    onMouseEnter={() => setActiveIndex(index)}
                  >
                    <span
                      className={`composer-command-icon composer-command-icon--${item.kind}`}
                    >
                      {item.kind === "skill" ? <Sparkles /> : <Bot />}
                    </span>
                    <span className="composer-command-copy">
                      <strong>
                        {item.kind === "skill" ? "/" : "@"}
                        {item.value.name}
                      </strong>
                      <span>
                        {item.value.description ||
                          (item.kind === "skill"
                            ? t("composer.skillFallbackDescription")
                            : t("composer.agentFallbackDescription"))}
                      </span>
                    </span>
                    <kbd>
                      {index === activeIndex
                        ? "↵"
                        : item.kind === "skill"
                          ? t("composer.skill")
                          : "Agent"}
                    </kbd>
                  </button>
                ))}
              </div>
            )}
          </div>
        ) : null}
        <div className="composer-menu-wrap">
          <button
            type="button"
            className="comp-icon"
            title={t("common.add")}
            aria-label={t("common.add")}
            disabled={disabled || !allowAttachments}
            onClick={() => {
              setTrigger(null);
              setMenuOpen((o) => !o);
            }}
          >
            <Plus className="icon" />
          </button>
          {menuOpen && (
            <>
              <div className="menu-scrim" onClick={() => setMenuOpen(false)} />
              <div className="composer-menu" role="menu">
                <button
                  type="button"
                  className="menu-item"
                  onClick={() => pick(imageInput)}
                >
                  <ImageIcon className="icon" />
                  {t("composer.uploadImage")}
                </button>
                <button
                  type="button"
                  className="menu-item"
                  onClick={() => pick(documentInput)}
                >
                  <FileText className="icon" />
                  {t("composer.uploadDocument")}
                </button>
                <button
                  type="button"
                  className="menu-item"
                  onClick={() => pick(videoInput)}
                >
                  <FileVideo2 className="icon" />
                  {t("composer.uploadVideo")}
                </button>
              </div>
            </>
          )}
        </div>

        {newChatWorkspaceMode === "agent" &&
        showAgentPicker &&
        onSelectRuntime &&
        onSelectSandboxSession ? (
          <NewChatAgentPicker
            selectedAgentName={appName ? agentName : ""}
            selectedRuntimeId={selectedRuntimeId}
            agentsSource={agentsSource}
            localApps={localApps}
            runtimeScope={runtimeScope}
            disabled={agentPickerDisabled}
            onSelectLocalApp={onSelectLocalApp}
            onSelectRuntime={onSelectRuntime}
            onSelectSandboxSession={onSelectSandboxSession}
          />
        ) : null}

        {newChatLayout &&
        newChatWorkspaceMode === "skill" &&
        onSkillActionChange ? (
          <NewChatSkillControls
            action={newChatSkillAction}
            onActionChange={onSkillActionChange}
            optimizationSource={newChatSkillTarget}
            onOptimizationSourceChange={onSkillTargetChange}
            disabled={busy}
          />
        ) : null}

        {newChatLayout && newChatWorkspaceMode === "video" ? (
          <>
            <div className="new-chat-video-task-mode">
              <NewChatCompactSelect
                label={t("composer.taskMode")}
                hideLabel
                value={newChatVideoConfig.taskMode}
                options={
                  videoCapabilities?.supportedModes?.length
                    ? videoModeOptions.filter(
                        (option) =>
                          option.value === "auto" ||
                          videoCapabilities.supportedModes.includes(
                            option.value as VideoTaskMode,
                          ),
                      )
                    : videoModeOptions
                }
                onChange={(taskMode) =>
                  setNewChatVideoConfig((current) => ({
                    ...current,
                    taskMode: taskMode as VideoTaskMode,
                  }))
                }
                placeholder={t("composer.selectTaskMode")}
                disabled={
                  busy ||
                  videoTaskRunning ||
                  videoCapabilitiesLoading ||
                  !videoCapabilities
                }
              />
            </div>
            <div
              className="new-chat-video-generation-model"
              title={
                videoCapabilitiesError || videoCapabilities?.generationModel
              }
            >
              {videoCapabilitiesLoading ? (
                <Loader2
                  className="icon spin"
                  role="status"
                  aria-label={t("composer.loadingGenerationModel")}
                />
              ) : (
                <strong>
                  {videoCapabilities?.generationModel || t("composer.modelUnavailable")}
                </strong>
              )}
            </div>
          </>
        ) : null}

        {showModeSelector && onModeChange ? (
          <NewChatModeSelector
            value={newChatMode}
            onChange={onModeChange}
            disabled={busy}
            temporaryEnabled={temporaryEnabled}
            deepseekHarnessEnabled={deepseekHarnessEnabled}
          />
        ) : null}

        {newChatLayout &&
        newChatWorkspaceMode === "agent" &&
        newChatMode === "agent" &&
        selectedTask &&
        onTaskChange ? (
          <button
            type="button"
            className={`new-chat-task-chip new-chat-task-chip--${selectedTask.value}`}
            aria-label={t("composer.cancelTask", {
              task: t(`composer.tasks.${selectedTask.value}`),
            })}
            disabled={busy}
            onClick={clearTask}
          >
            <span className="new-chat-task-chip__icon" aria-hidden="true">
              <selectedTask.icon className="new-chat-task-chip__task-icon" />
              <X className="new-chat-task-chip__remove-icon" />
            </span>
            <span>{t(`composer.tasks.${selectedTask.value}`)}</span>
          </button>
        ) : null}

        <div
          className={`composer-input-stack${requiredInlineAsset ? " has-inline-asset" : ""}`}
        >
          {requiredInlineAsset ? (
            <NewChatInlineAssetInput
              asset={requiredInlineAsset.asset}
              kind={requiredInlineAsset.kind}
              label={requiredInlineAsset.label}
              disabled={
                busy ||
                videoTaskRunning ||
                !(videoCapabilities?.assetStorageAvailable ?? false)
              }
              unavailableReason={
                videoCapabilities?.assetStorageUnavailableReason || ""
              }
              onChange={(asset) =>
                setNewChatVideoConfig((current) =>
                  current.taskMode === "first_last_frame"
                    ? { ...current, firstFrame: asset }
                    : { ...current, referenceVideo: asset },
                )
              }
            />
          ) : null}
          <textarea
            ref={ref}
            className="comp-input scroll"
            rows={newChatLayout ? 4 : 1}
            value={value}
            disabled={disabled}
            placeholder={placeholderText}
            aria-expanded={Boolean(trigger)}
            onChange={(e) => {
              onChange(e.target.value);
              updateCompletion(e.target.value, e.target.selectionStart);
            }}
            onSelect={(e) => {
              updateCompletion(
                e.currentTarget.value,
                e.currentTarget.selectionStart,
              );
            }}
            onBlur={() => setTimeout(() => setTrigger(null), 0)}
            onKeyDown={(e) => {
              if (isImeCompositionEvent(e.nativeEvent)) return;
              if (trigger) {
                if (e.key === "ArrowDown" && suggestions.length > 0) {
                  e.preventDefault();
                  setActiveIndex((index) => (index + 1) % suggestions.length);
                  return;
                }
                if (e.key === "ArrowUp" && suggestions.length > 0) {
                  e.preventDefault();
                  setActiveIndex(
                    (index) =>
                      (index - 1 + suggestions.length) % suggestions.length,
                  );
                  return;
                }
                if (
                  (e.key === "Enter" || e.key === "Tab") &&
                  suggestions[activeIndex]
                ) {
                  e.preventDefault();
                  choose(suggestions[activeIndex]);
                  return;
                }
                if (e.key === "Escape") {
                  e.preventDefault();
                  setTrigger(null);
                  return;
                }
              }
              if (
                e.key === "Backspace" &&
                !value &&
                e.currentTarget.selectionStart === 0 &&
                e.currentTarget.selectionEnd === 0
              ) {
                removeLastInvocation();
                return;
              }
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                if (canSend) submitComposer();
              }
            }}
          />
          {newChatLayout && value.length === 0 ? (
            <span
              key={placeholderText}
              className="composer-placeholder-reveal"
              aria-hidden="true"
            >
              {placeholderText}
            </span>
          ) : null}
        </div>
        <div className="composer-submit-actions">
          {sessionId && appName && newChatWorkspaceMode === "agent" ? (
            <TokenUsageIndicator
              cloudProvider={cloudProvider}
              modelName={modelName}
              usage={tokenUsage}
              systemTokenEstimate={systemTokenEstimate}
            />
          ) : null}
          <motion.button
            type="button"
            className="comp-send"
            disabled={canStop ? false : !canSend}
            onClick={canStop ? onStop : submitComposer}
            aria-label={
              canStop
                ? t("composer.stopGenerating")
                : videoTaskRunning || canOpenVideoTask
                  ? t("composer.viewVideoProgress")
                  : t("composer.send")
            }
            title={canStop ? t("composer.stopGenerating") : videoCapabilitiesError || undefined}
            whileTap={canStop || canSend ? { scale: 0.9 } : undefined}
            transition={{ type: "spring", stiffness: 600, damping: 22 }}
          >
            {canStop ? (
              <ComposerStopIcon className="icon" />
            ) : busy || videoTaskRunning ? (
              <Loader2 className="icon spin" />
            ) : (
              <ComposerSendIcon className="icon" />
            )}
          </motion.button>
        </div>
      </div>

      <AnimatePresence initial={false}>
        {newChatLayout &&
        showWorkspaceTabs &&
        newChatWorkspaceMode === "video" ? (
          <NewChatVideoControls
            key="new-chat-video-controls"
            config={newChatVideoConfig}
            onChange={setNewChatVideoConfig}
            enhancerModel={videoCapabilities?.enhancerModel || ""}
            assetStorageAvailable={
              videoCapabilities?.assetStorageAvailable ?? false
            }
            assetStorageUnavailableReason={
              videoCapabilities?.assetStorageUnavailableReason || ""
            }
            modelsLoading={videoCapabilitiesLoading}
            modelsError={videoCapabilitiesError}
            disabled={busy || videoTaskRunning}
          />
        ) : null}
      </AnimatePresence>

      {newChatLayout &&
      newChatWorkspaceMode === "agent" &&
      newChatMode === "agent" &&
      harnessEnabled &&
      !selectedTask ? (
        <div className="task-shortcuts" aria-label={t("composer.selectTaskType")}>
          {availableTaskShortcuts.map((task) => {
            const TaskIcon = task.icon;
            return (
              <button
                key={task.value}
                type="button"
                className="task-shortcut"
                disabled={disabled || busy}
                onClick={() => applyTaskShortcut(task)}
              >
                <TaskIcon />
                <span>{t(`composer.tasks.${task.value}`)}</span>
              </button>
            );
          })}
        </div>
      ) : null}

      {newChatLayout &&
      newChatWorkspaceMode === "agent" &&
      newChatMode === "agent" &&
      selectedTask ? (
        <div
          className="prompt-suggestions"
          aria-label={t("composer.enterprisePrompts", {
            task: t(`composer.tasks.${selectedTask.value}`),
          })}
        >
          {selectedTask.prompts.map((prompt) => {
            const PromptIcon = selectedTask.icon;
            const translatedPrompt = t(prompt);
            return (
              <button
                key={prompt}
                type="button"
                className="prompt-suggestion"
                disabled={disabled || busy}
                onClick={() => applyTaskPrompt(translatedPrompt)}
              >
                <PromptIcon />
                <span>{translatedPrompt}</span>
              </button>
            );
          })}
        </div>
      ) : null}

      {showMeta && (
        <div className="composer-meta">
          <span className="composer-session-line">
            {t("composer.sessionIdLabel")}
            <span
              className="composer-session-id"
              title={sessionId || undefined}
              aria-live="polite"
            >
              {sessionInitializing ? t("composer.initializing") : sessionId || "—"}
            </span>
            {sessionId && (
              <button
                type="button"
                className="composer-session-copy"
                title={sessionIdCopied ? t("composer.copied") : t("composer.copySessionId")}
                aria-label={sessionIdCopied ? t("composer.sessionIdCopied") : t("composer.copySessionId")}
                onClick={() => void copySessionId()}
              >
                {sessionIdCopied ? <Check /> : <Copy />}
              </button>
            )}
          </span>
          <span className="composer-meta-separator" aria-hidden>
            |
          </span>
          <span>{t("composer.disclaimer")}</span>
          {runtimeLogTarget ? (
            <>
              <span className="composer-meta-separator" aria-hidden>
                |
              </span>
              <button
                type="button"
                className="composer-runtime-logs"
                onClick={() => setRuntimeLogsOpen(true)}
              >
                <SandboxTerminalIcon />
                <span>{t("composer.viewLogs")}</span>
              </button>
            </>
          ) : null}
        </div>
      )}

      {runtimeLogTarget ? (
        <RuntimeLogsDialog
          open={runtimeLogsOpen}
          provider={cloudProvider}
          sessionId={sessionId}
          target={runtimeLogTarget}
          onClose={() => setRuntimeLogsOpen(false)}
        />
      ) : null}

      {/* hidden pickers */}
      <input
        ref={imageInput}
        type="file"
        accept="image/*"
        multiple
        hidden
        onChange={onInputChange}
      />
      <input
        ref={documentInput}
        type="file"
        accept=".txt,.md,.markdown,.pdf,text/plain,text/markdown,application/pdf"
        multiple
        hidden
        onChange={onInputChange}
      />
      <input
        ref={videoInput}
        type="file"
        accept="video/mp4,video/webm,video/quicktime"
        multiple
        hidden
        onChange={onInputChange}
      />
    </div>
  );
}
