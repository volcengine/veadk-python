import { ComponentApi } from "../api/ComponentApi";
import { PromptInput, SingleLinePromptInput } from "../../components/ai-app/PromptInput";

const promptPlaceholders = [
  "Describe the agent you want to create",
  "Create an agent that summarizes meeting notes",
  "Build an agent to help review project progress",
] as const;

const adjustmentPlaceholders = [
  "Add anything you need to adjust",
  "Adjust the tone and level of detail",
  "Add the tools your agent needs",
] as const;

export function PromptInputPreview() {
  return (
    <section aria-labelledby="prompt-input-preview-title">
      <h2 id="prompt-input-preview-title" className="component-preview-title">Prompt Input</h2>
      <PromptInput placeholders={promptPlaceholders} />
      <div style={{ marginTop: 32 }}>
        <SingleLinePromptInput aria-label="Single line prompt" placeholders={adjustmentPlaceholders} />
      </div>
      <ComponentApi names={["PromptInput", "SingleLinePromptInput"]} />
    </section>
  );
}
