import { useState } from "react";
import { today } from "@internationalized/date";
import { ComponentApi } from "../api/ComponentApi";
import { DatePicker } from "../../components/primitives/DatePicker";
import { FormField } from "../../components/composites/FormField";
import { Select } from "../../components/primitives/Select";
import "./DatePickerPreview.css";

export function DatePickerPreview() {
  const [zone, setZone] = useState("Asia/Shanghai");
  const [date, setDate] = useState("");
  const [runAt, setRunAt] = useState(() => `${today("Asia/Shanghai").add({ days: 1 })}T09:00`);
  const start = today(zone);
  return <section className="date-picker-preview" aria-labelledby="date-picker-preview-title">
    <h2 id="date-picker-preview-title" className="component-preview-title">Date Picker</h2>
    <div className="date-picker-preview__examples">
      <section className="date-picker-preview__example">
        <h3>日期</h3>
        <FormField label="选择日期" htmlFor="date-picker-basic" tip="支持日历选择，也可以直接修改年月日">
          <DatePicker id="date-picker-basic" aria-label="选择日期" value={date} onChange={setDate} />
        </FormField>
      </section>
      <section className="date-picker-preview__example">
        <h3>定时任务 · 单次执行</h3>
        <FormField label="执行时间" htmlFor="date-picker-schedule" required>
          <DatePicker id="date-picker-schedule" aria-label="执行时间" granularity="minute" value={runAt} onChange={setRunAt} timeZone={zone} required />
        </FormField>
        <FormField label="时区" htmlFor="date-picker-timezone">
          <Select id="date-picker-timezone" aria-label="时区" value={zone} onChange={event => setZone(event.target.value)} options={[
            { value: "Asia/Shanghai", label: "Asia/Shanghai" },
            { value: "Asia/Singapore", label: "Asia/Singapore" },
            { value: "America/Los_Angeles", label: "America/Los_Angeles" },
            { value: "UTC", label: "UTC" },
          ]} />
        </FormField>
        <p className="date-picker-preview__summary" aria-live="polite">{runAt ? `${runAt.replace("T", " ")} · ${zone}` : "请选择执行时间"}</p>
      </section>
      <section className="date-picker-preview__example">
        <h3>日期范围限制</h3>
        <FormField label="执行日期" htmlFor="date-picker-limits" tip="仅允许选择今天至 30 天后的日期">
          <DatePicker id="date-picker-limits" aria-label="执行日期" minValue={start.toString()} maxValue={start.add({ days: 30 }).toString()} timeZone={zone} />
        </FormField>
      </section>
      <section className="date-picker-preview__example">
        <h3>状态</h3>
        <FormField label="只读" htmlFor="date-picker-readonly"><DatePicker id="date-picker-readonly" aria-label="只读日期" defaultValue={start.toString()} readOnly /></FormField>
        <FormField label="禁用" htmlFor="date-picker-disabled"><DatePicker id="date-picker-disabled" aria-label="禁用日期" defaultValue={start.toString()} disabled /></FormField>
        <FormField label="校验错误" htmlFor="date-picker-invalid" error="请选择有效的执行时间"><DatePicker id="date-picker-invalid" aria-label="校验错误" granularity="minute" /></FormField>
      </section>
    </div>
    <ComponentApi names={["DatePicker"]} />
  </section>;
}
