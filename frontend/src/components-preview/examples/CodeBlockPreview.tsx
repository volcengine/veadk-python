import { ComponentApi } from "../api/ComponentApi";
import { CodeBlock } from "../../components/composites/CodeBlock";
import { codeBlockSample } from "./codeBlockSample";

export function CodeBlockPreview() {
  return <section aria-labelledby="code-block-preview-title">
    <h2 id="code-block-preview-title" className="component-preview-title">Code block</h2>
    <CodeBlock lines={codeBlockSample} />
  <ComponentApi names={["CodeBlock"]} />
    </section>;
}
