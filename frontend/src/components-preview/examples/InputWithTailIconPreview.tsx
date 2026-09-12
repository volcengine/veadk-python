import { useState } from "react";
import { InputWithTailIcon } from "../../components/primitives/InputWithTailIcon";
import "./InputWithTailIconPreview.css";

export function InputWithTailIconPreview() {
  const [value, setValue] = useState("https://agentkit.example.volceapi.com/run_sse");
  const [copyStatus, setCopyStatus] = useState("");

  async function copyValue() {
    try {
      await navigator.clipboard.writeText(value);
      setCopyStatus("Copied");
    } catch {
      setCopyStatus("Unable to copy, select the text to copy manually");
    }
  }

  return (
    <section aria-labelledby="input-with-tail-icon-preview-title">
      <h2 id="input-with-tail-icon-preview-title" className="component-preview-title">Input with tail icon</h2>
      <InputWithTailIcon
        aria-label="Endpoint URL"
        value={value}
        onChange={(event) => {
          setValue(event.target.value);
          setCopyStatus("");
        }}
        onTailIconClick={copyValue}
        tailIconLabel="Copy endpoint URL"
      />
      <span className="input-with-tail-icon-preview-status" role="status">{copyStatus}</span>
    </section>
  );
}
