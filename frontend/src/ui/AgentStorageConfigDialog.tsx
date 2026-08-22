import { Button } from "@openai/apps-sdk-ui/components/Button";
import { Select, type Option } from "@openai/apps-sdk-ui/components/Select";
import {
  useEffect,
  useId,
  useRef,
  useState,
  type ReactElement,
  type SVGProps,
} from "react";
import { createPortal } from "react-dom";
import "./AgentStorageConfigDialog.css";

export type AgentStorageMode = "managed" | "enterprise" | "local";

export interface AgentStorageConfig {
  enabled: boolean;
  mode: AgentStorageMode;
  database: string;
}

export type AgentStorageCapabilityKey =
  "knowledgeBase" | "shortTermMemory" | "longTermMemory";

export type AgentStorageCapabilities = Record<
  AgentStorageCapabilityKey,
  AgentStorageConfig
>;

export const AGENT_STORAGE_CAPABILITY_LABELS: Record<
  AgentStorageCapabilityKey,
  { label: string; dialogTitle: string }
> = {
  knowledgeBase: { label: "知识库", dialogTitle: "知识库配置" },
  shortTermMemory: { label: "短期记忆", dialogTitle: "短期记忆存储" },
  longTermMemory: { label: "长期记忆", dialogTitle: "长期记忆存储" },
};

export function createDefaultAgentStorageCapabilities(): AgentStorageCapabilities {
  return {
    knowledgeBase: { enabled: false, mode: "enterprise", database: "" },
    shortTermMemory: { enabled: false, mode: "enterprise", database: "" },
    longTermMemory: { enabled: false, mode: "enterprise", database: "" },
  };
}

const DATABASE_OPTIONS: Option[] = [
  { value: "beijing", label: "北京" },
  { value: "shanghai", label: "上海" },
];

const STORAGE_OPTIONS: Array<{
  mode: AgentStorageMode;
  title: string;
  description: string;
  Icon: (props: SVGProps<SVGSVGElement>) => ReactElement;
}> = [
  {
    mode: "managed",
    title: "平台托管存储",
    description: "自动保存，会话结束 24 小时后清除",
    Icon: CloudStorageIcon,
  },
  {
    mode: "enterprise",
    title: "企业数据库",
    description: "自动保存，会话结束 24 小时后清楚",
    Icon: EnterpriseStorageIcon,
  },
  {
    mode: "local",
    title: "本地存储",
    description: "自动保存，会话结束 24 小时后清楚",
    Icon: LocalStorageIcon,
  },
];

function CloudStorageIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 20 20" fill="none" aria-hidden="true" {...props}>
      <path
        d="M14.5826 15.8334H7.49924C6.41746 15.8331 5.35707 15.532 4.43655 14.9638C3.51604 14.3955 2.77167 13.5825 2.28663 12.6155C1.80159 11.6486 1.59498 10.5658 1.6899 9.48822C1.78481 8.41061 2.17751 7.38062 2.82411 6.51335C3.47071 5.64608 4.34574 4.9757 5.35141 4.57711C6.35708 4.17852 7.45378 4.06743 8.51895 4.25626C9.58412 4.44508 10.5758 4.92638 11.3832 5.64637C12.1906 6.36636 12.7818 7.29668 13.0909 8.33337H14.5826C15.5771 8.33337 16.531 8.72846 17.2342 9.43172C17.9375 10.135 18.3326 11.0888 18.3326 12.0834C18.3326 13.0779 17.9375 14.0318 17.2342 14.735C16.531 15.4383 15.5771 15.8334 14.5826 15.8334Z"
        stroke="currentColor"
        strokeWidth="1.3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function EnterpriseStorageIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 20 20" fill="none" aria-hidden="true" {...props}>
      <path
        d="M8.33333 17.5V6.66667C8.33333 6.44565 8.24554 6.23369 8.08926 6.07741C7.93298 5.92113 7.72101 5.83333 7.5 5.83333H3.33333C3.11232 5.83333 2.90036 5.92113 2.74408 6.07741C2.5878 6.23369 2.5 6.44565 2.5 6.66667V16.6667C2.5 16.8877 2.5878 17.0996 2.74408 17.2559C2.90036 17.4122 3.11232 17.5 3.33333 17.5H13.3333C13.5543 17.5 13.7663 17.4122 13.9226 17.2559C14.0789 17.0996 14.1667 16.8877 14.1667 16.6667V12.5C14.1667 12.279 14.0789 12.067 13.9226 11.9107C13.7663 11.7545 13.5543 11.6667 13.3333 11.6667H2.5M12.5 2.5H16.6667C17.1269 2.5 17.5 2.8731 17.5 3.33333V7.5C17.5 7.96024 17.1269 8.33333 16.6667 8.33333H12.5C12.0398 8.33333 11.6667 7.96024 11.6667 7.5V3.33333C11.6667 2.8731 12.0398 2.5 12.5 2.5Z"
        stroke="currentColor"
        strokeWidth="1.3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function LocalStorageIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 20 20" fill="none" aria-hidden="true" {...props}>
      <path
        d="M18.3334 14.5833L17.7569 6.22479C17.6664 4.91253 17.6212 4.2564 17.3368 3.75902C17.0864 3.32111 16.7093 2.9692 16.2552 2.74952C15.7395 2.5 15.0818 2.5 13.7664 2.5H6.23367C4.91829 2.5 4.2606 2.5 3.74483 2.74952C3.29074 2.9692 2.91372 3.32111 2.66331 3.75902C2.3789 4.2564 2.33365 4.91253 2.24315 6.22479L1.6667 14.5833M18.3334 14.5833C18.3334 16.1942 17.0275 17.5 15.4167 17.5H4.58337C2.97254 17.5 1.6667 16.1942 1.6667 14.5833M18.3334 14.5833C18.3334 12.9725 17.0275 11.6667 15.4167 11.6667H4.58337C2.97254 11.6667 1.6667 12.9725 1.6667 14.5833M5.00003 14.5833H5.00837M10 14.5833H15"
        stroke="currentColor"
        strokeWidth="1.3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function CloseIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 20 20" fill="none" aria-hidden="true" {...props}>
      <path
        d="M5 5L15 15"
        stroke="currentColor"
        strokeWidth="1.25"
        strokeLinecap="round"
      />
      <path
        d="M15 5L5 15"
        stroke="currentColor"
        strokeWidth="1.25"
        strokeLinecap="round"
      />
    </svg>
  );
}

function EditIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 14 14" fill="none" aria-hidden="true" {...props}>
      <path
        d="M6.70833 1.75C6.82437 1.75 6.93565 1.79609 7.01769 1.87814C7.09974 1.96019 7.14583 2.07147 7.14583 2.1875C7.14583 2.30353 7.09974 2.41481 7.01769 2.49686C6.93565 2.57891 6.82437 2.625 6.70833 2.625H2.91667C2.87836 2.625 2.84044 2.63254 2.80505 2.6472C2.76966 2.66186 2.73751 2.68334 2.71043 2.71043C2.68334 2.73751 2.66186 2.76966 2.6472 2.80505C2.63254 2.84044 2.625 2.87836 2.625 2.91667V11.0833C2.625 11.1216 2.63254 11.1596 2.6472 11.1949C2.66186 11.2303 2.68334 11.2625 2.71043 11.2896C2.73751 11.3167 2.76966 11.3381 2.80505 11.3528C2.84044 11.3675 2.87836 11.375 2.91667 11.375H11.0833C11.1607 11.375 11.2349 11.3443 11.2896 11.2896C11.3443 11.2349 11.375 11.0833V7L11.377 6.958C11.3879 6.84617 11.4413 6.7428 11.5263 6.6693C11.6113 6.59581 11.7213 6.55782 11.8335 6.56322C11.9458 6.56862 12.0516 6.61699 12.1291 6.6983C12.2067 6.77962 12.2499 6.88765 12.25 7V11.0833C12.25 11.3928 12.1271 11.6895 11.9083 11.9083C11.6895 12.1271 11.3928 12.25 11.0833 12.25H2.91667C2.60725 12.25 2.3105 12.1271 2.09171 11.9083C1.87292 11.6895 1.75 11.3928 1.75 11.0833V2.91667C1.75 2.60725 1.87292 2.3105 2.09171 2.09171C2.3105 1.87292 2.60725 1.75 2.91667 1.75H6.70833Z"
        fill="currentColor"
      />
      <path
        d="M11.5372 1.85996C11.6145 1.78283 11.7185 1.7383 11.8276 1.73557C11.9368 1.73283 12.0429 1.77208 12.124 1.84524C12.2051 1.9184 12.255 2.01989 12.2635 2.12877C12.2719 2.23765 12.2383 2.34564 12.1695 2.43046L12.1403 2.46254L7.0245 7.57838C6.94713 7.65541 6.84316 7.69983 6.73402 7.70249C6.62487 7.70515 6.51886 7.66584 6.43783 7.59266C6.35681 7.51949 6.30693 7.41802 6.29849 7.30917C6.29005 7.20032 6.32368 7.09238 6.39246 7.00758L6.42162 6.9755L11.5375 1.85967L11.5372 1.85996Z"
        fill="currentColor"
      />
    </svg>
  );
}

export function AgentStorageConfigCard({
  config,
  label,
  onEdit,
}: {
  config: AgentStorageConfig;
  label: string;
  onEdit: () => void;
}) {
  const option =
    STORAGE_OPTIONS.find(({ mode }) => mode === config.mode) ??
    STORAGE_OPTIONS[0];
  const { Icon } = option;

  return (
    <button
      type="button"
      className="agent-storage-card"
      aria-label={`编辑${label}配置`}
      onClick={onEdit}
    >
      <span className="agent-storage-card__icon-wrap">
        <Icon className="agent-storage-card__icon" />
      </span>
      <span className="agent-storage-card__copy">
        <strong>{option.title}</strong>
        <span>{option.description}</span>
      </span>
      <EditIcon className="agent-storage-card__edit" />
    </button>
  );
}

export function AgentStorageConfigDialog({
  title,
  value,
  onCancel,
  onConfirm,
}: {
  title: string;
  value: AgentStorageConfig;
  onCancel: () => void;
  onConfirm: (value: AgentStorageConfig) => void;
}) {
  const titleId = useId();
  const dialogRef = useRef<HTMLElement>(null);
  const onCancelRef = useRef(onCancel);
  const [draft, setDraft] = useState<AgentStorageConfig>(value);

  useEffect(() => {
    onCancelRef.current = onCancel;
  }, [onCancel]);

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    const previousFocus =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    document.body.style.overflow = "hidden";
    dialogRef.current?.focus();

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onCancelRef.current();
        return;
      }
      if (event.key !== "Tab" || !dialogRef.current) return;

      const focusable = Array.from(
        dialogRef.current.querySelectorAll<HTMLElement>(
          'button:not([disabled]), [href], input:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ),
      );
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (!first || !last) return;
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
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleKeyDown);
      if (previousFocus?.isConnected) previousFocus.focus();
    };
  }, []);

  return createPortal(
    <div
      className="agent-storage-dialog__backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onCancel();
      }}
    >
      <section
        ref={dialogRef}
        className="agent-storage-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
      >
        <header className="agent-storage-dialog__header">
          <h2 id={titleId}>{title}</h2>
          <button
            type="button"
            className="agent-storage-dialog__close"
            aria-label={`关闭${title}`}
            onClick={onCancel}
          >
            <CloseIcon />
          </button>
        </header>

        <form
          onSubmit={(event) => {
            event.preventDefault();
            onConfirm({ ...draft, enabled: true });
          }}
        >
          <div className="agent-storage-dialog__content">
            <div
              className="agent-storage-dialog__options"
              role="radiogroup"
              aria-label="存储模式"
            >
              {STORAGE_OPTIONS.map(
                ({ mode, title: optionTitle, description, Icon }) => {
                  const selected = draft.mode === mode;
                  return (
                    <label
                      key={mode}
                      className={`agent-storage-dialog__option${selected ? " is-selected" : ""}`}
                    >
                      <input
                        type="radio"
                        name="agent-storage-mode"
                        value={mode}
                        checked={selected}
                        onChange={() =>
                          setDraft((current) => ({ ...current, mode }))
                        }
                      />
                      <span className="agent-storage-dialog__option-icon-wrap">
                        <Icon className="agent-storage-dialog__option-icon" />
                      </span>
                      <span className="agent-storage-dialog__option-copy">
                        <strong>{optionTitle}</strong>
                        <span>{description}</span>
                      </span>
                      <span
                        className="agent-storage-dialog__radio"
                        aria-hidden="true"
                      >
                        {selected ? <span /> : null}
                      </span>
                    </label>
                  );
                },
              )}
            </div>

            <div
              className={`agent-storage-dialog__database${draft.mode === "enterprise" ? "" : " is-hidden"}`}
              aria-hidden={draft.mode !== "enterprise"}
            >
              <label htmlFor="agent-storage-database">选择数据库</label>
              <Select
                id="agent-storage-database"
                options={DATABASE_OPTIONS}
                value={draft.database}
                onChange={(option) =>
                  setDraft((current) => ({
                    ...current,
                    database: option.value,
                  }))
                }
                placeholder="请选择"
                triggerClassName="agent-storage-dialog__select"
                size="md"
                dropdownIconType="chevronDown"
                pill={false}
                block
                align="start"
              />
            </div>
          </div>

          <footer className="agent-storage-dialog__footer">
            <div className="agent-storage-dialog__actions">
              <Button
                type="button"
                className="agent-storage-dialog__button"
                color="secondary"
                variant="outline"
                size="md"
                pill={false}
                onClick={onCancel}
              >
                取消
              </Button>
              <Button
                type="submit"
                className="agent-storage-dialog__button"
                color="primary"
                variant="solid"
                size="md"
                pill={false}
              >
                确定
              </Button>
            </div>
          </footer>
        </form>
      </section>
    </div>,
    document.body,
  );
}
