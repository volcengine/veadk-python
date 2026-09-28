import { useTranslation } from "react-i18next";
import { FormField } from "../components/composites/FormField";
import { InputWithTailIcon } from "../components/primitives/InputWithTailIcon";
import { DATASET_COUNT_MAX, DATASET_COUNT_MIN, datasetCountError } from "./datasetCount";

interface Props {
  id: string;
  label: string;
  value: string;
  disabled: boolean;
  onChange: (value: string) => void;
}

export function DatasetCountField({ id, label, value, disabled, onChange }: Props) {
  const { t } = useTranslation("ui");
  const error = datasetCountError(value);
  const message = (key: string) => t(`agentWorkspace.qualityManagement.countValidation.${key}`, { min: DATASET_COUNT_MIN, max: DATASET_COUNT_MAX });
  return <FormField label={label} htmlFor={id} tip={message("hint")} error={error ? message(error) : undefined}>
    <InputWithTailIcon id={id} tailIcon={null} type="number" inputMode="numeric" required min={DATASET_COUNT_MIN} max={DATASET_COUNT_MAX} step={1}
      disabled={disabled} value={value} onChange={event => onChange(event.target.value)} />
  </FormField>;
}
