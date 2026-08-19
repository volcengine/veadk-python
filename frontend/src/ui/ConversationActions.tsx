import { useState } from "react";
import { Check, Copy } from "lucide-react";
import { FeedbackDownIcon, FeedbackUpIcon } from "./icons/FeedbackIcons";

export type ConversationFeedbackRating = "good" | "bad" | null;

export function ConversationCopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  return (
    <button
      type="button"
      className="icon-btn"
      aria-label={copied ? "已复制" : "复制"}
      title={copied ? "已复制" : "复制"}
      disabled={!text}
      onClick={async () => {
        if (!text) return;
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          window.setTimeout(() => setCopied(false), 1500);
        } catch {
          /* Clipboard access can be unavailable in embedded browsers. */
        }
      }}
    >
      {copied ? <Check className="icon" /> : <Copy className="icon" />}
    </button>
  );
}

export function ConversationFeedbackButtons({
  rating,
  pending = false,
  onChange,
}: {
  rating: ConversationFeedbackRating;
  pending?: boolean;
  onChange: (rating: ConversationFeedbackRating) => void;
}) {
  return (
    <>
      <button
        type="button"
        className={`icon-btn feedback-btn${
          rating === "good" ? " feedback-btn--good" : ""
        }`}
        aria-label="赞"
        aria-pressed={rating === "good"}
        aria-busy={pending}
        title={rating === "good" ? "取消点赞" : "赞"}
        disabled={pending}
        onClick={() => onChange(rating === "good" ? null : "good")}
      >
        <FeedbackUpIcon className="icon" filled={rating === "good"} />
      </button>
      <button
        type="button"
        className={`icon-btn feedback-btn${
          rating === "bad" ? " feedback-btn--bad" : ""
        }`}
        aria-label="踩"
        aria-pressed={rating === "bad"}
        aria-busy={pending}
        title={rating === "bad" ? "取消点踩" : "踩"}
        disabled={pending}
        onClick={() => onChange(rating === "bad" ? null : "bad")}
      >
        <FeedbackDownIcon className="icon" filled={rating === "bad"} />
      </button>
    </>
  );
}
