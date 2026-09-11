import { ComponentApi } from "../api/ComponentApi";
import { Button, PlusIcon, PlayIcon, BackIcon } from "../../components";
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
      </div>
    <ComponentApi names={["Button"]} />
    </section>
  );
}
