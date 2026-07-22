import { TextShimmer } from "../text-shimmer/TextShimmer";
import { ToolDisclosureIcon } from "./icons";
import type { BuiltinToolDefinition } from "./registry";
import "./builtin-tools.css";

export function BuiltinToolHeader({
  definition,
  done,
  open,
  onToggle,
}: {
  definition: BuiltinToolDefinition;
  done: boolean;
  open: boolean;
  onToggle: () => void;
}) {
  const Icon = definition.icon;

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
        <span className="builtin-tool-label">{definition.doneLabel}</span>
      ) : (
        <TextShimmer
          className="builtin-tool-label"
          duration={2.4}
          spread={18}
          aria-live="polite"
        >
          {definition.runningLabel}
        </TextShimmer>
      )}
      <ToolDisclosureIcon className={`builtin-tool-chevron${open ? " is-open" : ""}`} />
    </button>
  );
}
