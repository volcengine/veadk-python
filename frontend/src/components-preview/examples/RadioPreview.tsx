import { useState } from "react";
import { Radio } from "../../components/primitives/Radio";
import { ComponentApi } from "../api/ComponentApi";
import "./RadioPreview.css";

export function RadioPreview() {
  const [storage, setStorage] = useState("enterprise");
  return (
    <section aria-labelledby="radio-preview-title">
      <h2 id="radio-preview-title" className="component-preview-title">Radio</h2>
      <div className="radio-preview-states" role="group" aria-label="Radio 状态">
        <Radio name="radio-preview-state" value="first" aria-label="选项一" />
        <Radio name="radio-preview-state" value="second" defaultChecked aria-label="选项二" />
        <Radio name="radio-preview-disabled" value="third" disabled aria-label="禁用选项一" />
        <Radio name="radio-preview-disabled" value="fourth" defaultChecked disabled aria-label="禁用选项二" />
      </div>
      <fieldset className="radio-preview-group">
        <legend>Storage</legend>
        <Radio
          name="radio-preview-storage"
          value="platform"
          label="Platform-hosted storage"
          checked={storage === "platform"}
          onChange={event => setStorage(event.target.value)}
        />
        <Radio
          name="radio-preview-storage"
          value="enterprise"
          label="Enterprise database"
          checked={storage === "enterprise"}
          onChange={event => setStorage(event.target.value)}
        />
        <Radio
          name="radio-preview-storage"
          value="local"
          label="Local storage"
          checked={storage === "local"}
          onChange={event => setStorage(event.target.value)}
        />
      </fieldset>
      <ComponentApi names={["Radio"]} />
    </section>
  );
}
