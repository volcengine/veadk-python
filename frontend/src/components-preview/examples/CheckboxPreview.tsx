import { Checkbox } from "../../components/primitives/Checkbox";
import "./CheckboxPreview.css";

export function CheckboxPreview() {
  return (
    <section aria-labelledby="checkbox-preview-title">
      <h2 id="checkbox-preview-title" className="component-preview-title">Checkbox</h2>
      <Checkbox className="checkbox-preview-example" label="Parallel web search" />
    </section>
  );
}
