import { ComponentApi } from "../api/ComponentApi";
import { useId, useState } from "react";
import { FormField } from "../../components/composites/FormField";
import { InputWithTailIcon } from "../../components/primitives/InputWithTailIcon";
import { InputWithHeaderIcon } from "../../components/primitives/InputWithHeaderIcon";
import { Textarea } from "../../components/primitives/Textarea";
import { Button } from "../../components/primitives/Button";
import "./FormFieldPreview.css";

export function FormFieldPreview() {
  const endpointId = useId();
  const descriptionId = useId();
  const searchId = useId();
  const rulesDescriptionId = useId();
  const [endpoint, setEndpoint] = useState("https://agentkit.example.volceapi.com/run_sse");
  const [copyStatus, setCopyStatus] = useState("");
  const [search, setSearch] = useState("");
  const [description, setDescription] = useState("");
  const [showValidation, setShowValidation] = useState(false);
  const searchError = showValidation && (search.trim().length < 2 || search.trim().length > 32) ? "请输入 2–32 个字符" : undefined;
  const descriptionError = showValidation && (description.trim().length < 10 || description.trim().length > 200) ? "请输入 10–200 个字符" : undefined;

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
      <section className="form-field-preview-with-tip" aria-labelledby="form-field-with-tip-title">
        <h3 id="form-field-with-tip-title" className="component-preview-title">With tip</h3>
        <form className="form-field-preview-validation" noValidate onSubmit={event => {
          event.preventDefault();
          setShowValidation(true);
        }}>
          <FormField label="Search" htmlFor={searchId} tip="输入 2–32 个字符" error={searchError} required>
            <InputWithHeaderIcon id={searchId} value={search} onChange={event => setSearch(event.target.value)} placeholder="Search resources" required />
          </FormField>
          <FormField label="Description" htmlFor={rulesDescriptionId} tip="输入 10–200 个字符" error={descriptionError} required>
            <Textarea className="form-field-preview-textarea" id={rulesDescriptionId} value={description} onChange={event => setDescription(event.target.value)} placeholder="Describe this resource" required />
          </FormField>
          <div className="form-field-preview-actions">
            <Button type="submit">验证</Button>
            <Button type="button" variant="secondary" onClick={() => {
              setSearch("");
              setDescription("");
              setShowValidation(false);
            }}>重置</Button>
          </div>
        </form>
      </section>
    <ComponentApi names={["FormField"]} />
    </section>
  );
}
