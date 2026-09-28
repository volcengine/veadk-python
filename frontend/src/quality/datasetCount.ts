export const DATASET_COUNT_MIN = 50;
export const DATASET_COUNT_MAX = 300;
export const DATASET_COUNT_DEFAULT = 100;

export function datasetCountError(value: string) {
  if (!value.trim()) return "required";
  const count = Number(value);
  if (!Number.isInteger(count)) return "integer";
  if (count < DATASET_COUNT_MIN || count > DATASET_COUNT_MAX) return "range";
  return null;
}
