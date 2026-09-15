import { ComponentApi } from "../api/ComponentApi";
import { useState } from "react";
import { CardLayout } from "../../components/layouts/CardLayout";
import { Button } from "../../components/primitives/Button";

export function CardLayoutPreview() {
  const [open, setOpen] = useState(true);
  return <section aria-labelledby="card-layout-preview-title">
    <h2 id="card-layout-preview-title" className="component-preview-title">Card layout</h2>
    {open ? <CardLayout title="Meeting Assistant" onClose={() => setOpen(false)} /> : <Button onClick={() => setOpen(true)}>Reopen</Button>}
  <ComponentApi names={["CardLayout"]} />
    </section>;
}
