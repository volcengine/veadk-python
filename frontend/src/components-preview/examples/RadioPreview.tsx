import { useState } from "react";
import { Radio, RadioCard } from "../../components/primitives/Radio";
import cloudIcon from "../../components/primitives/Radio/assets/cloud.svg";
import blocksIcon from "../../components/primitives/Radio/assets/blocks.svg";
import serverIcon from "../../components/primitives/Radio/assets/server.svg";
import { ComponentApi } from "../api/ComponentApi";
import "./RadioPreview.css";

export function RadioPreview() {
  const [storage, setStorage] = useState("enterprise");
  return (
    <section aria-labelledby="radio-preview-title">
      <h2 id="radio-preview-title" className="component-preview-title">Radio</h2>
      <div className="radio-preview-cards" role="radiogroup" aria-label="Storage">
        <RadioCard
          name="radio-preview-storage"
          value="platform"
          title="Platform-hosted storage"
          description="Auto-save. Cleared 24 hours after the session ends"
          icon={<img src={cloudIcon} alt="" />}
          checked={storage === "platform"}
          onChange={event => setStorage(event.target.value)}
        />
        <RadioCard
          name="radio-preview-storage"
          value="enterprise"
          title="Enterprise database"
          description="Auto-save. Cleared 24 hours after the session ends"
          icon={<img src={blocksIcon} alt="" />}
          checked={storage === "enterprise"}
          onChange={event => setStorage(event.target.value)}
        />
        <RadioCard
          name="radio-preview-storage"
          value="local"
          title="Local storage"
          description="Auto-save. Cleared 24 hours after the session ends"
          icon={<img src={serverIcon} alt="" />}
          checked={storage === "local"}
          onChange={event => setStorage(event.target.value)}
        />
      </div>
      <h3 className="radio-preview-state-title">Radio control</h3>
      <div className="radio-preview-states" role="group" aria-label="Radio 状态">
        <Radio name="radio-preview-state" value="first" aria-label="选项一" />
        <Radio name="radio-preview-state" value="second" defaultChecked aria-label="选项二" />
        <Radio name="radio-preview-disabled" value="third" disabled aria-label="禁用选项一" />
        <Radio name="radio-preview-disabled" value="fourth" defaultChecked disabled aria-label="禁用选项二" />
      </div>
      <ComponentApi names={["RadioCard", "Radio"]} />
    </section>
  );
}
