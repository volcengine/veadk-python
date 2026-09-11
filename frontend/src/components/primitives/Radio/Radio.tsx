import { useId, type ComponentProps, type ReactNode } from "react";
import "./Radio.css";

export type RadioProps = Omit<ComponentProps<"input">, "type" | "children"> & {
  /** 可选标签；不显示标签时请设置 aria-label 或 aria-labelledby */
  label?: ReactNode;
};

function RadioControl(props: Omit<RadioProps, "label">) {
  return <span className="studio-radio__control">
    <input {...props} className="studio-radio__input" type="radio" />
    <span className="studio-radio__box" aria-hidden="true"><span className="studio-radio__dot" /></span>
  </span>;
}

export function Radio({ label, className = "", ...props }: RadioProps) {
  return (
    <label className={`studio-radio ${className}`.trim()}>
      <RadioControl {...props} />
      {label != null && <span className="studio-radio__label">{label}</span>}
    </label>
  );
}

export type RadioCardProps = Omit<RadioProps, "label" | "title" | "style"> & {
  /** 卡片主标题 */
  title: ReactNode;
  /** 标题下方的描述 */
  description?: ReactNode;
  /** 左侧 20px 图标，放在 44px 的图标容器内 */
  icon?: ReactNode;
  /** 卡片容器样式 */
  style?: ComponentProps<"label">["style"];
};

export function RadioCard({ title, description, icon, className = "", style, ...props }: RadioCardProps) {
  const id = useId();
  const titleId = `${id}-title`;
  const descriptionId = `${id}-description`;
  const describedBy = [props["aria-describedby"], description != null ? descriptionId : undefined].filter(Boolean).join(" ") || undefined;
  return <label className={`studio-radio studio-radio-card ${className}`.trim()} style={style}>
    {icon != null && <span className="studio-radio-card__icon" aria-hidden="true">{icon}</span>}
    <span className="studio-radio-card__content">
      <span className="studio-radio-card__title" id={titleId}>{title}</span>
      {description != null && <span className="studio-radio-card__description" id={descriptionId}>{description}</span>}
    </span>
    <RadioControl
      {...props}
      aria-labelledby={props["aria-labelledby"] ?? (props["aria-label"] ? undefined : titleId)}
      aria-describedby={describedBy}
    />
  </label>;
}
