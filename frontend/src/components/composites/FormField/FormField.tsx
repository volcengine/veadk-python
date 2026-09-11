import { Children, cloneElement, isValidElement, useId, type ComponentProps, type ReactNode } from "react";
import { FormLabel } from "../../primitives/FormLabel";
import "./FormField.css";

export type FormFieldProps = ComponentProps<"div"> & {
  label: ReactNode;
  htmlFor: string;
  required?: boolean;
  /** 控件下方的输入规则或辅助提示 */
  tip?: ReactNode;
  /** 错误提示，优先于 tip；为对应控件设置 aria-invalid 并显示红色边框 */
  error?: ReactNode;
};

type DescribedControlProps = Pick<ComponentProps<"input">, "id" | "aria-describedby" | "aria-invalid"> & { children?: ReactNode };

function describeControl(children: ReactNode, controlId: string, messageId: string | undefined, invalid: boolean): ReactNode {
  return Children.map(children, child => {
    if (!isValidElement<DescribedControlProps>(child)) return child;
    if (child.props.id === controlId) {
      const descriptionIds = new Set(child.props["aria-describedby"]?.split(/\s+/).filter(Boolean));
      if (messageId) descriptionIds.add(messageId);
      return cloneElement(child, {
        "aria-describedby": [...descriptionIds].join(" ") || undefined,
        "aria-invalid": invalid ? true : child.props["aria-invalid"],
      });
    }
    if (child.props.children !== undefined) {
      return cloneElement(child, { children: describeControl(child.props.children, controlId, messageId, invalid) });
    }
    return child;
  });
}

export function FormField({ label, htmlFor, required = false, tip, error, children, className = "", ...props }: FormFieldProps) {
  const descriptionId = useId();
  const hasError = error != null && typeof error !== "boolean" && error !== "";
  const message = hasError ? error : tip;
  const hasMessage = message != null && typeof message !== "boolean" && message !== "";
  return (
    <div {...props} className={`studio-form-field ${className}`.trim()} data-invalid={hasError || undefined}>
      {required ? <FormLabel htmlFor={htmlFor} required>{label}</FormLabel> : <label className="studio-form-field__label" htmlFor={htmlFor}>{label}</label>}
      {describeControl(children, htmlFor, hasMessage ? descriptionId : undefined, hasError)}
      {hasMessage && <p key={hasError ? "error" : "tip"} id={descriptionId} className="studio-form-field__message" role={hasError ? "alert" : undefined}>{message}</p>}
    </div>
  );
}
