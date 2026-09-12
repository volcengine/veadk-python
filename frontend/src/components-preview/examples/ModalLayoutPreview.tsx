import { ComponentApi } from "../api/ComponentApi";
import { useState } from "react";
import { ModalLayout } from "../../components/layouts/ModalLayout";
import { Button } from "../../components/primitives/Button";

export function ModalLayoutPreview() {
  const [open, setOpen] = useState(true);
  const close = () => setOpen(false);
  return <section aria-labelledby="modal-layout-preview-title">
    <h2 id="modal-layout-preview-title" className="component-preview-title">Modal layout</h2>
    {open ? <ModalLayout title="Long-term memory storage" onClose={close} onCancel={close} onConfirm={close} /> : <Button onClick={() => setOpen(true)}>Reopen</Button>}
  <ComponentApi names={["ModalLayout"]} />
    </section>;
}
