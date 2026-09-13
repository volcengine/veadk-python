import { useEffect, useState } from "react";
import { ComponentApi } from "../api/ComponentApi";
import { Button, PlusIcon, PlayIcon, BackIcon, ExternalLinkIcon } from "../../components";
import "./ButtonPreview.css";

export function ButtonPreview() {
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!loading) return;
    const timer = window.setTimeout(() => setLoading(false), 1800);
    return () => window.clearTimeout(timer);
  }, [loading]);

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
        <section aria-labelledby="button-outline-title">
          <h3 id="button-outline-title">Outline</h3>
          <Button variant="outline">Cancel</Button>
        </section>
        <section aria-labelledby="button-large-title">
          <h3 id="button-large-title">Large</h3>
          <div className="button-preview-icon-group">
            <Button size="large" variant="secondary" startIcon={<PlayIcon />}>Test</Button>
            <Button size="large" startIcon={<PlusIcon />}>Create</Button>
          </div>
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
          <section aria-labelledby="button-icon-compact-title">
            <h4 id="button-icon-compact-title">Compact</h4>
            <Button iconOnly size="compact" variant="ghost" startIcon={<BackIcon />} aria-label="Go back" title="Go back" />
          </section>
          <section aria-labelledby="button-icon-disabled-title">
            <h4 id="button-icon-disabled-title">Disabled</h4>
            <Button iconOnly variant="ghost" startIcon={<PlusIcon />} aria-label="Add disabled" title="Add disabled" disabled />
          </section>
        </div>
      </section>
      <section className="button-preview-loading-section" aria-labelledby="button-loading-title">
        <h3 id="button-loading-title">Loading</h3>
        <div className="button-preview-examples">
          <section aria-labelledby="button-loading-primary-title">
            <h4 id="button-loading-primary-title">Primary</h4>
            <Button loading>Confirm</Button>
          </section>
          <section aria-labelledby="button-loading-secondary-title">
            <h4 id="button-loading-secondary-title">Secondary</h4>
            <Button variant="secondary" loading>Confirm</Button>
          </section>
          <section aria-labelledby="button-loading-ghost-title">
            <h4 id="button-loading-ghost-title">Ghost</h4>
            <Button variant="ghost" loading>Confirm</Button>
          </section>
          <section aria-labelledby="button-loading-icon-title">
            <h4 id="button-loading-icon-title">Icon button</h4>
            <Button iconOnly variant="secondary" startIcon={<PlayIcon />} loading aria-label="Run" />
          </section>
          <section aria-labelledby="button-loading-interactive-title">
            <h4 id="button-loading-interactive-title">点击体验</h4>
            <Button
              startIcon={<PlayIcon />}
              loading={loading}
              onClick={() => setLoading(true)}
            >
              运行任务
            </Button>
          </section>
        </div>
      </section>
    <ComponentApi names={["Button"]} />
    </section>
  );
}
