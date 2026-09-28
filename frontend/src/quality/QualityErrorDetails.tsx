import { useTranslation } from "react-i18next";
import { Dropdown } from "../components/primitives/Dropdown";
import "./QualityErrorDetails.css";

export function QualityErrorDetails({ diagnostics }: { diagnostics: string }) {
  const { t } = useTranslation("ui");
  if (!diagnostics) return null;
  return (
    <Dropdown label={t("agentWorkspace.qualityManagement.errorDetails")} fullWidth defaultOpen>
      <div className="quality-error-details" tabIndex={0}>{diagnostics}</div>
    </Dropdown>
  );
}
