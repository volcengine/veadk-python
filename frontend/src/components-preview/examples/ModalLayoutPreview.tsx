import { useState } from "react";
import { ModalLayout } from "../../components/layouts/ModalLayout";
import { Button } from "../../components/primitives/Button";

export function ModalLayoutPreview() {
  const [open, setOpen] = useState(true);
  const close = () => setOpen(false);
  return <section aria-labelledby="modal-layout-preview-title">
    <h2 data-preview-heading tabIndex={-1} id="modal-layout-preview-title" className="component-preview-title">Default</h2>
    {open ? <ModalLayout title="Long-term memory storage" onClose={close} onCancel={close} onConfirm={close} /> : <Button onClick={() => setOpen(true)}>Reopen</Button>}
    </section>;
}
