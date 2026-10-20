import { useEffect, useLayoutEffect, useRef, useState } from "react";

import { Button, PlusIcon, PlayIcon, BackIcon, ExternalLinkIcon } from "../../components";
import type { ButtonProps } from "../../components/primitives/Button";
import "./ButtonPreview.css";

const sizes = [
  { value: "compact", label: "Compact" },
  { value: "default", label: "Default" },
  { value: "large", label: "Large" },
] as const;

function ButtonSizeExample({ label, size, ...props }: ButtonProps & { label: string }) {
  const buttonRef = useRef<HTMLButtonElement>(null);
  const [metrics, setMetrics] = useState<{ height: string; detail: string } | null>(null);
  const { iconOnly } = props;

  useLayoutEffect(() => {
    const button = buttonRef.current;
    if (!button) return;
    const icon = button.querySelector<HTMLElement>(".studio-button__icon");
    const updateMetrics = () => {
      const buttonStyle = getComputedStyle(button);
      const next = {
        height: buttonStyle.height,
        detail: iconOnly && icon ? `图标 ${getComputedStyle(icon).width}` : `字号 ${buttonStyle.fontSize}`,
      };
      setMetrics(current => current?.height === next.height && current.detail === next.detail ? current : next);
    };
    updateMetrics();
    const observer = new ResizeObserver(updateMetrics);
    observer.observe(button);
    button.querySelectorAll(".studio-button__icon, .studio-button__label").forEach(element => observer.observe(element));
    return () => observer.disconnect();
  }, [size, iconOnly]);

  return <div className="button-preview-size-example">
    <Button {...props} ref={buttonRef} size={size} />
    <span className="button-preview-size-label">
      <span>{label}{metrics && ` · 高 ${metrics.height}`}</span>
      <span>{metrics?.detail}</span>
    </span>
  </div>;
}

function ButtonSizes(props: Omit<ButtonProps, "size">) {
  return <div className="button-preview-sizes">
    {sizes.map(size => <ButtonSizeExample {...props} key={size.value} size={size.value} label={size.label} />)}
  </div>;
}

export function ButtonPreview() {
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!loading) return;
    const timer = window.setTimeout(() => setLoading(false), 1800);
    return () => window.clearTimeout(timer);
  }, [loading]);

  return (
    <section aria-labelledby="component-page-title">
      <div className="button-preview-examples">
        <section aria-labelledby="button-default-title">
          <h2 data-preview-heading tabIndex={-1} id="button-default-title">Primary</h2>
          <ButtonSizes>Confirm</ButtonSizes>
        </section>
        <section aria-labelledby="button-icon-title">
          <h2 data-preview-heading tabIndex={-1} id="button-icon-title">Primary with Icon</h2>
          <ButtonSizes startIcon={<PlusIcon />}>Create agent</ButtonSizes>
        </section>
        <section aria-labelledby="button-secondary-title">
          <h2 data-preview-heading tabIndex={-1} id="button-secondary-title">Secondary</h2>
          <ButtonSizes variant="secondary" startIcon={<PlayIcon />}>Test</ButtonSizes>
        </section>
        <section aria-labelledby="button-ghost-title">
          <h2 data-preview-heading tabIndex={-1} id="button-ghost-title">Ghost</h2>
          <ButtonSizes variant="ghost" startIcon={<BackIcon />}>Back</ButtonSizes>
        </section>
        <section aria-labelledby="button-outline-title">
          <h2 data-preview-heading tabIndex={-1} id="button-outline-title">Outline</h2>
          <ButtonSizes variant="outline">Cancel</ButtonSizes>
        </section>
        <section aria-labelledby="button-pill-title">
          <h2 data-preview-heading tabIndex={-1} id="button-pill-title">Pill</h2>
          <ButtonSizes variant="pill">Update</ButtonSizes>
        </section>
        <section aria-labelledby="button-link-title">
          <h2 data-preview-heading tabIndex={-1} id="button-link-title">Link</h2>
          <ButtonSizes variant="link" endIcon={<ExternalLinkIcon />}>View details</ButtonSizes>
        </section>
      </div>
      <section className="button-preview-icon-section" aria-labelledby="button-icon-only-title">
        <h2 data-preview-heading tabIndex={-1} id="button-icon-only-title">Icon Button</h2>
        <ButtonSizes iconOnly variant="secondary" startIcon={<PlusIcon />} aria-label="Add" />
        <div className="button-preview-examples">
          <section aria-labelledby="button-icon-background-title">
            <h3 id="button-icon-background-title">Hover background</h3>
            <Button iconOnly variant="ghost" hoverEffect="background" startIcon={<PlusIcon />} aria-label="Add with hover background" title="Hover background" />
          </section>
          <section aria-labelledby="button-icon-highlight-title">
            <h3 id="button-icon-highlight-title">Hover icon highlight</h3>
            <Button iconOnly variant="ghost" hoverEffect="icon" startIcon={<PlusIcon />} aria-label="Add with icon highlight" title="Hover icon highlight" />
          </section>
          <section aria-labelledby="button-icon-group-title">
            <h3 id="button-icon-group-title">Group</h3>
            <div className="button-preview-icon-group" role="group" aria-label="Row actions">
              <Button iconOnly variant="ghost" startIcon={<PlusIcon />} aria-label="Add row" title="Add row" />
              <Button iconOnly variant="ghost" startIcon={<PlayIcon />} aria-label="Run row" title="Run row" />
            </div>
          </section>
          <section aria-labelledby="button-icon-compact-title">
            <h3 id="button-icon-compact-title">Compact</h3>
            <Button iconOnly size="compact" variant="ghost" startIcon={<BackIcon />} aria-label="Go back" title="Go back" />
          </section>
          <section aria-labelledby="button-icon-disabled-title">
            <h3 id="button-icon-disabled-title">Disabled</h3>
            <Button iconOnly variant="ghost" startIcon={<PlusIcon />} aria-label="Add disabled" title="Add disabled" disabled />
          </section>
        </div>
      </section>
      <section className="button-preview-loading-section" aria-labelledby="button-loading-title">
        <h2 data-preview-heading tabIndex={-1} id="button-loading-title">Loading</h2>
        <div className="button-preview-examples">
          <section aria-labelledby="button-loading-primary-title">
            <h3 id="button-loading-primary-title">Primary</h3>
            <Button loading>Confirm</Button>
          </section>
          <section aria-labelledby="button-loading-secondary-title">
            <h3 id="button-loading-secondary-title">Secondary</h3>
            <Button variant="secondary" loading>Confirm</Button>
          </section>
          <section aria-labelledby="button-loading-ghost-title">
            <h3 id="button-loading-ghost-title">Ghost</h3>
            <Button variant="ghost" loading>Confirm</Button>
          </section>
          <section aria-labelledby="button-loading-icon-title">
            <h3 id="button-loading-icon-title">Icon button</h3>
            <Button iconOnly variant="secondary" startIcon={<PlayIcon />} loading aria-label="Run" />
          </section>
          <section aria-labelledby="button-loading-interactive-title">
            <h3 id="button-loading-interactive-title">点击体验</h3>
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
    </section>
  );
}
