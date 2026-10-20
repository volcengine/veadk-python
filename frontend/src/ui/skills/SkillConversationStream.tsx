import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import type { Block } from "../../blocks";
import { Blocks } from "../Blocks";
import type { SkillWorkbenchActivity } from "../skill-workbench/types";
import { skillT } from "./i18n";
import "./SkillConversationStream.css";

const ignoreAction = () => undefined;
type ConversationActivity = Exclude<SkillWorkbenchActivity, { kind: "status" }>;

function toConversationBlock(activity: ConversationActivity): Block {
  if (activity.kind === "message") {
    return { kind: "text", text: activity.text };
  }
  if (activity.kind === "thinking") {
    return {
      kind: "thinking",
      text: activity.text,
      done: activity.status === "done",
    };
  }
  if (activity.kind === "tool") {
    return {
      kind: "tool",
      name: activity.name,
      args: activity.args,
      response: activity.response,
      done: activity.status === "done",
    };
  }
  throw new Error(skillT("conversation.unsupportedActivity"));
}

export function SkillConversationStream({ activities }: { activities: SkillWorkbenchActivity[] }) {
  const { t } = useTranslation("skills");
  const blocks = useMemo(
    () => activities.filter((activity) => activity.kind !== "status").map(toConversationBlock),
    [activities],
  );

  if (blocks.length === 0) return null;
  return (
    <div
      className="skill-conversation"
      aria-label={t("conversation.ariaLabel")}
      aria-live="polite"
    >
      <Blocks blocks={blocks} onAction={ignoreAction} />
    </div>
  );
}
