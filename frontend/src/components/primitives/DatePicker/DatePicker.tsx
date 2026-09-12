import { useContext, type AriaAttributes, type CSSProperties } from "react";
import {
  Button as AriaButton, Calendar, CalendarCell, CalendarGrid, CalendarGridBody,
  CalendarGridHeader, CalendarHeaderCell, DateInput, DatePicker as AriaDatePicker,
  DatePickerStateContext, DateSegment, Dialog, FieldError, Group, Heading,
  I18nProvider, Popover, TimeField,
} from "react-aria-components";
import { getLocalTimeZone, today, toCalendarDateTime, toTime, type DateValue } from "@internationalized/date";
import { Button } from "../Button";
import { formatPickerValue, parsePickerValue, type DatePickerGranularity } from "./dateValue";
import "./DatePicker.css";

export interface DatePickerProps {
  /** 日期 YYYY-MM-DD；日期时间 YYYY-MM-DDTHH:mm；空字符串或 null 清空 */
  value?: string | null;
  /** 非受控初始值，格式与 value 相同 */
  defaultValue?: string;
  /** 返回日期字符串，清空时返回空字符串；不进行时区转换 */
  onChange?: (value: string) => void;
  /** day 只选日期；minute 同时选择日期与时间，默认 day */
  granularity?: DatePickerGranularity;
  /** 最早可选日期或时间，包含边界；仅日期在 minute 模式下按 00:00 处理 */
  minValue?: string;
  /** 最晚可选日期或时间，包含边界；仅日期在 minute 模式下按 23:59 处理 */
  maxValue?: string;
  /** 日期显示与无障碍文案的语言，默认 zh-CN */
  locale?: string;
  /** IANA 时区，用于计算今天；value 始终保留该时区的当地时间，不自动转换 */
  timeZone?: string;
  /** 空值时日历打开的参考日期，minute 模式默认时间为 09:00；不代表已选中 */
  placeholderValue?: string;
  disabled?: boolean;
  readOnly?: boolean;
  required?: boolean;
  /** 默认 24 小时制，可使用 12 小时制 */
  hourCycle?: 12 | 24;
  open?: boolean;
  defaultOpen?: boolean;
  onOpenChange?: (open: boolean) => void;
  id?: string;
  name?: string;
  className?: string;
  style?: CSSProperties;
  "aria-label"?: string;
  "aria-labelledby"?: string;
  "aria-describedby"?: string;
  "aria-invalid"?: AriaAttributes["aria-invalid"];
}

function CalendarIcon() {
  return <svg aria-hidden="true" width="16" height="16" viewBox="0 0 16 16" fill="none"><rect x="2.25" y="3.25" width="11.5" height="10.5" rx="2" stroke="currentColor" strokeWidth="1.2" /><path d="M5 2v2.5M11 2v2.5M2.5 6.5h11M5.25 9h.5M8 9h.5M10.75 9h.5M5.25 11.5h.5M8 11.5h.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" /></svg>;
}

function Chevron({ next = false }: { next?: boolean }) {
  return <svg aria-hidden="true" width="14" height="14" viewBox="0 0 16 16" fill="none" style={{ transform: next ? "rotate(180deg)" : undefined }}><path d="m9.5 4-4 4 4 4" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" /></svg>;
}

function TimeControls({ locale, hourCycle, timeZone, placeholder, minimum, maximum }: {
  locale: string; hourCycle: 12 | 24; timeZone?: string;
  placeholder: DateValue; minimum?: DateValue; maximum?: DateValue;
}) {
  const state = useContext(DatePickerStateContext)!;
  const chinese = locale.startsWith("zh");
  const time = state.timeValue ?? toTime(toCalendarDateTime(placeholder));
  const candidate = state.dateValue ? toCalendarDateTime(state.dateValue, time) : null;
  const outsideBounds = candidate && ((minimum && candidate.compare(minimum) < 0) || (maximum && candidate.compare(maximum) > 0));
  return <div className="studio-date-picker__footer">
    <div className="studio-date-picker__time-row">
      <span>{chinese ? "时间" : "Time"}</span>
      <TimeField
        aria-label={chinese ? "执行时间" : "Execution time"}
        value={time}
        onChange={value => { if (value) state.setTimeValue(value); }}
        granularity="minute" hourCycle={hourCycle} shouldForceLeadingZeros
        className="studio-date-picker__time"
      >
        <DateInput className="studio-date-picker__segments">
          {segment => <DateSegment segment={segment} className="studio-date-picker__segment" />}
        </DateInput>
      </TimeField>
    </div>
    <div className="studio-date-picker__footer-actions">
      <span className="studio-date-picker__timezone" title={timeZone}>{timeZone}</span>
      <Button className="studio-date-picker__done" disabled={!candidate || Boolean(outsideBounds) || state.isInvalid} onClick={() => state.setOpen(false)}>{chinese ? "完成" : "Done"}</Button>
    </div>
  </div>;
}

/** Figma 风格的分段日期输入与日历面板，可用于定时任务的当地执行时间 */
export function DatePicker({
  value, defaultValue, onChange, granularity = "day", minValue, maxValue,
  locale = "zh-CN", timeZone, placeholderValue, disabled, readOnly, required,
  hourCycle = 24, open, defaultOpen, onOpenChange, className = "", style,
  "aria-invalid": invalid, "aria-label": ariaLabel, "aria-labelledby": labelledBy,
  ...props
}: DatePickerProps) {
  const referenceDate = today(timeZone ?? getLocalTimeZone());
  const placeholder = parsePickerValue(placeholderValue, granularity) ??
    (granularity === "minute" ? toCalendarDateTime(referenceDate).set({ hour: 9 }) : referenceDate);
  const minimum = parsePickerValue(minValue, granularity, "min") ?? undefined;
  const maximum = parsePickerValue(maxValue, granularity, "max") ?? undefined;
  if (minimum && maximum && minimum.compare(maximum) > 0) throw new RangeError("DatePicker minValue must not exceed maxValue");

  return <I18nProvider locale={locale}>
    <AriaDatePicker
      {...props}
      {...(value !== undefined ? { value: parsePickerValue(value, granularity) } : { defaultValue: parsePickerValue(defaultValue, granularity) })}
      onChange={next => onChange?.(formatPickerValue(next, granularity))}
      granularity={granularity} placeholderValue={placeholder}
      minValue={minimum} maxValue={maximum}
      isDisabled={disabled} isReadOnly={readOnly} isRequired={required}
      isInvalid={invalid === true || invalid === "true" || invalid === "grammar" || invalid === "spelling"}
      isOpen={disabled || readOnly ? false : open} defaultOpen={defaultOpen}
      onOpenChange={onOpenChange} shouldCloseOnSelect={granularity === "day"}
      hourCycle={hourCycle} shouldForceLeadingZeros
      aria-label={ariaLabel ?? (labelledBy ? undefined : locale.startsWith("zh") ? "选择日期" : "Choose date")}
      aria-labelledby={labelledBy}
      className={`studio-date-picker ${className}`.trim()} style={style}
    >
      <Group className="studio-date-picker__field">
        <DateInput className="studio-date-picker__segments">
          {segment => <DateSegment segment={segment} className="studio-date-picker__segment" />}
        </DateInput>
        <AriaButton className="studio-date-picker__icon-button"><CalendarIcon /></AriaButton>
      </Group>
      <FieldError className="studio-date-picker__error" />
      <Popover className="studio-date-picker__popover" placement="bottom start" offset={6} containerPadding={8}>
        <Dialog className="studio-date-picker__dialog">
          <Calendar className="studio-date-picker__calendar" firstDayOfWeek="mon">
            <header className="studio-date-picker__calendar-header">
              <Heading />
              <div className="studio-date-picker__navigation">
                <AriaButton slot="previous" className="studio-date-picker__icon-button"><Chevron /></AriaButton>
                <AriaButton slot="next" className="studio-date-picker__icon-button"><Chevron next /></AriaButton>
              </div>
            </header>
            <CalendarGrid className="studio-date-picker__grid" weekdayStyle="short">
              <CalendarGridHeader>{day => <CalendarHeaderCell className="studio-date-picker__weekday">{day}</CalendarHeaderCell>}</CalendarGridHeader>
              <CalendarGridBody>{date => <CalendarCell date={date} data-today={date.compare(referenceDate) === 0 || undefined} className="studio-date-picker__day" />}</CalendarGridBody>
            </CalendarGrid>
          </Calendar>
          {granularity === "minute" && <TimeControls locale={locale} hourCycle={hourCycle} timeZone={timeZone} placeholder={placeholder} minimum={minimum} maximum={maximum} />}
        </Dialog>
      </Popover>
    </AriaDatePicker>
  </I18nProvider>;
}
