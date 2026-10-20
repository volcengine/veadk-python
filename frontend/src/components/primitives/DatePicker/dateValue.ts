import { parseDate, parseDateTime, toCalendarDate, toCalendarDateTime, type DateValue } from "@internationalized/date";

export type DatePickerGranularity = "day" | "minute";

/** Keep schedule values as wall-clock dates; the task owns their time zone */
export function parsePickerValue(value: string | null | undefined, granularity: DatePickerGranularity, boundary?: "min" | "max"): DateValue | null {
  if (!value) return null;
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    const date = parseDate(value);
    if (granularity === "day") return date;
    return toCalendarDateTime(date).set(boundary === "max" ? { hour: 23, minute: 59 } : { hour: 0, minute: 0 });
  }
  if (granularity === "minute" && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d{1,3})?)?$/.test(value)) {
    return parseDateTime(value).set({ second: 0, millisecond: 0 });
  }
  throw new RangeError(`DatePicker expects ${granularity === "day" ? "YYYY-MM-DD" : "YYYY-MM-DDTHH:mm"} without a time-zone suffix`);
}

export function formatPickerValue(value: DateValue | null, granularity: DatePickerGranularity): string {
  if (!value) return "";
  return granularity === "day" ? toCalendarDate(value).toString() : toCalendarDateTime(value).toString().slice(0, 16);
}
