/** Match a local picker row against a case-insensitive keyword. */
export function localPickerMatches(
  query: string,
  values: Array<string | undefined>,
): boolean {
  const keyword = query.trim().toLocaleLowerCase();
  if (!keyword) return true;
  return values.some((value) => value?.toLocaleLowerCase().includes(keyword));
}
