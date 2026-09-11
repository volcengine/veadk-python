import { ComponentApi } from "../api/ComponentApi";
import { Textarea } from "../../components/primitives/Textarea";
import "./TextareaPreview.css";

export function TextareaPreview() {
  return (
    <section aria-labelledby="textarea-preview-title">
      <h2 id="textarea-preview-title" className="component-preview-title">Textarea</h2>
      <Textarea
        maxHeight={240}
        aria-label="Agent description"
        className="textarea-preview-example"
        defaultValue="Prepares you for meetings by gathering and summarizing relevant information。"
        counter="38/50"
      />
    <ComponentApi names={["Textarea"]} />
    </section>
  );
}
