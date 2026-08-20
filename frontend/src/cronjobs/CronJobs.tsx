import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
} from "react";
import {
  cancelCronJobRun,
  createCronJob,
  deleteCronJob,
  fetchRemoteApps,
  getRuntimes,
  listCronJobRuns,
  listCronJobs,
  runCronJobNow,
  setCronJobEnabled,
  updateCronJob,
  type CloudRuntime,
  type CronJob,
  type CronJobInput,
  type CronJobRun,
  type CronJobScheduleType,
} from "../adk/client";
import type { CloudProvider } from "../adk/cloudProvider";
import { formatCloudRegion } from "../adk/cloudProvider";
import { StudioConfirmDialog } from "../ui/StudioConfirmDialog";
import { DeploymentErrorMessage } from "../ui/DeploymentErrorMessage";
import { TextShimmer } from "../ui/text-shimmer/TextShimmer";
import {
  CronBackIcon,
  CronClockIcon,
  CronCloseIcon,
  CronDeleteIcon,
  CronEditIcon,
  CronPauseIcon,
  CronPlusIcon,
  CronRefreshIcon,
  CronRunIcon,
} from "./icons";
import {
  CRONJOB_STATUS_LABELS,
  WEEKDAY_LABELS,
  cronJobIsRunning,
  describeCronJobSchedule,
  formatCronJobDate,
  formatCronJobDuration,
} from "./model";
import "./CronJobs.css";

interface CronJobsProps {
  cloudProvider: CloudProvider;
}

interface CronJobDraft {
  name: string;
  runtimeId: string;
  prompt: string;
  scheduleType: CronJobScheduleType;
  onceAt: string;
  time: string;
  weekday: number;
  cron: string;
  timezone: string;
  enabled: boolean;
}

type ConfirmTarget =
  | { kind: "delete"; job: CronJob }
  | { kind: "cancel"; job: CronJob; run: CronJobRun };

const FALLBACK_TIMEZONE = "Asia/Shanghai";
const CRONJOB_ACTIVE_REFRESH_MS = 3_000;
const TIMEZONE_OPTIONS = [
  "Asia/Shanghai",
  "Asia/Singapore",
  "Asia/Tokyo",
  "Europe/London",
  "America/Los_Angeles",
  "America/New_York",
  "UTC",
];

function browserTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || FALLBACK_TIMEZONE;
  } catch {
    return FALLBACK_TIMEZONE;
  }
}

function emptyDraft(): CronJobDraft {
  const timezone = browserTimezone();
  const tomorrow = new Date(Date.now() + 24 * 60 * 60 * 1000);
  tomorrow.setSeconds(0, 0);
  const localTomorrow = new Date(
    tomorrow.getTime() - tomorrow.getTimezoneOffset() * 60_000,
  );
  return {
    name: "",
    runtimeId: "",
    prompt: "",
    scheduleType: "daily",
    onceAt: localTomorrow.toISOString().slice(0, 16),
    time: "09:00",
    weekday: 1,
    cron: "0 9 * * *",
    timezone,
    enabled: true,
  };
}

function draftFromJob(job: CronJob): CronJobDraft {
  return {
    name: job.name,
    runtimeId: job.runtimeId,
    prompt: job.prompt,
    scheduleType: job.schedule.type,
    onceAt: job.schedule.onceAt ?? "",
    time: job.schedule.time ?? "09:00",
    weekday: job.schedule.weekday ?? 1,
    cron: job.schedule.cron ?? "0 9 * * *",
    timezone: job.schedule.timezone || FALLBACK_TIMEZONE,
    enabled: job.enabled,
  };
}

function StatusBadge({ run }: { run?: CronJobRun }) {
  if (!run) return <span className="cronjobs-status is-idle">尚未执行</span>;
  return (
    <span className={`cronjobs-status is-${run.status}`}>
      <span aria-hidden="true" />
      {CRONJOB_STATUS_LABELS[run.status]}
    </span>
  );
}

function Drawer({
  job,
  runtimes,
  cloudProvider,
  busy,
  onClose,
  onSubmit,
}: {
  job: CronJob | null;
  runtimes: CloudRuntime[];
  cloudProvider: CloudProvider;
  busy: boolean;
  onClose: () => void;
  onSubmit: (input: CronJobInput) => Promise<void>;
}) {
  const [draft, setDraft] = useState<CronJobDraft>(() => job ? draftFromJob(job) : emptyDraft());
  const [error, setError] = useState("");
  const [resolvingRuntime, setResolvingRuntime] = useState(false);
  const drawerRef = useRef<HTMLElement>(null);
  const nameRef = useRef<HTMLInputElement>(null);
  const errorRef = useRef<HTMLDivElement>(null);
  const isBusy = busy || resolvingRuntime;
  const busyRef = useRef(isBusy);
  const onCloseRef = useRef(onClose);
  const zones = useMemo(() => Array.from(new Set([draft.timezone, ...TIMEZONE_OPTIONS])), [draft.timezone]);

  useEffect(() => {
    busyRef.current = isBusy;
    onCloseRef.current = onClose;
  }, [isBusy, onClose]);

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    document.body.style.overflow = "hidden";
    nameRef.current?.focus();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busyRef.current) {
        onCloseRef.current();
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = Array.from(
        drawerRef.current?.querySelectorAll<HTMLElement>(
          'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ) ?? [],
      ).filter((element) => !element.hidden && element.getClientRects().length > 0);
      if (focusable.length === 0) {
        event.preventDefault();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement;
      if (event.shiftKey && (active === first || !drawerRef.current?.contains(active))) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleKeyDown);
      if (previousFocus?.isConnected) previousFocus.focus();
    };
  }, []);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const name = draft.name.trim();
    const prompt = draft.prompt.trim();
    const runtime = runtimes.find((item) => item.runtimeId === draft.runtimeId);
    if (!name) return setError("请输入任务名称。");
    if (!runtime) return setError("请选择可用的 Runtime Agent。");
    if (!prompt) return setError("请输入每次执行时发送给 Agent 的文本。");
    if (draft.scheduleType === "once" && !draft.onceAt) return setError("请选择执行时间。");
    if ((draft.scheduleType === "daily" || draft.scheduleType === "weekly") && !draft.time) {
      return setError("请选择执行时间。");
    }
    const cronFields = draft.cron.trim().split(/\s+/);
    if (draft.scheduleType === "cron" && cronFields.length !== 5) {
      return setError("Cron 表达式需要包含 5 个字段，例如 0 9 * * *。");
    }
    setError("");
    setResolvingRuntime(true);
    try {
      let agentName = job?.runtimeId === runtime.runtimeId
        ? job.agentName.trim()
        : "";
      if (!agentName) {
        const [runtimeApp] = await fetchRemoteApps("", "", {
          runtimeId: runtime.runtimeId,
          region: runtime.region,
        });
        agentName = runtimeApp?.trim() ?? "";
      }
      if (!agentName) {
        throw new Error("Runtime Agent 未返回可调用的 appName，请确认 Runtime 已就绪且版本兼容。");
      }
      await onSubmit({
        name,
        runtimeId: runtime.runtimeId,
        runtimeName: runtime.name,
        agentName,
        region: runtime.region,
        prompt,
        enabled: draft.enabled,
        schedule: {
          type: draft.scheduleType,
          timezone: draft.timezone,
          ...(draft.scheduleType === "once" ? { onceAt: draft.onceAt } : {}),
          ...(draft.scheduleType === "daily" ? { time: draft.time } : {}),
          ...(draft.scheduleType === "weekly" ? { time: draft.time, weekday: draft.weekday } : {}),
          ...(draft.scheduleType === "cron" ? { cron: draft.cron.trim() } : {}),
        },
      });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
      window.requestAnimationFrame(() => errorRef.current?.focus());
    } finally {
      setResolvingRuntime(false);
    }
  };

  return (
    <div className="cronjobs-drawer-backdrop" onMouseDown={(event) => {
      if (event.target === event.currentTarget && !isBusy) onClose();
    }}>
      <aside ref={drawerRef} className="cronjobs-drawer" role="dialog" aria-modal="true" aria-labelledby="cronjobs-drawer-title">
        <header className="cronjobs-drawer-head">
          <div>
            <h2 id="cronjobs-drawer-title">{job ? "编辑定时任务" : "创建定时任务"}</h2>
            <p>每次触发都会为 Runtime Agent 创建独立 Session。</p>
          </div>
          <button type="button" className="cronjobs-icon-button" onClick={onClose} disabled={isBusy} aria-label="关闭抽屉">
            <CronCloseIcon />
          </button>
        </header>
        <form className="cronjobs-form" onSubmit={(event) => void submit(event)}>
          <div className="cronjobs-form-scroll">
            <label className="cronjobs-field">
              <span>任务名称</span>
              <input ref={nameRef} value={draft.name} maxLength={80} onChange={(event) => setDraft({ ...draft, name: event.target.value })} placeholder="例如：每日生成运营摘要" />
            </label>
            <label className="cronjobs-field">
              <span>Runtime Agent</span>
              <select value={draft.runtimeId} disabled={runtimes.length === 0} onChange={(event) => setDraft({ ...draft, runtimeId: event.target.value })}>
                <option value="">{runtimes.length ? "选择 Runtime Agent" : "暂无可用 Runtime"}</option>
                {runtimes.map((runtime) => (
                  <option key={runtime.runtimeId} value={runtime.runtimeId}>
                    {runtime.name} · {formatCloudRegion(runtime.region, cloudProvider)}
                  </option>
                ))}
              </select>
              <small>任务始终跟随该 Runtime 当前生效版本。</small>
            </label>
            <label className="cronjobs-field">
              <span>执行文本</span>
              <textarea value={draft.prompt} maxLength={20_000} onChange={(event) => setDraft({ ...draft, prompt: event.target.value })} placeholder="输入每次执行时发送给 Agent 的固定文本" />
              <small>{draft.prompt.length.toLocaleString()} / 20,000</small>
            </label>
            <fieldset className="cronjobs-fieldset">
              <legend>执行计划</legend>
              <div className="cronjobs-schedule-types" role="radiogroup" aria-label="执行计划类型">
                {(["once", "daily", "weekly", "cron"] as const).map((type) => (
                  <label key={type}>
                    <input type="radio" name="schedule-type" value={type} checked={draft.scheduleType === type} onChange={() => setDraft({ ...draft, scheduleType: type })} />
                    <span>{{ once: "一次性", daily: "每天", weekly: "每周", cron: "Cron" }[type]}</span>
                  </label>
                ))}
              </div>
              {draft.scheduleType === "once" ? (
                <label className="cronjobs-field"><span>执行时间</span><input type="datetime-local" value={draft.onceAt} onChange={(event) => setDraft({ ...draft, onceAt: event.target.value })} /></label>
              ) : null}
              {draft.scheduleType === "daily" ? (
                <label className="cronjobs-field"><span>每天执行时间</span><input type="time" value={draft.time} onChange={(event) => setDraft({ ...draft, time: event.target.value })} /></label>
              ) : null}
              {draft.scheduleType === "weekly" ? (
                <div className="cronjobs-inline-fields">
                  <label className="cronjobs-field"><span>星期</span><select value={draft.weekday} onChange={(event) => setDraft({ ...draft, weekday: Number(event.target.value) })}>{WEEKDAY_LABELS.map((label, index) => <option key={label} value={index}>{label}</option>)}</select></label>
                  <label className="cronjobs-field"><span>执行时间</span><input type="time" value={draft.time} onChange={(event) => setDraft({ ...draft, time: event.target.value })} /></label>
                </div>
              ) : null}
              {draft.scheduleType === "cron" ? (
                <label className="cronjobs-field"><span>Cron 表达式</span><input value={draft.cron} onChange={(event) => setDraft({ ...draft, cron: event.target.value })} placeholder="0 9 * * *" /><small>依次填写分钟、小时、日期、月份、星期。</small></label>
              ) : null}
              <label className="cronjobs-field"><span>时区</span><select value={draft.timezone} onChange={(event) => setDraft({ ...draft, timezone: event.target.value })}>{zones.map((zone) => <option key={zone} value={zone}>{zone}</option>)}</select></label>
            </fieldset>
            <label className="cronjobs-switch-row">
              <span><strong>创建后启用</strong><small>启用后会从下一个计划时间开始执行。</small></span>
              <input type="checkbox" checked={draft.enabled} onChange={(event) => setDraft({ ...draft, enabled: event.target.checked })} />
            </label>
            {error ? <div ref={errorRef} className="cronjobs-inline-error" role="alert" tabIndex={-1}>{error}</div> : null}
          </div>
          <footer className="cronjobs-drawer-actions">
            <button type="button" className="cronjobs-button is-secondary" onClick={onClose} disabled={isBusy}>取消</button>
            <button type="submit" className="cronjobs-button is-primary" disabled={isBusy || runtimes.length === 0} aria-busy={isBusy || undefined}>{resolvingRuntime ? "正在连接 Runtime…" : busy ? "保存中…" : job ? "保存更改" : "创建任务"}</button>
          </footer>
        </form>
      </aside>
    </div>
  );
}

function JobList({
  jobs,
  busyAction,
  onSelect,
  onEdit,
  onToggle,
  onRun,
}: {
  jobs: CronJob[];
  busyAction: string;
  onSelect: (job: CronJob) => void;
  onEdit: (job: CronJob) => void;
  onToggle: (job: CronJob) => void;
  onRun: (job: CronJob) => void;
}) {
  return (
    <div className="cronjobs-table-wrap">
      <table className="cronjobs-table">
        <thead><tr><th>任务名称</th><th>Runtime Agent</th><th>执行计划</th><th>状态</th><th>下次执行</th><th>最近结果</th><th><span className="sr-only">操作</span></th></tr></thead>
        <tbody>
          {jobs.map((job) => {
            const running = cronJobIsRunning(job);
            const busy = busyAction.includes(job.jobId);
            return (
              <tr key={job.jobId}>
                <td><button type="button" className="cronjobs-name-button" onClick={() => onSelect(job)} title={job.name}>{job.name}</button></td>
                <td data-label="Runtime Agent"><span className="cronjobs-agent" title={`${job.runtimeName} / ${job.agentName}`}><CronClockIcon />{job.runtimeName || job.agentName}</span></td>
                <td data-label="执行计划" title={describeCronJobSchedule(job.schedule)}>{describeCronJobSchedule(job.schedule)}</td>
                <td data-label="状态">{job.enabled ? <span className="cronjobs-enabled">已启用</span> : <span className="cronjobs-disabled">已暂停</span>}</td>
                <td data-label="下次执行">{job.enabled ? formatCronJobDate(job.nextRunAt) : "-"}</td>
                <td data-label="最近结果"><StatusBadge run={job.latestRun} /></td>
                <td className="cronjobs-actions-cell">
                  <div className="cronjobs-row-actions">
                    <button type="button" onClick={() => onRun(job)} disabled={busy || running || !job.enabled} title={running ? "已有执行正在进行" : !job.enabled ? "请先启用任务" : "立即执行"} aria-label={`立即执行 ${job.name}`}><CronRunIcon /></button>
                    <button type="button" onClick={() => onToggle(job)} disabled={busy} title={job.enabled ? "暂停" : "启用"} aria-label={`${job.enabled ? "暂停" : "启用"} ${job.name}`}>{job.enabled ? <CronPauseIcon /> : <CronRunIcon />}</button>
                    <button type="button" onClick={() => onEdit(job)} disabled={busy} title="编辑" aria-label={`编辑 ${job.name}`}><CronEditIcon /></button>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function JobDetail({
  job,
  runs,
  runsLoading,
  runsError,
  busyAction,
  onBack,
  onEdit,
  onToggle,
  onRun,
  onDelete,
  onCancel,
  onRetryRun,
  onRetryRuns,
}: {
  job: CronJob;
  runs: CronJobRun[];
  runsLoading: boolean;
  runsError: string;
  busyAction: string;
  onBack: () => void;
  onEdit: () => void;
  onToggle: () => void;
  onRun: () => void;
  onDelete: () => void;
  onCancel: (run: CronJobRun) => void;
  onRetryRun: () => Promise<void>;
  onRetryRuns: () => void;
}) {
  const latestRunning = runs.find((run) => run.status === "queued" || run.status === "running" || run.status === "retrying" || run.status === "pending") ?? (cronJobIsRunning(job) ? job.latestRun : undefined);
  const busy = busyAction.includes(job.jobId);
  return (
    <div className="cronjobs-detail">
      <header className="cronjobs-detail-head">
        <div className="cronjobs-detail-title">
          <button type="button" className="cronjobs-icon-button" onClick={onBack} aria-label="返回定时任务列表"><CronBackIcon /></button>
          <div><h1>{job.name}</h1><p>{job.runtimeName || job.agentName} · {describeCronJobSchedule(job.schedule)}</p></div>
        </div>
        <div className="cronjobs-detail-actions">
          <button type="button" className="cronjobs-button is-secondary" onClick={onEdit} disabled={busy}><CronEditIcon />编辑</button>
          <button type="button" className="cronjobs-button is-secondary" onClick={onToggle} disabled={busy}>{job.enabled ? <CronPauseIcon /> : <CronRunIcon />}{job.enabled ? "暂停" : "启用"}</button>
          {latestRunning ? <button type="button" className="cronjobs-button is-danger-quiet" onClick={() => onCancel(latestRunning)} disabled={busy || Boolean(latestRunning.cancellationRequestedAt)}>{latestRunning.cancellationRequestedAt ? (latestRunning.status === "queued" ? "取消中…" : "终止中…") : (latestRunning.status === "queued" ? "取消排队" : "终止本次执行")}</button> : <button type="button" className="cronjobs-button is-primary" onClick={onRun} disabled={busy || !job.enabled}><CronRunIcon />立即执行</button>}
          <button type="button" className="cronjobs-icon-button cronjobs-delete-action is-danger" onClick={onDelete} disabled={busy || Boolean(latestRunning)} aria-label="删除任务" title={latestRunning ? (latestRunning.status === "queued" ? "请先取消排队" : "请先终止当前执行") : "删除任务"}><CronDeleteIcon /><span>删除</span></button>
        </div>
      </header>
      <div className="cronjobs-detail-scroll">
        <section className="cronjobs-summary-grid" aria-label="任务配置">
          <dl><div><dt>任务状态</dt><dd>{job.enabled ? "已启用" : "已暂停"}</dd></div><div><dt>下次执行</dt><dd>{job.enabled ? formatCronJobDate(job.nextRunAt) : "-"}</dd></div><div><dt>Runtime</dt><dd title={job.runtimeName}>{job.runtimeName}</dd></div><div><dt>地域</dt><dd>{job.region}</dd></div></dl>
          <div className="cronjobs-prompt"><span>执行文本</span><p>{job.prompt}</p></div>
        </section>
        <section className="cronjobs-history">
          <header><div><h2>执行历史</h2><p>每次运行均使用独立 Session，结果与错误会永久保留。</p></div><button type="button" className="cronjobs-icon-button" onClick={onRetryRuns} disabled={runsLoading} aria-label="刷新执行历史" title="刷新"><CronRefreshIcon /></button></header>
          {runsLoading && runs.length === 0 ? <div className="cronjobs-history-state"><TextShimmer as="span" duration={2.4}>正在加载执行历史</TextShimmer></div> : runsError ? <div className="cronjobs-history-state is-error" role="alert"><p>{runsError}</p><button type="button" onClick={onRetryRuns}>重试</button></div> : runs.length === 0 ? <div className="cronjobs-history-state"><CronClockIcon /><p>暂无执行记录</p><span>任务触发或立即执行后，记录会显示在这里。</span></div> : (
            <div className="cronjobs-runs">
              {runs.map((run) => <article className="cronjobs-run" key={run.runId}>
                <div className="cronjobs-run-main"><StatusBadge run={run} /><div><strong>{formatCronJobDate(run.startedAt || run.scheduledAt)}</strong><span>耗时 {formatCronJobDuration(run)}{run.runtimeVersion ? ` · Runtime v${run.runtimeVersion}` : ""}</span></div></div>
                {run.sessionId ? <div className="cronjobs-run-meta"><span>Session</span><strong title={run.sessionId}>{run.sessionId}</strong></div> : null}
                {run.output ? <div className="cronjobs-run-output"><span>最终回答</span><p>{run.output}</p></div> : null}
                {run.error ? <div className="cronjobs-run-output is-error"><span>错误详情</span><DeploymentErrorMessage message={run.error} className="cronjobs-run-error-detail" defaultExpanded={false} onRetry={run.status === "failed" ? onRetryRun : undefined} retryLabel="重新执行" /></div> : null}
                {(run.status === "queued" || run.status === "running" || run.status === "retrying" || run.status === "pending") ? <button type="button" className="cronjobs-run-cancel" onClick={() => onCancel(run)} disabled={busy || Boolean(run.cancellationRequestedAt)}>{run.cancellationRequestedAt ? "终止中…" : run.status === "queued" ? "取消排队" : "终止执行"}</button> : null}
              </article>)}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

export function CronJobs({ cloudProvider }: CronJobsProps) {
  const [jobs, setJobs] = useState<CronJob[]>([]);
  const [runtimes, setRuntimes] = useState<CloudRuntime[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selectedId, setSelectedId] = useState("");
  const [drawerJob, setDrawerJob] = useState<CronJob | null | undefined>(undefined);
  const [runs, setRuns] = useState<CronJobRun[]>([]);
  const [runsLoading, setRunsLoading] = useState(false);
  const [runsError, setRunsError] = useState("");
  const [busyAction, setBusyAction] = useState("");
  const [notice, setNotice] = useState("");
  const [confirmTarget, setConfirmTarget] = useState<ConfirmTarget | null>(null);
  const [confirmError, setConfirmError] = useState("");
  const selectedJob = jobs.find((job) => job.jobId === selectedId);

  const load = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    setError("");
    try {
      const [items, runtimePage] = await Promise.all([
        listCronJobs(signal),
        getRuntimes({ scope: "all", region: "all", pageSize: 100 }),
      ]);
      if (signal?.aborted) return;
      setJobs(items);
      setRuntimes(runtimePage.runtimes.filter((runtime) => runtime.status.toLowerCase() === "ready"));
    } catch (cause) {
      if (signal?.aborted) return;
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);

  const loadRuns = useCallback(async (jobId: string, signal?: AbortSignal) => {
    setRunsLoading(true);
    setRunsError("");
    try {
      const items = await listCronJobRuns(jobId, signal);
      if (!signal?.aborted) setRuns(items);
    } catch (cause) {
      if (!signal?.aborted) setRunsError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      if (!signal?.aborted) setRunsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!selectedId) {
      setRuns([]);
      setRunsError("");
      return;
    }
    const controller = new AbortController();
    void loadRuns(selectedId, controller.signal);
    return () => controller.abort();
  }, [loadRuns, selectedId]);

  const hasActiveJob = jobs.some(cronJobIsRunning);
  useEffect(() => {
    if (!hasActiveJob) return;
    const controller = new AbortController();
    const refreshActiveState = async () => {
      try {
        const [nextJobs, nextRuns] = await Promise.all([
          listCronJobs(controller.signal),
          selectedId
            ? listCronJobRuns(selectedId, controller.signal)
            : Promise.resolve(null),
        ]);
        if (controller.signal.aborted) return;
        setJobs(nextJobs);
        if (nextRuns) setRuns(nextRuns);
      } catch (cause) {
        if (!controller.signal.aborted) {
          setNotice(cause instanceof Error ? cause.message : String(cause));
        }
      }
    };
    const timer = window.setInterval(
      () => void refreshActiveState(),
      CRONJOB_ACTIVE_REFRESH_MS,
    );
    return () => {
      window.clearInterval(timer);
      controller.abort();
    };
  }, [hasActiveJob, selectedId]);

  const replaceJob = (job: CronJob) => setJobs((current) => current.some((item) => item.jobId === job.jobId) ? current.map((item) => item.jobId === job.jobId ? job : item) : [job, ...current]);
  const runAction = async (
    key: string,
    action: () => Promise<void>,
    success: string,
    propagateError = false,
  ) => {
    setBusyAction(key);
    setNotice("");
    try {
      await action();
      setNotice(success);
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : String(cause);
      if (propagateError) throw new Error(message);
      setNotice(message);
    } finally {
      setBusyAction("");
    }
  };

  const submitDrawer = async (input: CronJobInput) => {
    const job = drawerJob ?? null;
    await runAction(`${job?.jobId ?? "new"}:save`, async () => {
      const saved = job ? await updateCronJob(job.jobId, input) : await createCronJob(input);
      replaceJob(saved);
      setDrawerJob(undefined);
      if (job) setSelectedId(saved.jobId);
    }, job ? "任务已更新。" : "任务已创建。", true);
  };

  const toggle = (job: CronJob) => void runAction(`${job.jobId}:toggle`, async () => replaceJob(await setCronJobEnabled(job.jobId, !job.enabled)), job.enabled ? "任务已暂停。" : "任务已启用。");
  const queueRun = (job: CronJob, success: string) => runAction(`${job.jobId}:run`, async () => {
    const run = await runCronJobNow(job.jobId);
    replaceJob({ ...job, latestRun: run });
    if (selectedId === job.jobId) setRuns((current) => [run, ...current.filter((item) => item.runId !== run.runId)]);
  }, success);
  const runNow = (job: CronJob) => void queueRun(job, "任务已排队，将在一分钟内开始执行。");

  const confirmAction = () => {
    if (!confirmTarget) return;
    setConfirmError("");
    const target = confirmTarget;
    if (target.kind === "delete") {
      void runAction(`${target.job.jobId}:delete`, async () => {
        await deleteCronJob(target.job.jobId);
        setJobs((current) => current.filter((job) => job.jobId !== target.job.jobId));
        setSelectedId("");
        setConfirmTarget(null);
      }, "任务及其执行历史已删除。", true).catch((cause) => {
        setConfirmError(cause instanceof Error ? cause.message : String(cause));
      });
    } else {
      void runAction(`${target.job.jobId}:cancel`, async () => {
        const cancelled = await cancelCronJobRun(target.job.jobId, target.run.runId);
        setRuns((current) => current.map((run) => run.runId === cancelled.runId ? cancelled : run));
        replaceJob({ ...target.job, latestRun: target.job.latestRun?.runId === cancelled.runId ? cancelled : target.job.latestRun });
        setConfirmTarget(null);
      }, "已提交终止请求。", true).catch((cause) => {
        setConfirmError(cause instanceof Error ? cause.message : String(cause));
      });
    }
  };

  if (selectedJob) {
    return <div className="cronjobs-page"><JobDetail job={selectedJob} runs={runs} runsLoading={runsLoading} runsError={runsError} busyAction={busyAction} onBack={() => setSelectedId("")} onEdit={() => setDrawerJob(selectedJob)} onToggle={() => toggle(selectedJob)} onRun={() => runNow(selectedJob)} onDelete={() => { setConfirmError(""); setConfirmTarget({ kind: "delete", job: selectedJob }); }} onCancel={(run) => { setConfirmError(""); setConfirmTarget({ kind: "cancel", job: selectedJob, run }); }} onRetryRun={() => queueRun(selectedJob, "任务已重新排队，将在一分钟内开始执行。")} onRetryRuns={() => void loadRuns(selectedJob.jobId)} />{notice ? <div className="cronjobs-notice" role="status">{notice}</div> : null}{drawerJob !== undefined ? <Drawer job={drawerJob} runtimes={runtimes} cloudProvider={cloudProvider} busy={busyAction.endsWith(":save")} onClose={() => setDrawerJob(undefined)} onSubmit={submitDrawer} /> : null}{confirmTarget ? <StudioConfirmDialog title={confirmTarget.kind === "delete" ? "删除定时任务？" : "终止本次执行？"} description={confirmTarget.kind === "delete" ? `“${confirmTarget.job.name}”及其全部执行历史将被永久删除。` : "本次 Session 将被取消，后续计划不会暂停。"} error={confirmError} confirmLabel={confirmTarget.kind === "delete" ? "删除任务" : "终止执行"} variant="danger" busy={busyAction.endsWith(confirmTarget.kind)} onCancel={() => { setConfirmError(""); setConfirmTarget(null); }} onConfirm={confirmAction} /> : null}</div>;
  }

  return (
    <div className="cronjobs-page">
      <header className="cronjobs-page-head"><div><h1>定时任务</h1><p>按计划调用 Runtime Agent，每次执行使用独立 Session。</p></div></header>
      {jobs.length > 0 ? (
        <div className="cronjobs-toolbar">
          <button type="button" className="cronjobs-button is-primary" onClick={() => setDrawerJob(null)} disabled={loading || runtimes.length === 0} title={runtimes.length === 0 ? "暂无可用的 Runtime Agent" : "创建定时任务"}><CronPlusIcon />创建任务</button>
        </div>
      ) : null}
      {notice ? <div className="cronjobs-banner" role="status">{notice}</div> : null}
      <section className="cronjobs-content">
        {loading && jobs.length === 0 ? <div className="cronjobs-loading"><TextShimmer as="span" duration={2.4}>正在加载定时任务</TextShimmer><div /><div /><div /></div> : error ? <div className="cronjobs-state is-error" role="alert"><CronClockIcon /><h2>无法加载定时任务</h2><p>{error}</p><button type="button" className="cronjobs-button is-secondary" onClick={() => void load()}><CronRefreshIcon />重试</button></div> : jobs.length === 0 ? <div className="cronjobs-state"><CronClockIcon /><h2>还没有定时任务</h2><p>创建任务后，系统会按计划调用选定的 Runtime Agent。</p><button type="button" className="cronjobs-button is-primary" onClick={() => setDrawerJob(null)} disabled={runtimes.length === 0}><CronPlusIcon />创建第一个任务</button>{runtimes.length === 0 ? <span>暂无可用的 Runtime Agent，请先部署并等待 Runtime 就绪。</span> : null}</div> : <JobList jobs={jobs} busyAction={busyAction} onSelect={(job) => setSelectedId(job.jobId)} onEdit={(job) => setDrawerJob(job)} onToggle={toggle} onRun={runNow} />}
      </section>
      {drawerJob !== undefined ? <Drawer job={drawerJob} runtimes={runtimes} cloudProvider={cloudProvider} busy={busyAction.endsWith(":save")} onClose={() => setDrawerJob(undefined)} onSubmit={submitDrawer} /> : null}
    </div>
  );
}
