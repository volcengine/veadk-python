import { useState } from "react";
import { Slider } from "../../components/primitives/Slider";

import "./SliderPreview.css";

export function SliderPreview() {
  const [volume, setVolume] = useState(65);
  return (
    <section aria-labelledby="slider-preview-title">
      <h2 data-preview-heading tabIndex={-1} id="slider-preview-title" className="component-preview-title">Default</h2>
      <Slider label="音量" name="volume" value={volume} onValueChange={setVolume} />
      <section className="components-preview-variant" aria-labelledby="slider-decimal-title">
        <h2 data-preview-heading tabIndex={-1} id="slider-decimal-title">Decimal Step</h2>
        <Slider label="温度" name="temperature" min={0} max={1} step={0.05} defaultValue={0.7} valueFormat={value => value.toFixed(2)} />
      </section>
      <section className="components-preview-variant" aria-labelledby="slider-disabled-title">
        <h2 data-preview-heading tabIndex={-1} id="slider-disabled-title">Disabled</h2>
        <Slider label="音量（禁用）" defaultValue={65} disabled />
      </section>
    </section>
  );
}
