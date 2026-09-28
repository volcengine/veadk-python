import { PromptInput, SingleLinePromptInput } from "../../components/ai-app/PromptInput";
import { promptPlaceholders } from "./promptInputExamples";

const adjustmentPlaceholders = [
  "Add anything you need to adjust",
  "Adjust the tone and level of detail",
  "Add the tools your agent needs",
] as const;

export function PromptInputPreview() {
  return (
    <section aria-labelledby="component-page-title">
      <section className="components-preview-variant" aria-labelledby="prompt-input-multiline-title">
        <h2 data-preview-heading tabIndex={-1} id="prompt-input-multiline-title">Multiline</h2>
        <PromptInput placeholders={promptPlaceholders} />
      </section>
      <section className="components-preview-variant" aria-labelledby="prompt-input-single-line-title">
        <h2 data-preview-heading tabIndex={-1} id="prompt-input-single-line-title">Single Line</h2>
        <SingleLinePromptInput aria-label="Single line prompt" placeholders={adjustmentPlaceholders} />
      </section>
    </section>
  );
}
