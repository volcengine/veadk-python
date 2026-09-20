import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { DialogShell } from "../ui/SandboxControls";
import { DeploymentSelect } from "../ui/DeploymentSelect";
import type { MpaCronTask, TaskFields } from "../adk/mpaCronTasks";
import { scheduleTypes } from "./mpaSchedule";
import { MpaIcon } from "./MpaTaskIcons";

export function MpaTaskEditor({
  task,
  copy,
  busy,
  error,
  onClose,
  onSave,
}: {
  task?: MpaCronTask;
  copy: boolean;
  busy: boolean;
  error: string;
  onClose: () => void;
  onSave: (fields: TaskFields) => void;
}) {
  const { t } = useTranslation("cronjobs");
  const label = (key: string) => t(`mpa.manage.${key}`);
  const initial = task?.schedule;
  const [name, setName] = useState(
    task ? task.name + (copy ? ` (${label("copy")})` : "") : "",
  );
  const [prompt, setPrompt] = useState(task?.prompt || "");
  const [type, setType] = useState(initial?.type || "Daily");
  const [zone, setZone] = useState(
    String(initial?.timezone || "Asia/Shanghai"),
  );
  const [time, setTime] = useState(String(initial?.time || "09:00"));
  const [date, setDate] = useState(() => {
    if (!initial?.runAt) return "";
    const d = new Date(String(initial.runAt));
    return new Date(d.getTime() - d.getTimezoneOffset() * 60000)
      .toISOString()
      .slice(0, 16);
  });
  const [interval, setInterval] = useState(
    String(initial?.intervalSeconds || 3600),
  );
  const [days, setDays] = useState(String(initial?.weekdays || "1,2,3,4,5"));
  const [monthDays, setMonthDays] = useState(String(initial?.monthDays || "1"));
  const [cron, setCron] = useState(
    String(initial?.cronExpression || "0 9 * * *"),
  );
  const [enabled, setEnabled] = useState(task?.enabled ?? true);
  const [channel, setChannel] = useState(
    String(task?.delivery?.channel || "Web"),
  );
  const [target, setTarget] = useState(String(task?.delivery?.targetId || ""));
  const [validation, setValidation] = useState("");
  const composing = useRef(false);
  const nameRef = useRef<HTMLInputElement>(null);
  function save() {
    if (busy || composing.current) return;
    try {
      new Intl.DateTimeFormat("en-US", { timeZone: zone });
    } catch {
      setValidation(label("timezoneInvalid"));
      return;
    }
    const schedule: TaskFields["schedule"] = { type, timezone: zone };
    if (type === "Once") {
      const at = Date.parse(date);
      if (!Number.isFinite(at) || at <= Date.now()) {
        setValidation(label("futureTime"));
        return;
      }
      schedule.runAt = new Date(at).toISOString();
    } else if (type === "Interval") {
      const seconds = Number(interval);
      if (!Number.isInteger(seconds) || seconds < 30 || seconds > 31536000) {
        setValidation(label("intervalInvalid"));
        return;
      }
      schedule.intervalSeconds = seconds;
      if (initial?.type === type && initial.anchorAt)
        schedule.anchorAt = initial.anchorAt;
    } else if (type === "Cron") {
      if (cron.trim().split(/\s+/).length !== 5) {
        setValidation(t("validation.cronFields"));
        return;
      }
      schedule.cronExpression = cron.trim();
    } else {
      schedule.time = time;
      if (type === "Weekly" || type === "Monthly") {
        const value = (type === "Weekly" ? days : monthDays)
          .split(",")
          .map(Number);
        const max = type === "Weekly" ? 7 : 31;
        if (
          !value.length ||
          value.some((n) => !Number.isInteger(n) || n < 1 || n > max) ||
          new Set(value).size !== value.length
        ) {
          setValidation(label("daysInvalid"));
          return;
        }
        schedule[type === "Weekly" ? "weekdays" : "monthDays"] = value;
      }
    }
    if (
      !name.trim() ||
      !prompt.trim() ||
      (channel === "Feishu" && !target.trim())
    ) {
      setValidation(label("required"));
      return;
    }
    const delivery =
      task?.delivery?.channel === channel &&
      String(task.delivery.targetId || "") === target
        ? task.delivery
        : {
            channel,
            targetId: channel === "Web" ? null : target.trim(),
            receiveIdType: "chat_id",
            bestEffort: true,
          };
    setValidation("");
    onSave({
      name: name.trim(),
      ...(task?.agentId ? { agentId: task.agentId } : {}),
      prompt: prompt.trim(),
      enabled,
      schedule,
      delivery,
      jitterSeconds: task?.jitterSeconds ?? 0,
      timeoutSeconds: task?.timeoutSeconds ?? 3600,
    });
  }
  return (
    <DialogShell
      open
      title={label(task && !copy ? "edit" : "create")}
      icon={<MpaIcon kind="edit" />}
      className="mpa-dialog"
      initialFocusRef={nameRef}
      busy={busy}
      onClose={onClose}
    >
      <form
        onSubmit={(e) => {
          e.preventDefault();
          save();
        }}
        onCompositionStart={() => {
          composing.current = true;
        }}
        onCompositionEnd={() => {
          composing.current = false;
        }}
        onKeyDown={(e) => {
          if (
            e.key === "Enter" &&
            (composing.current ||
              e.nativeEvent.isComposing ||
              e.keyCode === 229)
          )
            e.preventDefault();
        }}
      >
        <div className="sandbox-control-body mpa-editor">
          <fieldset disabled={busy}>
            <label>
              {label("name")}
              <input
                ref={nameRef}
                className="cw-input"
                required
                maxLength={128}
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            <label>
              {label("prompt")}
              <textarea
                className="cw-input"
                required
                maxLength={4000}
                rows={5}
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
              />
            </label>
            <div className="mpa-fields">
              <div>
                <span>{label("schedule")}</span>
                <DeploymentSelect
                  ariaLabel={label("schedule")}
                  placeholder=""
                  value={type}
                  options={scheduleTypes.map((value) => ({
                    value,
                    label: label(value),
                  }))}
                  onChange={setType}
                />
              </div>
              <label>
                {label("timezone")}
                <input
                  className="cw-input"
                  required
                  value={zone}
                  onChange={(e) => setZone(e.target.value)}
                />
              </label>
            </div>
            {type === "Once" ? (
              <label>
                {label("localTime")}
                <input
                  className="cw-input"
                  required
                  type="datetime-local"
                  value={date}
                  onChange={(e) => setDate(e.target.value)}
                />
              </label>
            ) : type === "Interval" ? (
              <label>
                {label("interval")}
                <input
                  className="cw-input"
                  required
                  type="number"
                  min={30}
                  max={31536000}
                  value={interval}
                  onChange={(e) => setInterval(e.target.value)}
                />
              </label>
            ) : type === "Cron" ? (
              <label>
                {label("Cron")}
                <input
                  className="cw-input"
                  required
                  value={cron}
                  maxLength={128}
                  onChange={(e) => setCron(e.target.value)}
                />
              </label>
            ) : (
              <label>
                {label("time")}
                <input
                  className="cw-input"
                  type="time"
                  required
                  value={time}
                  onChange={(e) => setTime(e.target.value)}
                />
              </label>
            )}
            {type === "Weekly" && (
              <label>
                {label("weekdays")}
                <input
                  className="cw-input"
                  required
                  value={days}
                  onChange={(e) => setDays(e.target.value)}
                />
              </label>
            )}
            {type === "Monthly" && (
              <label>
                {label("monthDays")}
                <input
                  className="cw-input"
                  required
                  value={monthDays}
                  onChange={(e) => setMonthDays(e.target.value)}
                />
              </label>
            )}
            <div>
              <span>{label("delivery")}</span>
              <DeploymentSelect
                ariaLabel={label("delivery")}
                placeholder=""
                value={channel}
                options={["Web", "Feishu"].map((value) => ({
                  value,
                  label: label(value),
                }))}
                onChange={setChannel}
              />
            </div>
            {channel === "Feishu" && (
              <label>
                {label("target")}
                <input
                  className="cw-input"
                  required
                  maxLength={512}
                  value={target}
                  onChange={(e) => setTarget(e.target.value)}
                />
              </label>
            )}
            <label className="mpa-checkbox">
              <input
                type="checkbox"
                checked={enabled}
                onChange={(e) => setEnabled(e.target.checked)}
              />
              {label("enabled")}
            </label>
          </fieldset>
          {(validation || error) && (
            <p role="alert" className="cw-error-text">
              {validation || error}
            </p>
          )}
        </div>
        <footer className="sandbox-control-actions">
          <button
            type="button"
            className="cw-btn cw-btn-ghost"
            disabled={busy}
            onClick={onClose}
          >
            {label("cancel")}
          </button>
          <button
            className="cw-btn cw-btn-primary is-primary"
            disabled={busy}
            type="submit"
          >
            {label(busy ? "saving" : "save")}
          </button>
        </footer>
      </form>
    </DialogShell>
  );
}
