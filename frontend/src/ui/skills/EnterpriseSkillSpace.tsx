import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { ensureSharedSkillSpace } from "../../adk/skills";
import type { SkillSpaceRef } from "../../create/skills/skillspace";
import { LibraryResourceCard } from "../LibraryResourceCard";
import { normalizeSkillError, SkillErrorDetails } from "./SkillErrorDetails";

export function EnterpriseSkillSpace({ region, active, revision, onOpen }: {
  region: string;
  active: boolean;
  revision: number;
  onOpen: (space: SkillSpaceRef) => void;
}) {
  const { t } = useTranslation("ui");
  const [space, setSpace] = useState<SkillSpaceRef | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    setError(null);
    void ensureSharedSkillSpace({ region, signal: controller.signal })
      .then((result) => { if (!controller.signal.aborted) setSpace(result); })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) setError(normalizeSkillError(reason, t("skillCenter.sharedLoadFailed")));
      });
    return () => controller.abort();
  }, [active, region, retry, revision, t]);

  return (
    <div className="skillcenter-shared-space">
      <LibraryResourceCard
        className="skillcenter-space-card"
        title={t("skillCenter.sharedSpace")}
        description={t("skillCenter.sharedDescription")}
        status={<span className="skillcenter-shared-badge">{t("skillCenter.sharedVisibility")}</span>}
        metadata={[
          { label: t("skillCenter.skillCount"), value: space ? t("skillCenter.skillCountValue", { count: space.skillCount ?? 0 }) : t(error ? "skillCenter.sharedLoadFailed" : "skillCenter.sharedPreparing") },
        ]}
        detailAction={{ label: t("common.viewDetails"), disabled: !space || Boolean(error), onClick: () => { if (space) onOpen(space); } }}
        action={error ? { label: t("common.reload"), onClick: () => setRetry((value) => value + 1) } : undefined}
      />
      {error ? <div className="skillcenter-inline-error" role="alert"><SkillErrorDetails error={error} /></div> : null}
    </div>
  );
}
