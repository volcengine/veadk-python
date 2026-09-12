import { ComponentApi } from "../api/ComponentApi";
import githubIcon from "../../components/primitives/Label/assets/github.svg";
import statusDot from "../../components/composites/Header/assets/status-dot.svg";
import { useId, useState } from "react";
import { Label, LabelAddIcon } from "../../components/primitives/Label";
import "./LabelPreview.css";

export function LabelPreview() {
  const id = useId();
  const [githubVisible, setGithubVisible] = useState(true);
  return (
    <section aria-labelledby={`${id}-title`}>
      <h2 id={`${id}-title`} className="component-preview-title">Label</h2>
      <div className="label-preview-examples">
        <section aria-labelledby={`${id}-default-title`}>
          <h3 id={`${id}-default-title`}>Label</h3>
          <Label className="label-preview-default">no-code-frontend-builder</Label>
        </section>
        <section aria-labelledby={`${id}-icon-title`}>
          <h3 id={`${id}-icon-title`}>Label with icon</h3>
          <Label className="label-preview-with-icon" startIcon={<LabelAddIcon />}>Add</Label>
        </section>
        <section aria-labelledby={`${id}-dismissible-title`}>
          <h3 id={`${id}-dismissible-title`}>Label with close</h3>
          {githubVisible ? <Label
            style={{ width: 97 }}
            startIcon={<span style={{ display: "block", width: 16, height: 16, background: "currentColor", mask: `url(${githubIcon}) center / contain no-repeat` }} />}
            dismissible
            dismissLabel="Remove GitHub"
            onDismiss={() => setGithubVisible(false)}
          >GitHub</Label> : null}
        </section>
        <section aria-labelledby={`${id}-status-title`}>
          <h3 id={`${id}-status-title`}>Status label</h3>
          <Label className="label-preview-status" variant="status">Control B</Label>
        </section>
        <section aria-labelledby={`${id}-pill-title`}>
          <h3 id={`${id}-pill-title`}>Pill label</h3>
          <Label variant="pill" startIcon={<img src={statusDot} alt="" />}>ACTIVE</Label>
        </section>
      </div>
    <ComponentApi names={["Label"]} />
    </section>
  );
}
