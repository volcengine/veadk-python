import githubIcon from "../../components/primitives/Label/assets/github.svg";
import statusDot from "../../components/composites/Header/assets/status-dot.svg";
import { useState } from "react";
import { Label, LabelAddIcon } from "../../components/primitives/Label";
import "./LabelPreview.css";

export function LabelPreview() {
  const id = "preview-label";
  const [githubVisible, setGithubVisible] = useState(true);
  return (
    <section aria-labelledby="component-page-title">
      <div className="label-preview-examples">
        <section aria-labelledby={`${id}-default-title`}>
          <h2 data-preview-heading tabIndex={-1} id={`${id}-default-title`}>Label</h2>
          <Label className="label-preview-default">no-code-frontend-builder</Label>
        </section>
        <section aria-labelledby={`${id}-icon-title`}>
          <h2 data-preview-heading tabIndex={-1} id={`${id}-icon-title`}>Label with icon</h2>
          <Label className="label-preview-with-icon" startIcon={<LabelAddIcon />}>Add</Label>
        </section>
        <section aria-labelledby={`${id}-dismissible-title`}>
          <h2 data-preview-heading tabIndex={-1} id={`${id}-dismissible-title`}>Label with close</h2>
          {githubVisible ? <Label
            style={{ width: 97 }}
            startIcon={<span style={{ display: "block", width: 16, height: 16, background: "currentColor", mask: `url(${githubIcon}) center / contain no-repeat` }} />}
            dismissible
            dismissLabel="Remove GitHub"
            onDismiss={() => setGithubVisible(false)}
          >GitHub</Label> : null}
        </section>
        <section aria-labelledby={`${id}-status-title`}>
          <h2 data-preview-heading tabIndex={-1} id={`${id}-status-title`}>Status label</h2>
          <Label className="label-preview-status" variant="status">Control B</Label>
        </section>
        <section aria-labelledby={`${id}-pill-title`}>
          <h2 data-preview-heading tabIndex={-1} id={`${id}-pill-title`}>Pill label</h2>
          <Label variant="pill" startIcon={<img src={statusDot} alt="" />}>ACTIVE</Label>
        </section>
      </div>
    </section>
  );
}
