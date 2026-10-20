import { useEffect, useId, useRef, useState, type ComponentProps, type CSSProperties, type ReactNode } from "react";
import "./Slider.css";

export type SliderProps = Omit<ComponentProps<"input">, "type" | "children" | "size" | "value" | "defaultValue" | "onChange" | "min" | "max" | "step"> & {
  label: ReactNode;
  /** 受控数值 */
  value?: number;
  /** 非受控初始数值，默认等于 min */
  defaultValue?: number;
  onValueChange?: (value: number) => void;
  min?: number;
  max?: number;
  step?: number | "any";
  /** 是否在 label 右侧显示数值 */
  showValue?: boolean;
  /** 格式化显示值，同时作为屏幕阅读器读取的数值 */
  valueFormat?: (value: number) => string;
};

function normalizeValue(value: number, min: number, max: number, step: number | "any") {
  if (max <= min) return min;
  const bounded = Math.min(max, Math.max(min, value));
  if (step === "any") return bounded;
  const increment = step > 0 ? step : 1;
  const lastStep = Math.floor((max - min) / increment + 1e-9);
  const nearestStep = Math.min(lastStep, Math.round((bounded - min) / increment));
  return Number((min + nearestStep * increment).toPrecision(12));
}

export function Slider({
  label,
  value,
  min = 0,
  max = 100,
  step = 1,
  defaultValue = min,
  onValueChange,
  showValue = true,
  valueFormat,
  disabled = false,
  id,
  className = "",
  style,
  ...props
}: SliderProps) {
  const generatedId = useId();
  const inputId = id ?? generatedId;
  const [localValue, setLocalValue] = useState(defaultValue);
  const [dragging, setDragging] = useState(false);
  const thumbRef = useRef<HTMLSpanElement>(null);
  const pointerStart = useRef<{ id: number; x: number; y: number } | null>(null);

  useEffect(() => {
    const ownerWindow = thumbRef.current?.ownerDocument.defaultView ?? window;
    const finishPointer = (event: PointerEvent | FocusEvent) => {
      if ("pointerId" in event && event.pointerId !== pointerStart.current?.id) return;
      pointerStart.current = null;
      setDragging(false);
    };
    ownerWindow.addEventListener("pointerup", finishPointer, true);
    ownerWindow.addEventListener("pointercancel", finishPointer, true);
    ownerWindow.addEventListener("blur", finishPointer);
    return () => {
      ownerWindow.removeEventListener("pointerup", finishPointer, true);
      ownerWindow.removeEventListener("pointercancel", finishPointer, true);
      ownerWindow.removeEventListener("blur", finishPointer);
    };
  }, []);

  const current = normalizeValue(value ?? localValue, min, max, step);
  const displayValue = valueFormat ? valueFormat(current) : String(current);
  const progress = max > min ? (current - min) / (max - min) * 100 : 0;

  return (
    <div
      className={`studio-slider ${className}`.trim()}
      style={{ ...style, "--slider-progress": `${progress}%`, "--slider-ratio": progress / 100 } as CSSProperties}
      dir={props.dir}
      data-disabled={disabled || undefined}
      data-dragging={dragging || undefined}
    >
      <div className="studio-slider__header">
        <label htmlFor={inputId} className="studio-slider__label">{label}</label>
        {showValue && <output htmlFor={inputId} className="studio-slider__value" aria-hidden="true">{displayValue}</output>}
      </div>
      <div className="studio-slider__control">
        <span className="studio-slider__track" aria-hidden="true">
          <span className="studio-slider__fill" />
        </span>
        <input
          {...props}
          id={inputId}
          type="range"
          className="studio-slider__input"
          min={min}
          max={max}
          step={step}
          value={current}
          disabled={disabled}
          aria-valuetext={props["aria-valuetext"] ?? (valueFormat ? displayValue : undefined)}
          onPointerDown={event => {
            props.onPointerDown?.(event);
            if (disabled || event.defaultPrevented || event.button !== 0) return;
            pointerStart.current = { id: event.pointerId, x: event.clientX, y: event.clientY };
            const thumb = thumbRef.current?.getBoundingClientRect();
            setDragging(Boolean(thumb && event.clientX >= thumb.left && event.clientX <= thumb.right));
          }}
          onPointerMove={event => {
            props.onPointerMove?.(event);
            const start = pointerStart.current;
            if (disabled || event.defaultPrevented || !start || event.pointerId !== start.id) return;
            if (Math.hypot(event.clientX - start.x, event.clientY - start.y) > 2) setDragging(true);
          }}
          onChange={event => {
            const next = event.currentTarget.valueAsNumber;
            if (value === undefined) setLocalValue(next);
            onValueChange?.(next);
          }}
        />
        <span ref={thumbRef} className="studio-slider__thumb" aria-hidden="true" />
      </div>
    </div>
  );
}
