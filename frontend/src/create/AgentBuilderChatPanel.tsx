import { Button } from "@openai/apps-sdk-ui/components/Button";
import { Textarea } from "@openai/apps-sdk-ui/components/Textarea";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { motion } from "motion/react";
import type { Block } from "../blocks";
import { Blocks } from "../ui/Blocks";
import { Markdown } from "../ui/Markdown";
import { isImeCompositionEvent } from "../ui/composerKeyboard";
import { ComposerSendIcon, ComposerStopIcon } from "../ui/icons/ComposerIcons";
import {
  CreateBackIcon,
  MessageSmileSquareIcon,
} from "../ui/icons/CreateAgentIcons";
import "./AgentBuilderChatPanel.css";

const ignoreBlockAction = () => undefined;

export interface AgentBuilderChatMessage {
  id: string;
  role: "user" | "assistant";
  text?: string;
  blocks?: Block[];
  streaming?: boolean;
  error?: string;
}

export interface AgentBuilderChatPanelProps {
  messages: AgentBuilderChatMessage[];
  busy: boolean;
  onSubmit: (goal: string) => void;
  onStop?: () => void;
  onCollapse: () => void;
}

export function AgentBuilderChatPanel({
  messages,
  busy,
  onSubmit,
  onStop,
  onCollapse,
}: AgentBuilderChatPanelProps) {
  const [value, setValue] = useState("");
  const threadRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const thread = threadRef.current;
    if (!thread) return;
    thread.scrollTo({ top: thread.scrollHeight, behavior: busy ? "smooth" : "auto" });
  }, [busy, messages]);

  const canStop = busy && Boolean(onStop);
  const canSend = !busy && value.trim().length > 0;

  function submit(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    const goal = value.trim();
    if (!goal || busy) return;
    setValue("");
    onSubmit(goal);
  }

  return (
    <aside className="agent-builder-chat" aria-label="智能创建对话">
      <header className="agent-builder-chat-header">
        <span className="agent-builder-chat-mark" aria-hidden="true">
          <MessageSmileSquareIcon />
        </span>
        <Button
          type="button"
          color="secondary"
          variant="ghost"
          size="sm"
          uniform
          pill={false}
          className="agent-builder-chat-collapse"
          aria-label="收起对话"
          onClick={onCollapse}
        >
          <CreateBackIcon />
        </Button>
      </header>

      <div ref={threadRef} className="agent-builder-chat-thread" aria-live="polite">
        {messages.map((message) => (
          <motion.div
            key={message.id}
            className={`turn turn--${message.role} agent-builder-chat-turn`}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.2, ease: "easeOut" }}
          >
            {message.role === "user" ? (
              <div className="bubble">
                <Markdown text={message.text ?? ""} />
              </div>
            ) : (
              <>
                <Blocks
                  blocks={message.blocks ?? []}
                  streaming={message.streaming === true}
                  onAction={ignoreBlockAction}
                />
                {message.error ? (
                  <div className="agent-builder-chat-error" role="alert">
                    {message.error}
                  </div>
                ) : null}
              </>
            )}
          </motion.div>
        ))}
      </div>

      <form className="agent-builder-chat-composer" onSubmit={submit}>
        <Textarea
          autoFocus
          value={value}
          rows={3}
          maxRows={6}
          autoResize
          aria-label="继续描述智能体需求"
          placeholder="继续描述或修改智能体需求"
          disabled={busy}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={(event) => {
            if (
              event.key === "Enter" &&
              !event.shiftKey &&
              !isImeCompositionEvent(event.nativeEvent)
            ) {
              event.preventDefault();
              submit();
            }
          }}
        />
        <Button
          type={canStop ? "button" : "submit"}
          color="primary"
          size="sm"
          uniform
          pill
          className="agent-builder-chat-send"
          aria-label={canStop ? "停止生成" : "发送"}
          disabled={canStop ? false : !canSend}
          disabledTone="relaxed"
          onClick={canStop ? onStop : undefined}
        >
          {canStop ? <ComposerStopIcon /> : <ComposerSendIcon />}
        </Button>
      </form>
    </aside>
  );
}
