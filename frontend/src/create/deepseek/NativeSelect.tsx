import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { DeploymentSelect } from "../../ui/DeploymentSelect";

// UI-only option, never written into the configuration
const CUSTOM_OPTION = "\u0000custom";

interface Props {
  label: string;
  value: string;
  options: readonly string[];
  onChange: (value: string) => void;
  allowCustom?: boolean;
  allowEmpty?: boolean;
  disabled?: boolean;
  placeholder?: string;
  error?: string;
  describedBy?: string;
}

export function NativeSelect({ label, value, options, onChange, allowCustom = false, allowEmpty = true, disabled = false, placeholder, error, describedBy }: Props) {
  const { t } = useTranslation("deepseek");
  const id = useId();
  const [editingCustom, setEditingCustom] = useState(false);
  const custom = allowCustom && (editingCustom || Boolean(value && !options.includes(value)));
  return (
    <div className="dsh-native-choice">
      <DeploymentSelect
        ariaLabel={label}
        value={custom ? CUSTOM_OPTION : value}
        valueLabel={value}
        placeholder={placeholder ?? t("optional")}
        disabled={disabled}
        options={[
          ...(allowEmpty ? [{ value: "", label: t("optional") }] : []),
          ...options.map((option) => ({ value: option, label: option })),
          ...(allowCustom ? [{ value: CUSTOM_OPTION, label: t("customValue") }] : []),
        ]}
        onChange={(next) => {
          setEditingCustom(next === CUSTOM_OPTION);
          if (next !== CUSTOM_OPTION) onChange(next);
        }}
      />
      {custom && (
        <div className="dsh-custom-value">
          <label className="cw-label" htmlFor={id}>{t("customField", { field: label })}</label>
          <input id={id} className="cw-input" value={value} autoComplete="off" spellCheck={false}
            placeholder={t("enterCustomValue")} aria-invalid={Boolean(error)} aria-describedby={describedBy}
            onChange={(event) => onChange(event.target.value)} />
        </div>
      )}
    </div>
  );
}
