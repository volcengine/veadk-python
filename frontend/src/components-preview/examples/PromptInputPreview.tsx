import { PromptInput, SingleLinePromptInput } from "../../components/ai-app/PromptInput";

export function PromptInputPreview() {
  return (
    <section aria-labelledby="prompt-input-preview-title">
      <h2 id="prompt-input-preview-title" className="component-preview-title">Prompt Input</h2>
      <PromptInput />
      <div style={{ marginTop: 32 }}>
        <SingleLinePromptInput aria-label="Single line prompt" />
      </div>
    </section>
  );
}
