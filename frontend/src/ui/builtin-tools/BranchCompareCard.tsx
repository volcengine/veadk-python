import { useMemo, useState } from "react";
import { Badge } from "@openai/apps-sdk-ui/components/Badge";
import { Button } from "@openai/apps-sdk-ui/components/Button";
import { useTranslation } from "react-i18next";
import { Markdown } from "../Markdown";
import {
  parseBranchCompare,
  type BranchCompareBranch,
} from "./branchCompareData";
import type { BuiltinToolDetailProps } from "./registry";
import "./branch-compare.css";

function BranchBody({ branch }: { branch: BranchCompareBranch }) {
  return (
    <div
      className={`branch-compare__body${branch.status === "running" ? " is-streaming" : ""}`}
      aria-live="polite"
    >
      {branch.content ? <Markdown text={branch.content} streaming={branch.status === "running"} /> : null}
      {branch.status === "running" ? <span className="branch-compare__caret" aria-hidden="true" /> : null}
      {branch.error ? <p className="branch-compare__error">{branch.error}</p> : null}
    </div>
  );
}

export function BranchCompareCard({
  args,
  response,
  status,
  onBranchSelect,
}: BuiltinToolDetailProps) {
  const { t } = useTranslation("conversation");
  const data = useMemo(() => parseBranchCompare(args, response, status), [args, response, status]);
  const [activeIndex, setActiveIndex] = useState(0);

  return (
    <section className="branch-compare" aria-label={t("blocks.branchCompare.ariaLabel")}>
      <div className="branch-compare__tabs" role="tablist" aria-label={t("blocks.branchCompare.selectDirection")}>
        {data.branches.map((branch, index) => (
          <button
            className={`branch-compare__tab${activeIndex === index ? " is-active" : ""}`}
            key={`${branch.label}:${index}`}
            type="button"
            role="tab"
            aria-selected={activeIndex === index}
            aria-controls={`branch-compare-panel-${index}`}
            onClick={() => setActiveIndex(index)}
          >
            <Badge color="info" size="sm" variant="soft">{branch.label}</Badge>
          </button>
        ))}
      </div>
      <div className="branch-compare__branches">
        {data.branches.map((branch, index) => (
          <article
            className={`branch-compare__branch${activeIndex === index ? " is-active" : ""}`}
            id={`branch-compare-panel-${index}`}
            key={`${branch.label}:${index}`}
            role="tabpanel"
          >
            <header className="branch-compare__head">
              <Badge color="info" size="sm" variant="soft">{branch.label}</Badge>
            </header>
            <BranchBody branch={branch} />
            <footer className="branch-compare__footer">
              <Button
                type="button"
                color="info"
                variant="ghost"
                size="sm"
                pill={false}
                disabled={branch.status !== "completed"}
                onClick={() => onBranchSelect?.(branch)}
              >
                {t("blocks.branchCompare.continue")}
              </Button>
            </footer>
          </article>
        ))}
      </div>
    </section>
  );
}
