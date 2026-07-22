import { useMemo } from "react";
import type { Block } from "../../blocks";
import { Blocks } from "../Blocks";
import type { SkillActivity } from "./types";

const ignoreAction = () => undefined;
type ConversationActivity = Exclude<SkillActivity, { kind: "status" }>;

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
  throw new Error("不支持的 Skill 对话活动");
}

export function SkillConversationStream({ activities }: { activities: SkillActivity[] }) {
  const blocks = useMemo(
    () => activities.filter((activity) => activity.kind !== "status").map(toConversationBlock),
    [activities],
  );

  if (blocks.length === 0) return null;
  return (
    <div
      className="skill-conversation"
      aria-label="Skill 生成对话"
      aria-live="polite"
    >
      <Blocks blocks={blocks} onAction={ignoreAction} />
    </div>
  );
}
