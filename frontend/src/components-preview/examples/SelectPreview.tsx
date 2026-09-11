import { ComponentApi } from "../api/ComponentApi";
import { Select } from "../../components/primitives/Select";
import doubao from "../../components/primitives/Select/assets/doubao.svg";

export function SelectPreview() {
  return <section aria-labelledby="select-preview-title">
    <h2 id="select-preview-title" className="component-preview-title">Select</h2>
    <Select aria-label="Model" options={[
      { value: "doubao-seed-2.0-pro", label: "Doubao-Seed-2.0-pro", icon: <img src={doubao} alt="" style={{ width: 13.008, height: 14.6672 }} /> },
      ...[
        "Doubao-Seed-2.0-lite",
        "Doubao-Seed-2.0-mini",
        "Doubao-Seed-1.8",
        "Doubao-Seed-1.6",
        "Doubao-Seed-1.6-flash",
        "Doubao-Seed-1.6-thinking",
        "Doubao-1.5-pro",
        "Doubao-1.5-lite",
        "Doubao-1.5-thinking-pro",
      ].map(label => ({ value: label.toLowerCase(), label, icon: <img src={doubao} alt="" style={{ width: 13.008, height: 14.6672 }} /> })),
    ]} />
  <ComponentApi names={["Select"]} />
    </section>;
}
