import { Loading } from "../../components/primitives/Loading";

import "./LoadingPreview.css";

export function LoadingPreview() {
  return <section aria-labelledby="component-page-title">
    <div className="loading-preview-examples">
      <section aria-labelledby="loading-preview-infinity">
        <h2 data-preview-heading tabIndex={-1} id="loading-preview-infinity" className="component-preview-title">Infinity Path</h2>
        <Loading />
      </section>
      <section aria-labelledby="loading-preview-ring">
        <h2 data-preview-heading tabIndex={-1} id="loading-preview-ring" className="component-preview-title">Ring Sweep</h2>
        <Loading variant="ring" />
      </section>
    </div>
  </section>;
}
