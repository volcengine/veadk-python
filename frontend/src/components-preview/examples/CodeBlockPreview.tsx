import { CodeBlock } from "../../components/composites/CodeBlock";
import { codeBlockSample } from "./codeBlockSample";

export function CodeBlockPreview() {
  return <section aria-labelledby="code-block-preview-title">
    <h2 data-preview-heading tabIndex={-1} id="code-block-preview-title" className="component-preview-title">Default</h2>
    <CodeBlock lines={codeBlockSample} />
    </section>;
}
