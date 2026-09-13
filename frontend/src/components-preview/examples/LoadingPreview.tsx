import { Loading } from "../../components/primitives/Loading";
import { ComponentApi } from "../api/ComponentApi";
import "./LoadingPreview.css";

export function LoadingPreview() {
  return <section aria-labelledby="loading-preview-title">
    <h2 id="loading-preview-title" className="component-preview-title">Loading</h2>
    <div className="loading-preview-examples">
      <section aria-labelledby="loading-preview-infinity">
        <h3 id="loading-preview-infinity" className="component-preview-title">Infinity Path</h3>
        <Loading />
      </section>
      <section aria-labelledby="loading-preview-ring">
        <h3 id="loading-preview-ring" className="component-preview-title">Ring Sweep</h3>
        <Loading variant="ring" />
      </section>
    </div>
    <ComponentApi names={["Loading"]} />
  </section>;
}
