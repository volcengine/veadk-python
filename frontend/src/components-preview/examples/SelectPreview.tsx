import { Select } from "../../components/primitives/Select";
import doubao from "../../components/primitives/Select/assets/doubao.svg";

export function SelectPreview() {
  return <section aria-labelledby="select-preview-title">
    <h2 id="select-preview-title" className="component-preview-title">Select</h2>
    <Select aria-label="Model" options={[
      { value: "doubao-seed-2.0-pro", label: "Doubao-Seed-2.0-pro", icon: <img src={doubao} alt="" style={{ width: 13.008, height: 14.6672 }} /> },
    ]} />
  </section>;
}
