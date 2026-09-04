import {
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useTranslation } from "react-i18next";
import type { Attachment } from "../adk/client";
import type {
  SandboxModel,
  SandboxSkill,
} from "../adk/sandbox";
import { InvocationChips } from "./InvocationChips";
import { MediaGroup } from "./Media";
import { isImeCompositionEvent } from "./composerKeyboard";
import {
  matchingSandboxCommands,
  matchingSandboxModels,
  type SandboxSlashCommand,
} from "./sandboxCommands";
import {
  SandboxBrowserIcon,
  SandboxAddIcon,
  SandboxCheckIcon,
  SandboxCopyIcon,
  SandboxFileIcon,
  SandboxImageIcon,
  SandboxPermissionsIcon,
  SandboxSendIcon,
  SandboxSparkIcon,
  SandboxSpinnerIcon,
  SandboxStopIcon,
  SandboxTerminalIcon,
  SandboxVideoIcon,
  SandboxWorkspaceIcon,
} from "./icons/SandboxControlIcons";

type SandboxCompletion =
  | { kind: "command"; command: SandboxSlashCommand }
  | { kind: "model"; model: SandboxModel }
  | { kind: "skill"; skill: SandboxSkill };

export interface SandboxComposerActions {
  onOpenTerminal: () => void;
  onOpenBrowser: () => void;
  onOpenPermissions: () => void;
  onOpenWorkspace: () => void;
  onCopyEndpoint?: () => void;
  endpointCopyEnabled?: boolean;
  endpointCopyState?: "idle" | "copying" | "copied";
  workspaceLocked: boolean;
  settingsBusy: boolean;
  uploadBusy: boolean;
}

interface SkillMention {
  query: string;
  start: number;
  end: number;
}

export interface SandboxComposerProps {
  appName: string;
  value: string;
  onChange: (value: string) => void;
  onSubmit: (value: string) => void;
  onStop?: () => void;
  disabled: boolean;
  busy: boolean;
  attachments: Attachment[];
  onAddFiles: (files: FileList | File[]) => void;
  onRemoveAttachment: (id: string) => void;
  actions: SandboxComposerActions;
  models: SandboxModel[];
  modelsLoading: boolean;
  modelsLoaded: boolean;
  currentModel?: string;
  onRequestModels: () => void;
  skills: SandboxSkill[];
  skillsLoading: boolean;
  skillsLoaded: boolean;
  selectedSkills: SandboxSkill[];
  onRequestSkills: () => void;
  onSelectedSkillsChange: (skills: SandboxSkill[]) => void;
  textOnly?: boolean;
}

export function SandboxComposer({
  appName,
  value,
  onChange,
  onSubmit,
  onStop,
  disabled,
  busy,
  attachments,
  onAddFiles,
  onRemoveAttachment,
  actions,
  models,
  modelsLoading,
  modelsLoaded,
  currentModel,
  onRequestModels,
  skills,
  skillsLoading,
  skillsLoaded,
  selectedSkills,
  onRequestSkills,
  onSelectedSkillsChange,
  textOnly = false,
}: SandboxComposerProps) {
  const { t, i18n } = useTranslation("sandbox");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const imageInput = useRef<HTMLInputElement>(null);
  const documentInput = useRef<HTMLInputElement>(null);
  const videoInput = useRef<HTMLInputElement>(null);
  const [addMenuOpen, setAddMenuOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const [menuDismissed, setMenuDismissed] = useState(false);

  useLayoutEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`;
  }, [value]);

  const slash = useMemo(() => {
    if (!value.startsWith("/") || value.includes("\n")) return undefined;
    const raw = value.slice(1);
    const separator = raw.search(/\s/);
    const command = (separator < 0 ? raw : raw.slice(0, separator))
      .toLocaleLowerCase();
    const argument = separator < 0 ? "" : raw.slice(separator).trim();
    if (separator >= 0 && command !== "model") return undefined;
    return { command, argument, modelMode: separator >= 0 };
  }, [value]);
  const mention = useMemo<SkillMention | undefined>(() => {
    const match = /(^|\s)\$([^\s$]*)$/.exec(value);
    if (!match) return undefined;
    return {
      query: match[2],
      start: value.length - match[2].length - 1,
      end: value.length,
    };
  }, [value]);
  const completions = useMemo<SandboxCompletion[]>(() => {
    if (mention) {
      const query = mention.query.toLocaleLowerCase();
      return skills
        .filter(
          (skill) =>
            !selectedSkills.some(
              (selected) =>
                selected.id === skill.id || selected.name === skill.name,
            ),
        )
        .filter((skill) =>
          `${skill.name} ${skill.description}`
            .toLocaleLowerCase()
            .includes(query)
        )
        .slice(0, 12)
        .map((skill) => ({ kind: "skill" as const, skill }));
    }
    if (slash?.modelMode) {
      return matchingSandboxModels(models, slash.argument)
        .map((model) => ({ kind: "model" as const, model }));
    }
    if (slash) {
      return matchingSandboxCommands(slash.command)
        .map((command) => ({ kind: "command" as const, command }));
    }
    return [];
  }, [i18n.resolvedLanguage, mention, models, selectedSkills, skills, slash]);
  const menuVisible = !textOnly && !menuDismissed && Boolean(mention || slash);

  useEffect(() => {
    setActiveIndex(0);
  }, [value]);
  useEffect(() => {
    if (slash?.modelMode && !modelsLoaded && !modelsLoading) {
      onRequestModels();
    }
  }, [modelsLoaded, modelsLoading, onRequestModels, slash?.modelMode]);
  useEffect(() => {
    if (mention && !skillsLoaded && !skillsLoading) onRequestSkills();
  }, [mention, onRequestSkills, skillsLoaded, skillsLoading]);

  const uploadPending = attachments.some(
    (attachment) => attachment.status !== "ready",
  );
  const canStop = busy && Boolean(onStop);
  const canSend =
    !disabled &&
    !busy &&
    !uploadPending &&
    (value.trim().length > 0 || attachments.length > 0);

  function updateValue(next: string) {
    setMenuDismissed(false);
    setAddMenuOpen(false);
    onChange(next);
  }

  function choose(item: SandboxCompletion) {
    if (item.kind === "skill") {
      if (!mention) return;
      const next = value.slice(0, mention.start) + value.slice(mention.end);
      onSelectedSkillsChange([...selectedSkills, item.skill]);
      updateValue(next);
      setMenuDismissed(true);
      requestAnimationFrame(() => {
        textareaRef.current?.focus();
        textareaRef.current?.setSelectionRange(mention.start, mention.start);
      });
      return;
    }
    if (item.kind === "model") {
      updateValue(`/model ${item.model.id}`);
      setMenuDismissed(true);
      requestAnimationFrame(() => textareaRef.current?.focus());
      return;
    }
    if (item.command.name === "model") {
      updateValue("/model ");
      onRequestModels();
      requestAnimationFrame(() => textareaRef.current?.focus());
      return;
    }
    if (item.command.name === "skill" || item.command.name === "skills") {
      updateValue(`/${item.command.name}`);
      setMenuDismissed(true);
      requestAnimationFrame(() => textareaRef.current?.focus());
      return;
    }
    updateValue(`/${item.command.name}`);
    setMenuDismissed(true);
    requestAnimationFrame(() => textareaRef.current?.focus());
  }

  function pick(input: React.RefObject<HTMLInputElement | null>) {
    setAddMenuOpen(false);
    input.current?.click();
  }

  function onInputChange(event: React.ChangeEvent<HTMLInputElement>) {
    const files = event.target.files ? Array.from(event.target.files) : [];
    if (files.length) onAddFiles(files);
    event.target.value = "";
  }

  const menuLabel = mention
    ? t("composer.availableSkills")
    : slash?.modelMode
      ? t("composer.selectModel")
      : t("composer.commands");

  return (
    <div className="composer sandbox-codex-composer">
      {attachments.length > 0 ? (
        <MediaGroup
          appName={appName}
          compact
          items={attachments}
          onRemove={onRemoveAttachment}
        />
      ) : null}

      <div className="composer-box">
        {menuVisible ? (
          <div
            className="composer-command-menu"
            role="listbox"
            aria-label={menuLabel}
          >
            <div className="composer-command-head">
              <SandboxSparkIcon />
              <span>{menuLabel}</span>
              {slash?.modelMode && currentModel ? (
                <small>{t("composer.currentModel", { model: currentModel })}</small>
              ) : null}
              <kbd>{mention ? "$" : "/"}</kbd>
            </div>
            {mention && skillsLoading ? (
              <div className="composer-command-empty">
                <SandboxSpinnerIcon className="spin" /> {t("composer.loadingSkills")}
              </div>
            ) : slash?.modelMode && modelsLoading ? (
              <div className="composer-command-empty">
                <SandboxSpinnerIcon className="spin" /> {t("composer.loadingModels")}
              </div>
            ) : completions.length === 0 ? (
              <div className="composer-command-empty">
                {mention
                  ? t("composer.noSkillMatches")
                  : slash?.modelMode
                    ? t("composer.noModelMatches")
                    : t("composer.noCommandMatches")}
              </div>
            ) : (
              <div className="composer-command-list">
                {completions.map((item, index) => {
                  const key =
                    item.kind === "command"
                      ? `command:${item.command.name}`
                      : item.kind === "model"
                        ? `model:${item.model.id}`
                        : `skill:${item.skill.id}`;
                  const title =
                    item.kind === "command"
                      ? item.command.usage
                      : item.kind === "model"
                        ? item.model.displayName
                        : `$${item.skill.name}`;
                  const description =
                    item.kind === "command"
                      ? item.command.description
                      : item.kind === "model"
                        ? item.model.description || item.model.id
                        : item.skill.description || t("composer.skillFallback");
                  return (
                    <button
                      type="button"
                      role="option"
                      aria-selected={index === activeIndex}
                      className={`composer-command-item${
                        index === activeIndex ? " is-active" : ""
                      }`}
                      key={key}
                      onMouseDown={(event) => {
                        event.preventDefault();
                        choose(item);
                      }}
                      onMouseEnter={() => setActiveIndex(index)}
                    >
                      <span
                        className={`composer-command-icon composer-command-icon--${item.kind}`}
                        aria-hidden="true"
                      >
                        {item.kind === "command"
                          ? "/"
                          : item.kind === "model"
                            ? "◇"
                            : "$"}
                      </span>
                      <span className="composer-command-copy">
                        <strong>{title}</strong>
                        <span>{description}</span>
                      </span>
                      {index === activeIndex ? <kbd>↵</kbd> : null}
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        ) : null}

        <div className="composer-left-controls">
          {!textOnly && <>
          <div className="composer-menu-wrap">
            <button
              type="button"
              className="comp-icon"
              title={t("composer.add")}
              aria-label={t("composer.add")}
              disabled={disabled}
              onClick={() => setAddMenuOpen((open) => !open)}
            >
              <SandboxAddIcon className="icon" />
            </button>
            {addMenuOpen ? (
              <>
                <div
                  className="menu-scrim"
                  onClick={() => setAddMenuOpen(false)}
                />
                <div className="composer-menu" role="menu">
                  <button
                    type="button"
                    className="menu-item"
                    disabled={actions.uploadBusy}
                    onClick={() => pick(imageInput)}
                  >
                    <SandboxImageIcon className="icon" />
                    {t("composer.uploadImage")}
                  </button>
                  <button
                    type="button"
                    className="menu-item"
                    disabled={actions.uploadBusy}
                    onClick={() => pick(documentInput)}
                  >
                    <SandboxFileIcon className="icon" />
                    {t("composer.uploadDocument")}
                  </button>
                  <button
                    type="button"
                    className="menu-item"
                    disabled={actions.uploadBusy}
                    onClick={() => pick(videoInput)}
                  >
                    <SandboxVideoIcon className="icon" />
                    {t("composer.uploadVideo")}
                  </button>
                  <div className="composer-menu-separator" role="separator" />
                  <button
                    type="button"
                    className="menu-item"
                    onClick={() => {
                      setAddMenuOpen(false);
                      actions.onOpenTerminal();
                    }}
                  >
                    <SandboxTerminalIcon className="icon" />
                    {t("composer.openTerminal")}
                  </button>
                  <button
                    type="button"
                    className="menu-item"
                    onClick={() => {
                      setAddMenuOpen(false);
                      actions.onOpenBrowser();
                    }}
                  >
                    <SandboxBrowserIcon className="icon" />
                    {t("composer.viewBrowser")}
                  </button>
                </div>
              </>
            ) : null}
          </div>
          <button
            type="button"
            className="comp-icon sandbox-composer-control"
            title={t("composer.permissions")}
            aria-label={t("composer.permissions")}
            disabled={actions.settingsBusy || busy}
            onClick={actions.onOpenPermissions}
          >
            <SandboxPermissionsIcon />
          </button>
          <button
            type="button"
            className={`comp-icon sandbox-composer-control${
              actions.workspaceLocked ? " is-locked" : ""
            }`}
            title={
              actions.workspaceLocked
                ? t("composer.workspaceLocked")
                : t("composer.selectWorkspace")
            }
            aria-label={t("composer.workspace")}
            disabled={actions.settingsBusy || busy}
            onClick={actions.onOpenWorkspace}
          >
            <SandboxWorkspaceIcon />
          </button>
          {actions.endpointCopyEnabled && actions.onCopyEndpoint ? (
            <button
              type="button"
              className="comp-icon sandbox-composer-control"
              title={
                actions.endpointCopyState === "copied"
                  ? t("composer.endpointCopied")
                  : t("composer.copyEndpoint")
              }
              aria-label={
                actions.endpointCopyState === "copied"
                  ? t("composer.endpointCopied")
                  : t("composer.copyEndpoint")
              }
              disabled={actions.endpointCopyState === "copying"}
              onClick={actions.onCopyEndpoint}
            >
              {actions.endpointCopyState === "copying" ? (
                <SandboxSpinnerIcon className="spin" />
              ) : actions.endpointCopyState === "copied" ? (
                <SandboxCheckIcon />
              ) : (
                <SandboxCopyIcon />
              )}
            </button>
          ) : null}
          </>}
        </div>

        <div className="composer-input-stack sandbox-composer-input">
          {!textOnly && selectedSkills.length > 0 ? (
            <InvocationChips
              skillPrefix="$"
              value={{
                skills: selectedSkills.map(({ name, description }) => ({
                  name,
                  description,
                })),
              }}
              onRemoveSkill={(name) =>
                onSelectedSkillsChange(
                  selectedSkills.filter((skill) => skill.name !== name),
                )
              }
            />
          ) : null}
          <textarea
            ref={textareaRef}
            className="comp-input scroll"
            rows={1}
            value={value}
            disabled={disabled}
            placeholder={
              textOnly
                ? t("composer.continuePlaceholder")
                : t("composer.messagePlaceholder")
            }
            aria-expanded={menuVisible}
            onChange={(event) => updateValue(event.target.value)}
            onBlur={() => window.setTimeout(() => setMenuDismissed(true), 0)}
            onKeyDown={(event) => {
              if (isImeCompositionEvent(event.nativeEvent)) return;
              if (menuVisible) {
                if (
                  (event.key === "ArrowDown" ||
                    (event.key === "Tab" && !event.shiftKey)) &&
                  completions.length > 0
                ) {
                  event.preventDefault();
                  setActiveIndex((index) => (index + 1) % completions.length);
                  return;
                }
                if (
                  (event.key === "ArrowUp" ||
                    (event.key === "Tab" && event.shiftKey)) &&
                  completions.length > 0
                ) {
                  event.preventDefault();
                  setActiveIndex(
                    (index) =>
                      (index - 1 + completions.length) % completions.length,
                  );
                  return;
                }
                if (
                  event.key === "Enter" &&
                  !event.shiftKey &&
                  completions[activeIndex]
                ) {
                  event.preventDefault();
                  choose(completions[activeIndex]);
                  return;
                }
                if (event.key === "Escape") {
                  event.preventDefault();
                  setMenuDismissed(true);
                  return;
                }
              }
              if (
                event.key === "Backspace" &&
                !value &&
                event.currentTarget.selectionStart === 0 &&
                selectedSkills.length > 0
              ) {
                event.preventDefault();
                onSelectedSkillsChange(selectedSkills.slice(0, -1));
                return;
              }
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                if (canSend) onSubmit(value);
              }
            }}
          />
        </div>
        <button
          type="button"
          className="comp-send"
          disabled={canStop ? false : !canSend}
          onClick={canStop ? onStop : () => onSubmit(value)}
          aria-label={canStop ? t("composer.stop") : t("composer.send")}
          title={canStop ? t("composer.stop") : undefined}
        >
          {canStop ? (
            <SandboxStopIcon className="icon" />
          ) : busy ? (
            <SandboxSpinnerIcon className="icon spin" />
          ) : (
            <SandboxSendIcon className="icon" />
          )}
        </button>
      </div>

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
