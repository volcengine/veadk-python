import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
} from "react";
import { Alert } from "@openai/apps-sdk-ui/components/Alert";
import { Badge } from "@openai/apps-sdk-ui/components/Badge";
import { Button } from "@openai/apps-sdk-ui/components/Button";
import { EmptyMessage } from "@openai/apps-sdk-ui/components/EmptyMessage";
import {
  ArrowLeft,
  ArrowRotateCw,
  Clock,
  Delete,
  Edit,
  Pause,
  Play,
  Plus,
  Stop,
  X,
} from "@openai/apps-sdk-ui/components/Icon";
import { Input } from "@openai/apps-sdk-ui/components/Input";
import { SegmentedControl } from "@openai/apps-sdk-ui/components/SegmentedControl";
import {
  Select,
  type Option,
} from "@openai/apps-sdk-ui/components/Select";
import { Switch } from "@openai/apps-sdk-ui/components/Switch";
import { Textarea } from "@openai/apps-sdk-ui/components/Textarea";
import { Tooltip } from "@openai/apps-sdk-ui/components/Tooltip";
import { useTranslation } from "react-i18next";
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
import { i18n } from "../i18n";
import { StudioConfirmDialog } from "../ui/StudioConfirmDialog";
import { DeploymentErrorMessage } from "../ui/DeploymentErrorMessage";
import { LibraryResourceCard } from "../ui/LibraryResourceCard";
import {
  ResourceCreateCard,
  ResourceGrid,
  ResourceLoadingState,
  ResourcePageHeader,
  ResourcePageShell,
  ResourceResults,
  ResourceTabs,
  ResourceToolbar,
} from "../ui/ResourceCollection";
import {
  CRONJOB_STATUS_LABEL_KEYS,
  WEEKDAY_KEYS,
  cronJobIsRunning,
  describeCronJobSchedule,
  formatCronJobDate,
  formatCronJobDuration,
} from "./model";
import { CronJobFinalAnswer } from "./CronJobFinalAnswer";
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

function cronText(key: string, options?: Record<string, unknown>): string {
  return i18n.t(key, { ns: "cronjobs", ...options });
}

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
  const color = !run
    ? "secondary"
    : run.status === "success"
      ? "success"
      : run.status === "failed"
        ? "danger"
        : ["queued", "pending", "running", "retrying"].includes(run.status)
          ? "info"
          : "secondary";
  return (
    <Badge
      className="cronjobs-status"
      color={color}
      variant="soft"
      size="sm"
      pill
    >
      {run
        ? cronText(CRONJOB_STATUS_LABEL_KEYS[run.status])
        : cronText("status.notRun")}
    </Badge>
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
  const runtimeOptions = useMemo<Option[]>(
    () => runtimes.map((runtime) => ({
      value: runtime.runtimeId,
      label: runtime.name,
      description: formatCloudRegion(runtime.region, cloudProvider),
    })),
    [cloudProvider, runtimes],
  );
  const weekdayOptions = useMemo<Option[]>(
    () => WEEKDAY_KEYS.map((key, index) => ({
      value: String(index),
      label: cronText(key),
    })),
    [],
  );
  const timezoneOptions = useMemo<Option[]>(
    () => zones.map((zone) => ({ value: zone, label: zone })),
    [zones],
  );

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
    if (!name) return setError(cronText("validation.nameRequired"));
    if (!runtime) return setError(cronText("validation.runtimeRequired"));
    if (!prompt) return setError(cronText("validation.promptRequired"));
    if (draft.scheduleType === "once" && !draft.onceAt) {
      return setError(cronText("validation.timeRequired"));
    }
    if ((draft.scheduleType === "daily" || draft.scheduleType === "weekly") && !draft.time) {
      return setError(cronText("validation.timeRequired"));
    }
    const cronFields = draft.cron.trim().split(/\s+/);
    if (draft.scheduleType === "cron" && cronFields.length !== 5) {
      return setError(cronText("validation.cronFields"));
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
        throw new Error(cronText("validation.runtimeAppMissing"));
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
            <h2 id="cronjobs-drawer-title">
              {cronText(job ? "drawer.editTitle" : "drawer.createTitle")}
            </h2>
            <p>{cronText("drawer.description")}</p>
          </div>
          <Button
            type="button"
            color="secondary"
            variant="ghost"
            size="lg"
            uniform
            pill={false}
            onClick={onClose}
            disabled={isBusy}
            aria-label={cronText("actions.closeDrawer")}
          >
            <X />
          </Button>
        </header>
        <form className="cronjobs-form" onSubmit={(event) => void submit(event)}>
          <div className="cronjobs-form-scroll">
            <label className="cronjobs-field">
              <span>{cronText("fields.name")}</span>
              <Input
                ref={nameRef}
                size="lg"
                value={draft.name}
                maxLength={80}
                invalid={Boolean(error) && !draft.name.trim()}
                onChange={(event) => setDraft({ ...draft, name: event.target.value })}
                placeholder={cronText("fields.namePlaceholder")}
              />
            </label>
            <label className="cronjobs-field">
              <span>{cronText("fields.runtimeAgent")}</span>
              <Select
                value={draft.runtimeId}
                options={runtimeOptions}
                size="lg"
                disabled={runtimes.length === 0}
                placeholder={cronText(
                  runtimes.length ? "fields.runtimePlaceholder" : "fields.noRuntime",
                )}
                onChange={(option) => setDraft({ ...draft, runtimeId: option.value })}
              />
              <small>{cronText("fields.runtimeHelp")}</small>
            </label>
            <label className="cronjobs-field">
              <span>{cronText("fields.prompt")}</span>
              <Textarea
                value={draft.prompt}
                rows={5}
                maxRows={10}
                autoResize
                maxLength={20_000}
                invalid={Boolean(error) && !draft.prompt.trim()}
                onChange={(event) => setDraft({ ...draft, prompt: event.target.value })}
                placeholder={cronText("fields.promptPlaceholder")}
              />
              <small className="cronjobs-character-count">
                {draft.prompt.length.toLocaleString()} / 20,000
              </small>
            </label>
            <fieldset className="cronjobs-fieldset">
              <legend>{cronText("fields.schedule")}</legend>
              <SegmentedControl
                className="cronjobs-schedule-types"
                value={draft.scheduleType}
                size="lg"
                block
                aria-label={cronText("fields.scheduleType")}
                onChange={(scheduleType) => setDraft({ ...draft, scheduleType })}
              >
                <SegmentedControl.Option value="once">{cronText("scheduleTypes.once")}</SegmentedControl.Option>
                <SegmentedControl.Option value="daily">{cronText("scheduleTypes.daily")}</SegmentedControl.Option>
                <SegmentedControl.Option value="weekly">{cronText("scheduleTypes.weekly")}</SegmentedControl.Option>
                <SegmentedControl.Option value="cron">Cron</SegmentedControl.Option>
              </SegmentedControl>
              {draft.scheduleType === "once" ? (
                <label className="cronjobs-field"><span>{cronText("fields.runAt")}</span><Input size="lg" type="datetime-local" value={draft.onceAt} onChange={(event) => setDraft({ ...draft, onceAt: event.target.value })} /></label>
              ) : null}
              {draft.scheduleType === "daily" ? (
                <label className="cronjobs-field"><span>{cronText("fields.dailyTime")}</span><Input size="lg" type="time" value={draft.time} onChange={(event) => setDraft({ ...draft, time: event.target.value })} /></label>
              ) : null}
              {draft.scheduleType === "weekly" ? (
                <div className="cronjobs-inline-fields">
                  <label className="cronjobs-field"><span>{cronText("fields.weekday")}</span><Select value={String(draft.weekday)} options={weekdayOptions} size="lg" onChange={(option) => setDraft({ ...draft, weekday: Number(option.value) })} /></label>
                  <label className="cronjobs-field"><span>{cronText("fields.runAt")}</span><Input size="lg" type="time" value={draft.time} onChange={(event) => setDraft({ ...draft, time: event.target.value })} /></label>
                </div>
              ) : null}
              {draft.scheduleType === "cron" ? (
                <label className="cronjobs-field"><span>{cronText("fields.cronExpression")}</span><Input size="lg" value={draft.cron} onChange={(event) => setDraft({ ...draft, cron: event.target.value })} placeholder="0 9 * * *" /><small>{cronText("fields.cronHelp")}</small></label>
              ) : null}
              <label className="cronjobs-field"><span>{cronText("fields.timezone")}</span><Select value={draft.timezone} options={timezoneOptions} size="lg" onChange={(option) => setDraft({ ...draft, timezone: option.value })} /></label>
            </fieldset>
            <div className="cronjobs-switch-row">
              <span><strong>{cronText("fields.enableAfterCreate")}</strong><small>{cronText("fields.enableHelp")}</small></span>
              <Switch checked={draft.enabled} onCheckedChange={(enabled) => setDraft({ ...draft, enabled })} aria-label={cronText("fields.enableAfterCreate")} />
            </div>
            {error ? <div ref={errorRef} className="cronjobs-inline-error" tabIndex={-1}><Alert color="danger" variant="soft" description={error} /></div> : null}
          </div>
          <footer className="cronjobs-drawer-actions">
            <Button type="button" color="secondary" variant="ghost" size="lg" pill={false} onClick={onClose} disabled={isBusy}>{cronText("actions.cancel")}</Button>
            <Button type="submit" color="primary" size="lg" pill={false} loading={isBusy} disabled={runtimes.length === 0} aria-busy={isBusy || undefined}>{cronText(resolvingRuntime ? "actions.connectingRuntime" : busy ? "actions.saving" : job ? "actions.saveChanges" : "actions.createTask")}</Button>
          </footer>
        </form>
      </aside>
    </div>
  );
}

function JobList({
  jobs,
  canCreate,
  onCreate,
  onSelect,
}: {
  jobs: CronJob[];
  canCreate: boolean;
  onCreate: () => void;
  onSelect: (job: CronJob) => void;
}) {
  return (
    <ResourceGrid>
      <ResourceCreateCard
        icon={<Plus />}
        onClick={onCreate}
        disabled={!canCreate}
        title={cronText(canCreate ? "actions.createScheduledTask" : "fields.noRuntime")}
      >
        {cronText("actions.createScheduledTask")}
      </ResourceCreateCard>
      {jobs.map((job) => {
        const schedule = describeCronJobSchedule(job.schedule);
        return (
          <LibraryResourceCard
            key={job.jobId}
            className="cronjobs-card"
            title={job.name}
            status={<Badge color={job.enabled ? "success" : "secondary"} variant="soft" size="sm" pill>{cronText(job.enabled ? "status.enabled" : "status.paused")}</Badge>}
            description={job.prompt}
            metadata={[
              { label: cronText("fields.schedule"), value: schedule, title: schedule },
            ]}
            detailAction={{ label: cronText("actions.viewDetails"), onClick: () => onSelect(job) }}
          />
        );
      })}
    </ResourceGrid>
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
          <Button type="button" color="secondary" variant="ghost" size="lg" uniform pill={false} onClick={onBack} aria-label={cronText("actions.backToList")}><ArrowLeft /></Button>
          <div><h1>{job.name}</h1><p>{job.runtimeName || job.agentName} · {describeCronJobSchedule(job.schedule)}</p></div>
        </div>
        <div className="cronjobs-detail-actions">
          <Button type="button" color="secondary" variant="outline" size="lg" pill={false} onClick={onEdit} disabled={busy}><Edit />{cronText("actions.edit")}</Button>
          <Button type="button" color="secondary" variant="outline" size="lg" pill={false} onClick={onToggle} disabled={busy}>{job.enabled ? <Pause /> : <Play />}{cronText(job.enabled ? "actions.pause" : "actions.enable")}</Button>
          {latestRunning ? <Button type="button" color="danger" variant="soft" size="lg" pill={false} onClick={() => onCancel(latestRunning)} disabled={busy || Boolean(latestRunning.cancellationRequestedAt)}><Stop />{cronText(latestRunning.cancellationRequestedAt ? (latestRunning.status === "queued" ? "actions.cancelling" : "actions.stopping") : (latestRunning.status === "queued" ? "actions.cancelQueue" : "actions.stopRun"))}</Button> : <Button type="button" color="primary" size="lg" pill={false} onClick={onRun} disabled={busy || !job.enabled}><Play />{cronText("actions.runNow")}</Button>}
          <Tooltip compact content={cronText(latestRunning ? (latestRunning.status === "queued" ? "actions.cancelQueueFirst" : "actions.stopRunFirst") : "actions.deleteTask")}>
            <Button type="button" color="danger" variant="ghost" size="lg" pill={false} onClick={onDelete} disabled={busy || Boolean(latestRunning)} aria-label={cronText("actions.deleteTask")}><Delete />{cronText("actions.delete")}</Button>
          </Tooltip>
        </div>
      </header>
      <div className="cronjobs-detail-scroll">
        <section className="cronjobs-summary-grid" aria-label={cronText("detail.configuration")}>
          <dl><div><dt>{cronText("detail.status")}</dt><dd>{cronText(job.enabled ? "status.enabled" : "status.paused")}</dd></div><div><dt>{cronText("detail.nextRun")}</dt><dd>{job.enabled ? formatCronJobDate(job.nextRunAt) : "-"}</dd></div><div><dt>{cronText("detail.runtime")}</dt><dd title={job.runtimeName}>{job.runtimeName}</dd></div><div><dt>{cronText("detail.region")}</dt><dd>{job.region}</dd></div></dl>
          <div className="cronjobs-prompt"><span>{cronText("fields.prompt")}</span><p>{job.prompt}</p></div>
        </section>
        <section className="cronjobs-history">
          <header><div><h2>{cronText("history.title")}</h2><p>{cronText("history.description")}</p></div><Tooltip compact content={cronText("actions.refresh")}><Button type="button" color="secondary" variant="ghost" size="lg" uniform pill={false} onClick={onRetryRuns} disabled={runsLoading} aria-label={cronText("actions.refreshHistory")}><ArrowRotateCw /></Button></Tooltip></header>
          {runsLoading && runs.length === 0 ? <ResourceLoadingState /> : runsError ? <Alert className="cronjobs-history-alert" color="danger" variant="soft" title={cronText("history.loadFailed")} description={runsError} actions={<Button type="button" color="danger" variant="soft" size="sm" pill={false} onClick={onRetryRuns}>{cronText("actions.retry")}</Button>} /> : runs.length === 0 ? <EmptyMessage className="cronjobs-history-state" fill="none"><EmptyMessage.Icon><Clock /></EmptyMessage.Icon><EmptyMessage.Title>{cronText("history.emptyTitle")}</EmptyMessage.Title><EmptyMessage.Description>{cronText("history.emptyDescription")}</EmptyMessage.Description></EmptyMessage> : (
            <div className="cronjobs-runs">
              {runs.map((run) => <article className="cronjobs-run" key={run.runId}>
                <div className="cronjobs-run-main"><StatusBadge run={run} /><div><strong>{formatCronJobDate(run.startedAt || run.scheduledAt)}</strong><span>{cronText("history.duration", { duration: formatCronJobDuration(run) })}{run.runtimeVersion ? ` · Runtime v${run.runtimeVersion}` : ""}</span></div></div>
                {run.sessionId ? <div className="cronjobs-run-meta"><span>{cronText("history.session")}</span><strong title={run.sessionId}>{run.sessionId}</strong></div> : null}
                {run.output ? <div className="cronjobs-run-output"><span>{cronText("history.finalAnswer")}</span><CronJobFinalAnswer output={run.output} /></div> : null}
                {run.error ? <div className="cronjobs-run-output is-error"><span>{cronText("history.errorDetails")}</span><DeploymentErrorMessage message={run.error} className="cronjobs-run-error-detail" defaultExpanded={false} onRetry={run.status === "failed" ? onRetryRun : undefined} retryLabel={cronText("actions.rerun")} /></div> : null}
                {(run.status === "queued" || run.status === "running" || run.status === "retrying" || run.status === "pending") ? <Button type="button" className="cronjobs-run-cancel" color="danger" variant="soft" size="sm" pill={false} onClick={() => onCancel(run)} disabled={busy || Boolean(run.cancellationRequestedAt)} loading={Boolean(run.cancellationRequestedAt)}>{cronText(run.cancellationRequestedAt ? "actions.stopping" : run.status === "queued" ? "actions.cancelQueue" : "actions.stop")}</Button> : null}
              </article>)}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

export function CronJobs({ cloudProvider }: CronJobsProps) {
  useTranslation("cronjobs");
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
  const [listFilter, setListFilter] = useState<"all" | "enabled" | "paused">("all");
  const [notice, setNotice] = useState("");
  const [confirmTarget, setConfirmTarget] = useState<ConfirmTarget | null>(null);
  const [confirmError, setConfirmError] = useState("");
  const selectedJob = jobs.find((job) => job.jobId === selectedId);
  const visibleJobs = listFilter === "all"
    ? jobs
    : jobs.filter((job) => listFilter === "enabled" ? job.enabled : !job.enabled);

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
      console.warn("Unable to load scheduled tasks", cause);
      setError(cronText("page.loadFailedDescription"));
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
      if (!signal?.aborted) {
        console.warn("Unable to load scheduled-task history", cause);
        setRunsError(cronText("history.loadFailedDescription"));
      }
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
    if (!hasActiveJob && notice === cronText("notices.queued")) setNotice("");
  }, [hasActiveJob, notice]);

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
        if (!nextJobs.some(cronJobIsRunning)) setNotice("");
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
    }, cronText(job ? "notices.updated" : "notices.created"), true);
  };

  const toggle = (job: CronJob) => void runAction(`${job.jobId}:toggle`, async () => replaceJob(await setCronJobEnabled(job.jobId, !job.enabled)), cronText(job.enabled ? "notices.paused" : "notices.enabled"));
  const queueRun = (job: CronJob, success: string) => runAction(`${job.jobId}:run`, async () => {
    const run = await runCronJobNow(job.jobId);
    replaceJob({ ...job, latestRun: run });
    if (selectedId === job.jobId) setRuns((current) => [run, ...current.filter((item) => item.runId !== run.runId)]);
  }, success);
  const runNow = (job: CronJob) => void queueRun(job, cronText("notices.queued"));

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
      }, cronText("notices.deleted"), true).catch((cause) => {
        setConfirmError(cause instanceof Error ? cause.message : String(cause));
      });
    } else {
      void runAction(`${target.job.jobId}:cancel`, async () => {
        const cancelled = await cancelCronJobRun(target.job.jobId, target.run.runId);
        setRuns((current) => current.map((run) => run.runId === cancelled.runId ? cancelled : run));
        replaceJob({ ...target.job, latestRun: target.job.latestRun?.runId === cancelled.runId ? cancelled : target.job.latestRun });
        setConfirmTarget(null);
      }, cronText("notices.cancelRequested"), true).catch((cause) => {
        setConfirmError(cause instanceof Error ? cause.message : String(cause));
      });
    }
  };

  if (selectedJob) {
    return <ResourcePageShell className="cronjobs-page" aria-label={cronText("detail.pageLabel")}><JobDetail job={selectedJob} runs={runs} runsLoading={runsLoading} runsError={runsError} busyAction={busyAction} onBack={() => setSelectedId("")} onEdit={() => setDrawerJob(selectedJob)} onToggle={() => toggle(selectedJob)} onRun={() => runNow(selectedJob)} onDelete={() => { setConfirmError(""); setConfirmTarget({ kind: "delete", job: selectedJob }); }} onCancel={(run) => { setConfirmError(""); setConfirmTarget({ kind: "cancel", job: selectedJob, run }); }} onRetryRun={() => queueRun(selectedJob, cronText("notices.requeued"))} onRetryRuns={() => void loadRuns(selectedJob.jobId)} />{notice ? <div className="cronjobs-notice" role="status"><Alert color="info" variant="soft" description={notice} /></div> : null}{drawerJob !== undefined ? <Drawer job={drawerJob} runtimes={runtimes} cloudProvider={cloudProvider} busy={busyAction.endsWith(":save")} onClose={() => setDrawerJob(undefined)} onSubmit={submitDrawer} /> : null}{confirmTarget ? <StudioConfirmDialog title={cronText(confirmTarget.kind === "delete" ? "confirm.deleteTitle" : "confirm.cancelTitle")} description={confirmTarget.kind === "delete" ? cronText("confirm.deleteDescription", { name: confirmTarget.job.name }) : cronText("confirm.cancelDescription")} error={confirmError} confirmLabel={cronText(confirmTarget.kind === "delete" ? "actions.deleteTask" : "actions.stop")} variant="danger" busy={busyAction.endsWith(confirmTarget.kind)} onCancel={() => { setConfirmError(""); setConfirmTarget(null); }} onConfirm={confirmAction} /> : null}</ResourcePageShell>;
  }

  return (
    <ResourcePageShell className="cronjobs-page" aria-label={cronText("page.title")}>
      <ResourcePageHeader
        className="cronjobs-page-head"
        title={cronText("page.title")}
      />
      <ResourceToolbar>
        <ResourceTabs
          idPrefix="cronjobs-filter"
          ariaLabel={cronText("page.filterLabel")}
          value={listFilter}
          items={[
            { id: "all", label: cronText("filters.all") },
            { id: "enabled", label: cronText("status.enabled") },
            { id: "paused", label: cronText("status.paused") },
          ]}
          onChange={setListFilter}
        />
      </ResourceToolbar>
      {notice ? <div className="cronjobs-banner" role="status"><Alert color="info" variant="soft" description={notice} /></div> : null}
      <ResourceResults aria-label={cronText("page.listLabel")}>
        {loading && jobs.length === 0 ? <ResourceLoadingState /> : error ? <EmptyMessage className="cronjobs-state" fill="none"><EmptyMessage.Icon color="danger"><Clock /></EmptyMessage.Icon><EmptyMessage.Title color="danger">{cronText("page.loadFailed")}</EmptyMessage.Title><EmptyMessage.Description>{error}</EmptyMessage.Description><EmptyMessage.ActionRow><Button type="button" color="secondary" variant="outline" size="lg" pill={false} onClick={() => void load()}><ArrowRotateCw />{cronText("actions.retry")}</Button></EmptyMessage.ActionRow></EmptyMessage> : <JobList jobs={visibleJobs} canCreate={!loading && runtimes.length > 0} onCreate={() => setDrawerJob(null)} onSelect={(job) => setSelectedId(job.jobId)} />}
      </ResourceResults>
      {drawerJob !== undefined ? <Drawer job={drawerJob} runtimes={runtimes} cloudProvider={cloudProvider} busy={busyAction.endsWith(":save")} onClose={() => setDrawerJob(undefined)} onSubmit={submitDrawer} /> : null}
    </ResourcePageShell>
  );
}
