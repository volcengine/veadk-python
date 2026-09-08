import {
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import { Button } from "@openai/apps-sdk-ui/components/Button";
import { useTranslation } from "react-i18next";

export function CronJobFinalAnswer({ output }: { output: string }) {
  const { t } = useTranslation("cronjobs");
  const contentId = useId();
  const contentRef = useRef<HTMLParagraphElement>(null);
  const expandedRef = useRef(false);
  const [expanded, setExpanded] = useState(false);
  const [overflowed, setOverflowed] = useState(false);

  const measureOverflow = useCallback(() => {
    const content = contentRef.current;
    if (!content || expandedRef.current) return;
    setOverflowed(content.scrollHeight > content.clientHeight + 1);
  }, []);

  useLayoutEffect(() => {
    expandedRef.current = expanded;
    if (!expanded) measureOverflow();
  }, [expanded, measureOverflow, output]);

  useEffect(() => {
    const content = contentRef.current;
    if (!content || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measureOverflow);
    observer.observe(content);
    return () => observer.disconnect();
  }, [measureOverflow]);

  return (
    <div
      className={`cronjobs-run-output-body${expanded ? " is-expanded" : ""}`}
    >
      <p id={contentId} ref={contentRef}>{output}</p>
      {overflowed ? (
        <Button
          type="button"
          className="cronjobs-run-output-toggle"
          color="secondary"
          variant="ghost"
          size="sm"
          pill={false}
          aria-expanded={expanded}
          aria-controls={contentId}
          onClick={() => setExpanded((value) => !value)}
        >
          {expanded ? t("actions.collapse") : t("actions.expand")}
        </Button>
      ) : null}
    </div>
  );
}
