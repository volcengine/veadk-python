import { ModalButton } from "../../components/composites/ModalButton";
import { ComponentApi } from "../api/ComponentApi";
import "./ModalButtonPreview.css";

export function ModalButtonPreview() {
  return <section aria-labelledby="modal-button-preview-title">
    <h2 id="modal-button-preview-title" className="component-preview-title">Modal button</h2>
    <div className="modal-button-preview__trigger">
      <ModalButton label="打开弹窗" title="Long-term memory storage" />
    </div>
    <ComponentApi names={["ModalButton"]} />
  </section>;
}
