import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@openai/apps-sdk-ui/components/Button";
import { Badge } from "@openai/apps-sdk-ui/components/Badge";
import { CodeBrowserDialog } from "../../ui/CodeBrowserDialog";
import { buildZip } from "../../ui/zip";
import { NativeConfigForm } from "./NativeConfigForm";
import { nativeConfigFiles, validateNativeDraft, type NativeConfigDraft } from "./nativeConfig";
import type { AgentProject } from "../project";
import { NativeDeployment, type NativeDeploymentCallbacks } from "./NativeDeployment";
import "../CustomCreate.css";
import "../../ui/ProjectPreview.css";
import "./NativeConfigPage.css";

interface Props extends NativeDeploymentCallbacks {
  draft: NativeConfigDraft;
  onDraftChange: (draft: NativeConfigDraft) => void;
  onBack: () => void;
}

export function NativeConfigPage({ draft, onDraftChange, onBack, ...deploymentCallbacks }: Props) {
  const { t } = useTranslation("deepseek");
  const pageRef = useRef<HTMLElement>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const [submitted, setSubmitted] = useState(false);
  const [status, setStatus] = useState<"" | "downloaded" | "downloadFailed">("");
  const [preview, setPreview] = useState<AgentProject | null>(null);
  const [deployment, setDeployment] = useState<AgentProject | null>(null);
  const errors = submitted ? validateNativeDraft(draft) : {};

  useEffect(() => { headingRef.current?.focus(); }, []);

  function createFiles(action: "preview" | "download" | "deploy") {
    setSubmitted(true);
    setStatus("");
    const validation = validateNativeDraft(draft);
    if (Object.keys(validation).length) {
      // Open every invalid section before moving focus to its first field
      requestAnimationFrame(() => {
        pageRef.current?.querySelectorAll<HTMLElement>("[data-invalid='true']").forEach((row) => {
          const details = row.closest("details");
          if (details) details.open = true;
        });
        const first = pageRef.current?.querySelector<HTMLElement>("[data-invalid='true']");
        first?.querySelector<HTMLElement>("input, button")?.focus();
        first?.scrollIntoView({ block: "nearest" });
      });
      return;
    }
    const files = nativeConfigFiles(draft, deploymentCallbacks.cloudProvider);
    if (action === "deploy") {
      setDeployment({ name: "DeepSeek Harness", files });
      return;
    }
    if (action === "preview") {
      setPreview({ name: "DeepSeek Harness", files });
      return;
    }
    let url: string | undefined;
    const link = document.createElement("a");
    try {
      url = URL.createObjectURL(buildZip(files));
      link.href = url;
      link.download = "deepseek-harness-config.zip";
      document.body.append(link);
      link.click();
      setStatus("downloaded");
    } catch {
      setStatus("downloadFailed");
    } finally {
      link.remove();
      if (url) {
        const downloadUrl = url;
        window.setTimeout(() => URL.revokeObjectURL(downloadUrl), 1000);
      }
    }
  }

  if (deployment) return <NativeDeployment {...deploymentCallbacks} project={deployment} draft={draft} onBack={() => setDeployment(null)} />;

  return (
    <>
      <main className="dsh-config-page" ref={pageRef} inert={Boolean(preview)} aria-labelledby="dsh-config-title">
        <header className="dsh-config-page-head">
          <Button className="cw-btn cw-btn-ghost dsh-page-back" color="secondary" variant="ghost" onClick={onBack}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m14 6-6 6 6 6" /></svg>
            {t("back")}
          </Button>
          <h1 id="dsh-config-title" tabIndex={-1} ref={headingRef}>
            <span>{t("pageTitle")}</span>
            <Badge className="dsh-config-beta" color="secondary" variant="soft" size="sm">Beta</Badge>
          </h1>
        </header>
        <div className="dsh-config-page-scroll">
          <div className="dsh-config-page-content">
            <NativeConfigForm draft={draft} errors={errors} onChange={(next) => { onDraftChange(next); setStatus(""); }} />
          </div>
        </div>
        <footer className="dsh-config-page-footer">
          <div className="dsh-config-page-actions">
            <div role="status" aria-live="polite">
              {Object.keys(errors).length
                ? <span className="cw-error-text">{t("validationSummary", { count: Object.keys(errors).length })}</span>
                : status ? <span className={status === "downloadFailed" ? "cw-error-text" : "cw-help"}>{t(status)}</span>
                : null}
            </div>
            <div className="dsh-page-buttons">
              <Button className="cw-btn cw-btn-ghost" color="secondary" variant="outline" onClick={() => createFiles("preview")}>{t("preview")}</Button>
              <Button className="cw-btn cw-btn-ghost" color="secondary" variant="outline" onClick={() => createFiles("download")}>{t("export")}</Button>
              <Button className="cw-btn cw-btn-primary" color="primary" onClick={() => createFiles("deploy")}>{t("deploy")}</Button>
            </div>
          </div>
        </footer>
      </main>
      {preview && <CodeBrowserDialog open project={preview} readOnly onChange={() => {}} onClose={() => setPreview(null)} />}
    </>
  );
}
