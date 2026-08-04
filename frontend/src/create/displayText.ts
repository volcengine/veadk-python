/** Keep compact UI descriptions visually clean without mutating source data. */
export function displayDescription(value: string): string {
  return value.trimEnd().replace(/[。.]+$/, "");
}
