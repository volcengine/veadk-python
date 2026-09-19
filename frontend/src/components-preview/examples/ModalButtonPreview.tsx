import { ModalButton } from "../../components/composites/ModalButton";

import "./ModalButtonPreview.css";

export function ModalButtonPreview() {
  return <section aria-labelledby="modal-button-preview-title">
    <h2 data-preview-heading tabIndex={-1} id="modal-button-preview-title" className="component-preview-title">Default</h2>
    <div className="modal-button-preview__trigger">
      <ModalButton label="打开弹窗" title="Long-term memory storage" />
    </div>
  </section>;
}
