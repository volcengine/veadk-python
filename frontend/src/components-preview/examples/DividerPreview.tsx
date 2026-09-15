import { ComponentApi } from "../api/ComponentApi";
import { Divider } from "../../components/primitives/Divider";

export function DividerPreview() {
  return <section aria-labelledby="divider-preview-title">
    <h2 id="divider-preview-title" className="component-preview-title">Divider</h2>
    <Divider />
  <ComponentApi names={["Divider"]} />
    </section>;
}
