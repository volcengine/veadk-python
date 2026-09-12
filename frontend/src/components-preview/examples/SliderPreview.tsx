import { useState } from "react";
import { Slider } from "../../components/primitives/Slider";
import { ComponentApi } from "../api/ComponentApi";
import "./SliderPreview.css";

export function SliderPreview() {
  const [volume, setVolume] = useState(65);
  return (
    <section aria-labelledby="slider-preview-title">
      <h2 id="slider-preview-title" className="component-preview-title">Slider</h2>
      <div className="slider-preview__examples">
        <Slider label="音量" name="volume" value={volume} onValueChange={setVolume} />
        <Slider label="温度" name="temperature" min={0} max={1} step={0.05} defaultValue={0.7} valueFormat={value => value.toFixed(2)} />
        <Slider label="音量（禁用）" defaultValue={65} disabled />
      </div>
      <ComponentApi names={["Slider"]} />
    </section>
  );
}
