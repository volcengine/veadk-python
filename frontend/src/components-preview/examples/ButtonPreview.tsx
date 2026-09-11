import { ComponentApi } from "../api/ComponentApi";
import { Button, PlusIcon, PlayIcon, BackIcon, ExternalLinkIcon } from "../../components";
import "./ButtonPreview.css";

export function ButtonPreview() {
  return (
    <section aria-labelledby="button-preview-title">
      <h2 id="button-preview-title" className="component-preview-title">Button</h2>
      <div className="button-preview-examples">
        <section aria-labelledby="button-default-title">
          <h3 id="button-default-title">Primary</h3>
          <Button>Confirm</Button>
        </section>
        <section aria-labelledby="button-icon-title">
          <h3 id="button-icon-title">Primary with icon</h3>
          <Button className="button-preview-create" startIcon={<PlusIcon />}>Create agent</Button>
        </section>
        <section aria-labelledby="button-secondary-title">
          <h3 id="button-secondary-title">Secondary</h3>
          <Button variant="secondary" startIcon={<PlayIcon />}>Test</Button>
        </section>
        <section aria-labelledby="button-ghost-title">
          <h3 id="button-ghost-title">Ghost</h3>
          <Button variant="ghost" startIcon={<BackIcon />}>Back</Button>
        </section>
        <section aria-labelledby="button-link-title">
          <h3 id="button-link-title">Link</h3>
          <Button variant="link" endIcon={<ExternalLinkIcon />}>View details</Button>
        </section>
      </div>
      <section className="button-preview-icon-section" aria-labelledby="button-icon-only-title">
        <h3 id="button-icon-only-title">Icon button</h3>
        <div className="button-preview-examples">
          <section aria-labelledby="button-icon-primary-title">
            <h4 id="button-icon-primary-title">Primary</h4>
            <Button iconOnly startIcon={<PlusIcon />} aria-label="Add" title="Add" />
          </section>
          <section aria-labelledby="button-icon-secondary-title">
            <h4 id="button-icon-secondary-title">Secondary</h4>
            <Button iconOnly variant="secondary" startIcon={<PlayIcon />} aria-label="Run" title="Run" />
          </section>
          <section aria-labelledby="button-icon-ghost-title">
            <h4 id="button-icon-ghost-title">Ghost</h4>
            <Button iconOnly variant="ghost" startIcon={<BackIcon />} aria-label="Go back" title="Go back" />
          </section>
          <section aria-labelledby="button-icon-group-title">
            <h4 id="button-icon-group-title">Group</h4>
            <div className="button-preview-icon-group" role="group" aria-label="Row actions">
              <Button iconOnly variant="ghost" startIcon={<PlusIcon />} aria-label="Add row" title="Add row" />
              <Button iconOnly variant="ghost" startIcon={<PlayIcon />} aria-label="Run row" title="Run row" />
            </div>
          </section>
          <section aria-labelledby="button-icon-disabled-title">
            <h4 id="button-icon-disabled-title">Disabled</h4>
            <Button iconOnly variant="ghost" startIcon={<PlusIcon />} aria-label="Add disabled" title="Add disabled" disabled />
          </section>
        </div>
      </section>
    <ComponentApi names={["Button"]} />
    </section>
  );
}
