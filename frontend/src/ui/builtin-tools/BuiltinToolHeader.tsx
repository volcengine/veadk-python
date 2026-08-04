import { TextShimmer } from "../text-shimmer/TextShimmer";
import { ToolDisclosureIcon } from "./icons";
import type { BuiltinToolDefinition } from "./registry";
import "./builtin-tools.css";

export function BuiltinToolHeader({
  definition,
  label,
  done,
  open,
  onToggle,
}: {
  definition: BuiltinToolDefinition;
  label?: string;
  done: boolean;
  open: boolean;
  onToggle: () => void;
}) {
  const Icon = definition.icon;
  const statusLabel = label ?? (done ? definition.doneLabel : definition.runningLabel);

  return (
    <button
      type="button"
      className={`builtin-tool-head${done ? " is-done" : " is-running"}`}
      data-tool-tone={definition.tone}
      onClick={onToggle}
      aria-expanded={open}
    >
      <span className="builtin-tool-icon" aria-hidden="true">
        <Icon />
      </span>
      {done ? (
        <span className="builtin-tool-label">{statusLabel}</span>
      ) : (
        <TextShimmer
          className="builtin-tool-label"
          duration={2.4}
          spread={18}
          aria-live="polite"
        >
          {statusLabel}
        </TextShimmer>
      )}
      <ToolDisclosureIcon className={`builtin-tool-chevron${open ? " is-open" : ""}`} />
    </button>
  );
}
