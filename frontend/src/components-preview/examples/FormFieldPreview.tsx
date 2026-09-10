import { useId, useState } from "react";
import { FormField } from "../../components/composites/FormField";
import { InputWithTailIcon } from "../../components/primitives/InputWithTailIcon";
import { Textarea } from "../../components/primitives/Textarea";
import "./FormFieldPreview.css";

export function FormFieldPreview() {
  const endpointId = useId();
  const descriptionId = useId();
  const [endpoint, setEndpoint] = useState("https://agentkit.example.volceapi.com/run_sse");
  const [copyStatus, setCopyStatus] = useState("");

  async function copyEndpoint() {
    try {
      await navigator.clipboard.writeText(endpoint);
      setCopyStatus("Copied");
    } catch {
      setCopyStatus("Unable to copy, select the text to copy manually");
    }
  }

  return (
    <section aria-labelledby="form-field-preview-title">
      <h2 id="form-field-preview-title" className="component-preview-title">Form field</h2>
      <FormField label="Endpoint" htmlFor={endpointId}>
        <InputWithTailIcon
          id={endpointId}
          value={endpoint}
          onChange={(event) => {
            setEndpoint(event.target.value);
            setCopyStatus("");
          }}
          onTailIconClick={copyEndpoint}
          tailIconLabel="Copy endpoint URL"
        />
      </FormField>
      <FormField style={{ marginTop: 32 }} label="Description" htmlFor={descriptionId} required>
        <Textarea id={descriptionId} required />
      </FormField>
      <span className="form-field-preview-status" role="status">{copyStatus}</span>
    </section>
  );
}
