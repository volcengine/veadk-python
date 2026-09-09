import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useTranslation } from "react-i18next";
import type {
  MigrationCapabilities,
  MigrationEvaluationCase,
  MigrationEvaluationDataset,
  MigrationEvaluationDimensionId,
  MigrationEvaluationStatus,
  MigrationTaskState,
} from "../adk/migrations";
import { TextShimmer } from "../ui/text-shimmer/TextShimmer";
import { initialEvaluationEnvironmentValues } from "./evaluationEnvironment";
import { CloseIcon } from "./MigrationIcons";
import "./MigrationEvaluation.css";

const STANDARD_DIMENSIONS: MigrationEvaluationDimensionId[] = [
  "semantic_fidelity",
  "output_contract",
  "workflow_tool_fidelity",
];
const MAX_CASES = 100;
const MAX_QUESTION_BYTES = 32 * 1024;
const MAX_REFERENCE_BYTES = 16 * 1024;
const MAX_CRITERIA = 20;
const MAX_CRITERION_BYTES = 2 * 1024;
const MAX_DATASET_BYTES = 10 * 1024 * 1024;

export interface EvaluationDraftCriterion {
  id: string;
  text: string;
}

export interface EvaluationDraftCase {
  id: string;
  userInput: string;
  expectedOutcome: string;
  criteria: EvaluationDraftCriterion[];
}

export interface MigrationEvaluationDraft {
  enabled: boolean;
  preset: "standard" | "custom";
  dimensions: MigrationEvaluationDimensionId[];
  cases: EvaluationDraftCase[];
}

export interface EvaluationDraftValidation {
  valid: boolean;
  errors: Record<string, string>;
}

type EvaluationTranslate = (
  key: string,
  options?: Record<string, unknown>,
) => string;

function stableId(prefix: string): string {
  return `${prefix}-${crypto.randomUUID()}`;
}

function MoveUpIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="m7 11 5-5 5 5" />
      <path d="M12 6v12" />
    </svg>
  );
}

function MoveDownIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="m7 13 5 5 5-5" />
      <path d="M12 18V6" />
    </svg>
  );
}

function RemoveIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      aria-hidden="true"
    >
      <path d="m7 7 10 10M17 7 7 17" />
    </svg>
  );
}

function emptyCase(): EvaluationDraftCase {
  return {
    id: stableId("case"),
    userInput: "",
    expectedOutcome: "",
    criteria: [],
  };
}

export function createMigrationEvaluationDraft(): MigrationEvaluationDraft {
  return {
    enabled: false,
    preset: "standard",
    dimensions: [...STANDARD_DIMENSIONS],
    cases: [emptyCase()],
  };
}

function utf8Bytes(value: string): number {
  return new TextEncoder().encode(value).byteLength;
}

export function evaluationCasesFromDraft(
  draft: MigrationEvaluationDraft,
): MigrationEvaluationCase[] {
  return draft.cases.map((item) => ({
    caseId: item.id,
    userInput: item.userInput.trim(),
    expectedOutcome: item.expectedOutcome.trim() || null,
    criteria: item.criteria.map((criterion) => criterion.text.trim()),
    priorMessages: [],
  }));
}

export function evaluationDraftFromDataset(
  dataset: MigrationEvaluationDataset,
  status: MigrationEvaluationStatus,
): MigrationEvaluationDraft {
  return {
    enabled: true,
    preset: status.preset ?? "standard",
    dimensions: status.dimensions?.length
      ? [...status.dimensions]
      : [...STANDARD_DIMENSIONS],
    cases: dataset.cases.map((item) => ({
      id: item.caseId,
      userInput: item.userInput,
      expectedOutcome: item.expectedOutcome ?? "",
      criteria: item.criteria.map((text) => ({
        id: stableId("criterion"),
        text,
      })),
    })),
  };
}

export function validateMigrationEvaluationDraft(
  draft: MigrationEvaluationDraft,
  unavailableMessage: string,
  translate: EvaluationTranslate,
): EvaluationDraftValidation {
  if (!draft.enabled) return { valid: true, errors: {} };
  const errors: Record<string, string> = {};
  if (unavailableMessage) errors.root = unavailableMessage;
  if (draft.cases.length < 1 || draft.cases.length > MAX_CASES) {
    errors.cases = translate("evaluation.validation.caseCount", {
      count: MAX_CASES,
    });
  }
  if (draft.dimensions.length < 1) {
    errors.dimensions = translate("evaluation.validation.dimensionRequired");
  }
  for (const item of draft.cases) {
    if (!item.userInput.trim()) {
      errors[`${item.id}:userInput`] = translate(
        "evaluation.validation.userInputRequired",
      );
    }
    if (utf8Bytes(item.userInput.trim()) > MAX_QUESTION_BYTES) {
      errors[`${item.id}:userInput`] = translate(
        "evaluation.validation.userInputBytes",
      );
    }
    if (utf8Bytes(item.expectedOutcome.trim()) > MAX_REFERENCE_BYTES) {
      errors[`${item.id}:expectedOutcome`] = translate(
        "evaluation.validation.expectedOutcomeBytes",
      );
    }
    if (item.criteria.length > MAX_CRITERIA) {
      errors[`${item.id}:criteria`] = translate(
        "evaluation.validation.criteriaCount",
        { count: MAX_CRITERIA },
      );
    }
    for (const criterion of item.criteria) {
      if (!criterion.text.trim()) {
        errors[`${item.id}:criterion:${criterion.id}`] = translate(
          "evaluation.validation.criterionRequired",
        );
      } else if (utf8Bytes(criterion.text.trim()) > MAX_CRITERION_BYTES) {
        errors[`${item.id}:criterion:${criterion.id}`] = translate(
          "evaluation.validation.criterionBytes",
        );
      }
    }
  }
  const normalizedBytes = utf8Bytes(
    evaluationCasesFromDraft(draft)
      .map((item) => JSON.stringify(item))
      .join("\n"),
  );
  if (normalizedBytes > MAX_DATASET_BYTES) {
    errors.cases = translate("evaluation.validation.datasetBytes");
  }
  return { valid: Object.keys(errors).length === 0, errors };
}

interface EvaluationDrawerProps {
  titleId: string;
  title: string;
  description: string;
  closeLabel: string;
  onClose: () => void;
  children: ReactNode;
  footer: ReactNode;
  variant?: "settings" | "report";
}

function MigrationEvaluationDrawer({
  titleId,
  title,
  description,
  closeLabel,
  onClose,
  children,
  footer,
  variant = "settings",
}: EvaluationDrawerProps) {
  const drawerRef = useRef<HTMLElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    previousFocusRef.current =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const focusFrame = window.requestAnimationFrame(() => {
      closeButtonRef.current?.focus();
    });
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onCloseRef.current();
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = Array.from(
        drawerRef.current?.querySelectorAll<HTMLElement>(
          'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ) ?? [],
      ).filter((element) => !element.hidden);
      if (!focusable.length) {
        event.preventDefault();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement;
      if (
        event.shiftKey &&
        (active === first || !drawerRef.current?.contains(active))
      ) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.cancelAnimationFrame(focusFrame);
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleKeyDown);
      const previousFocus = previousFocusRef.current;
      if (previousFocus?.isConnected) previousFocus.focus();
    };
  }, []);

  return (
    <div
      className="migration-evaluation-drawer"
      onMouseDown={(event) => {
        if (event.currentTarget === event.target) onClose();
      }}
    >
      <aside
        ref={drawerRef}
        className={`is-${variant}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
      >
        <header className="migration-evaluation-drawer__header">
          <div>
            <strong id={titleId}>{title}</strong>
            <span>{description}</span>
          </div>
          <button
            ref={closeButtonRef}
            type="button"
            className="migration-evaluation-drawer__close"
            onClick={onClose}
            aria-label={closeLabel}
          >
            <CloseIcon />
          </button>
        </header>
        <div className="migration-evaluation-drawer__body">{children}</div>
        <footer className="migration-evaluation-drawer__footer">{footer}</footer>
      </aside>
    </div>
  );
}

interface SetupProps {
  value: MigrationEvaluationDraft;
  onChange: (value: MigrationEvaluationDraft) => void;
  capability: MigrationCapabilities["evaluation"];
  disabled: boolean;
  configLocked?: boolean;
  locked?: boolean;
  errors: Record<string, string>;
}

export function MigrationEvaluationSetup({
  value,
  onChange,
  capability,
  disabled,
  configLocked = false,
  locked = false,
  errors,
}: SetupProps) {
  const { t } = useTranslation("migrations");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [bulkText, setBulkText] = useState("");
  const bulkQuestions = useMemo(
    () =>
      bulkText
        .split(/\r?\n/)
        .map((item) => item.trim())
        .filter(Boolean),
    [bulkText],
  );
  const incompleteCases = value.cases.filter(
    (item) => !item.userInput.trim(),
  ).length;
  const closeDrawer = () => setDrawerOpen(false);

  useEffect(() => {
    if (value.enabled && Object.keys(errors).length > 0) {
      setDrawerOpen(true);
    }
  }, [errors, value.enabled]);

  const updateCase = (caseId: string, update: Partial<EvaluationDraftCase>) => {
    onChange({
      ...value,
      cases: value.cases.map((item) =>
        item.id === caseId ? { ...item, ...update } : item,
      ),
    });
  };
  const moveCase = (index: number, offset: -1 | 1) => {
    const target = index + offset;
    if (target < 0 || target >= value.cases.length) return;
    const cases = [...value.cases];
    [cases[index], cases[target]] = [cases[target], cases[index]];
    onChange({ ...value, cases });
  };
  const toggleDimension = (dimension: MigrationEvaluationDimensionId) => {
    const selected = value.dimensions.includes(dimension);
    if (selected && value.dimensions.length === 1) return;
    const ordered = (capability?.dimensions ?? [])
      .map((item) => item.id)
      .filter((item) =>
        item === dimension ? !selected : value.dimensions.includes(item),
      );
    onChange({ ...value, dimensions: ordered });
  };
  const unavailable = !capability?.available;
  const configurationReadOnly = locked || configLocked;
  const presetLabel = t(`evaluation.advanced.${value.preset}`);
  const dimensionSummary = t("evaluation.setup.dimensionSummary", {
    count: value.dimensions.length,
  });
  const summary = incompleteCases
    ? t("evaluation.setup.incompleteSummary", {
        count: incompleteCases,
        preset: presetLabel,
        dimensions: dimensionSummary,
      })
    : t("evaluation.setup.configuredSummary", {
        count: value.cases.length,
        preset: presetLabel,
        dimensions: dimensionSummary,
      });
  return (
    <section
      className="migration-evaluation-setup"
      aria-labelledby="migration-evaluation-title"
    >
      <div className="migration-evaluation-setup__switch-row">
        <div>
          <strong id="migration-evaluation-title">
            {t("evaluation.setup.title")}
          </strong>
          <span>{t("evaluation.setup.description")}</span>
        </div>
        <label className="migration-evaluation-switch">
          <input
            type="checkbox"
            role="switch"
            checked={value.enabled}
            onChange={(event) => {
              const enabled = event.currentTarget.checked;
              onChange({ ...value, enabled });
              setDrawerOpen(enabled);
            }}
            disabled={disabled || configLocked || unavailable}
            aria-describedby={
              unavailable ? "migration-evaluation-unavailable" : undefined
            }
          />
          <span aria-hidden="true" />
          <b>
            {value.enabled
              ? t("evaluation.setup.on")
              : t("evaluation.setup.off")}
          </b>
        </label>
      </div>
      {unavailable ? (
        <p
          id="migration-evaluation-unavailable"
          className="migration-evaluation-hint is-error"
          role="alert"
        >
          {capability?.reason || t("evaluation.setup.unavailable")}
        </p>
      ) : null}
      {value.enabled ? (
        <div className="migration-evaluation-setup__summary">
          <span>{summary}</span>
          <button
            type="button"
            onClick={() => setDrawerOpen(true)}
            disabled={disabled}
          >
            {locked
              ? t("evaluation.setup.viewSettings")
              : t("evaluation.setup.editSettings")}
          </button>
        </div>
      ) : null}
      {value.enabled && drawerOpen ? (
        <MigrationEvaluationDrawer
          titleId="migration-evaluation-drawer-title"
          title={
            locked
              ? t("evaluation.setup.lockedTitle")
              : t("evaluation.setup.casesTitle")
          }
          description={
            locked
              ? t("evaluation.setup.lockedDescription")
              : t("evaluation.setup.casesDescription")
          }
          closeLabel={t("evaluation.setup.closeAria")}
          onClose={closeDrawer}
          footer={
            <>
              <span>{summary}</span>
              <button
                type="button"
                className="is-primary"
                onClick={closeDrawer}
              >
                {locked
                  ? t("evaluation.setup.close")
                  : t("evaluation.setup.done")}
              </button>
            </>
          }
        >
              <fieldset className="migration-evaluation-advanced">
                <legend>{t("evaluation.advanced.title")}</legend>
                <div
                  className="migration-evaluation-preset"
                  role="radiogroup"
                  aria-label={t("evaluation.advanced.title")}
                >
                  <label
                    className={value.preset === "standard" ? "is-selected" : ""}
                  >
                    <input
                      type="radio"
                      name="migration-evaluation-preset"
                      value="standard"
                      checked={value.preset === "standard"}
                      onChange={() =>
                        onChange({
                          ...value,
                          preset: "standard",
                          dimensions: [...STANDARD_DIMENSIONS],
                        })
                      }
                      disabled={disabled || configurationReadOnly}
                    />
                    <span>
                      <strong>{t("evaluation.advanced.standard")}</strong>
                      <small>
                        {t("evaluation.advanced.standardDescription")}
                      </small>
                    </span>
                  </label>
                  <label
                    className={value.preset === "custom" ? "is-selected" : ""}
                  >
                    <input
                      type="radio"
                      name="migration-evaluation-preset"
                      value="custom"
                      checked={value.preset === "custom"}
                      onChange={() =>
                        onChange({
                          ...value,
                          preset: "custom",
                          dimensions: [],
                        })
                      }
                      disabled={disabled || configurationReadOnly}
                    />
                    <span>
                      <strong>{t("evaluation.advanced.custom")}</strong>
                      <small>
                        {t("evaluation.advanced.customDescription")}
                      </small>
                    </span>
                  </label>
                </div>
                {value.preset === "custom" ? (
                  <div
                    className="migration-evaluation-dimensions"
                    aria-describedby={
                      errors.dimensions
                        ? "migration-evaluation-dimensions-error"
                        : undefined
                    }
                  >
                    {(capability?.dimensions ?? []).map((dimension) => (
                      <label
                        key={dimension.id}
                        className={
                          value.dimensions.includes(dimension.id)
                            ? "is-selected"
                            : ""
                        }
                      >
                        <input
                          type="checkbox"
                          checked={value.dimensions.includes(dimension.id)}
                          onChange={() => toggleDimension(dimension.id)}
                          disabled={
                            disabled ||
                            configurationReadOnly ||
                            (value.dimensions.length === 1 &&
                              value.dimensions.includes(dimension.id))
                          }
                        />
                        <span>
                          <strong>
                            {t(`evaluation.dimension.${dimension.id}`)}
                          </strong>
                          <small>
                            {t(
                              `evaluation.dimensionDescription.${dimension.id}`,
                            )}
                          </small>
                        </span>
                      </label>
                    ))}
                  </div>
                ) : null}
                {configurationReadOnly ? (
                  <small className="migration-evaluation-advanced__locked">
                    {t("evaluation.advanced.lockedDescription")}
                  </small>
                ) : null}
                {errors.dimensions ? (
                  <small
                    id="migration-evaluation-dimensions-error"
                    role="alert"
                  >
                    {errors.dimensions}
                  </small>
                ) : null}
              </fieldset>
              {!locked ? (
                <div className="migration-evaluation-drawer__toolbar">
                  <button
                    type="button"
                    onClick={() => setBulkOpen((current) => !current)}
                    disabled={disabled}
                    aria-expanded={bulkOpen}
                  >
                    {t("evaluation.bulk.open")}
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      onChange({ ...value, cases: [...value.cases, emptyCase()] })
                    }
                    disabled={disabled || value.cases.length >= MAX_CASES}
                  >
                    {t("evaluation.case.add")}
                  </button>
                </div>
              ) : null}
              {errors.root || errors.cases ? (
                <div className="migration-evaluation-error-summary" role="alert">
                  {errors.root || errors.cases}
                </div>
              ) : null}
              {bulkOpen && !locked ? (
                <div className="migration-evaluation-bulk">
                  <label htmlFor="migration-evaluation-bulk-input">
                    {t("evaluation.bulk.label")}
                  </label>
                  <textarea
                    id="migration-evaluation-bulk-input"
                    value={bulkText}
                    onChange={(event) => setBulkText(event.currentTarget.value)}
                    placeholder={t("evaluation.bulk.placeholder")}
                    disabled={disabled}
                  />
                  <div
                    className="migration-evaluation-bulk__preview"
                    aria-live="polite"
                  >
                    <strong>
                      {t("evaluation.bulk.preview", {
                        count: bulkQuestions.length,
                      })}
                    </strong>
                    {bulkQuestions.length ? (
                      <ol>
                        {bulkQuestions.slice(0, 5).map((question, index) => (
                          <li key={`${index}:${question}`}>{question}</li>
                        ))}
                      </ol>
                    ) : null}
                  </div>
                  <div className="migration-evaluation-bulk__actions">
                    <button
                      type="button"
                      onClick={() => {
                        setBulkOpen(false);
                        setBulkText("");
                      }}
                      disabled={disabled}
                    >
                      {t("actions.cancel")}
                    </button>
                    <button
                      type="button"
                      className="is-primary"
                      disabled={
                        disabled ||
                        !bulkQuestions.length ||
                        value.cases.length + bulkQuestions.length > MAX_CASES
                      }
                      onClick={() => {
                        const cases = bulkQuestions.map((question) => ({
                          ...emptyCase(),
                          userInput: question,
                        }));
                        const existing =
                          value.cases.length === 1 &&
                          !value.cases[0].userInput.trim()
                            ? []
                            : value.cases;
                        onChange({ ...value, cases: [...existing, ...cases] });
                        setBulkOpen(false);
                        setBulkText("");
                      }}
                    >
                      {t("evaluation.bulk.confirm")}
                    </button>
                  </div>
                </div>
              ) : null}
              <div className="migration-evaluation-cases">
                {value.cases.map((item, index) => {
                  const inputError = errors[`${item.id}:userInput`];
                  const expectedError = errors[`${item.id}:expectedOutcome`];
                  return (
                    <article className="migration-evaluation-case" key={item.id}>
                      <header>
                        <strong>
                          {t("evaluation.case.title", { index: index + 1 })}
                        </strong>
                        {!locked ? (
                          <div>
                            <button
                              type="button"
                              onClick={() => moveCase(index, -1)}
                              disabled={disabled || index === 0}
                              aria-label={t("evaluation.case.moveUp", {
                                index: index + 1,
                              })}
                            >
                              <MoveUpIcon />
                            </button>
                            <button
                              type="button"
                              onClick={() => moveCase(index, 1)}
                              disabled={
                                disabled || index === value.cases.length - 1
                              }
                              aria-label={t("evaluation.case.moveDown", {
                                index: index + 1,
                              })}
                            >
                              <MoveDownIcon />
                            </button>
                            <button
                              type="button"
                              onClick={() =>
                                onChange({
                                  ...value,
                                  cases: [
                                    ...value.cases.slice(0, index + 1),
                                    {
                                      ...item,
                                      id: stableId("case"),
                                      criteria: item.criteria.map(
                                        (criterion) => ({
                                          ...criterion,
                                          id: stableId("criterion"),
                                        }),
                                      ),
                                    },
                                    ...value.cases.slice(index + 1),
                                  ],
                                })
                              }
                              disabled={
                                disabled || value.cases.length >= MAX_CASES
                              }
                            >
                              {t("evaluation.case.copy")}
                            </button>
                            <button
                              type="button"
                              onClick={() =>
                                onChange({
                                  ...value,
                                  cases: value.cases.filter(
                                    (candidate) => candidate.id !== item.id,
                                  ),
                                })
                              }
                              disabled={disabled || value.cases.length === 1}
                            >
                              {t("evaluation.case.delete")}
                            </button>
                          </div>
                        ) : null}
                      </header>
                      <label htmlFor={`${item.id}-input`}>
                        <span>
                          {t("evaluation.case.userInput")}
                          <b aria-hidden="true">*</b>
                        </span>
                        <textarea
                          id={`${item.id}-input`}
                          value={item.userInput}
                          onChange={(event) =>
                            updateCase(item.id, {
                              userInput: event.currentTarget.value,
                            })
                          }
                          placeholder={t(
                            "evaluation.case.userInputPlaceholder",
                          )}
                          required
                          aria-required="true"
                          aria-invalid={Boolean(inputError)}
                          aria-describedby={
                            inputError ? `${item.id}-input-error` : undefined
                          }
                          disabled={disabled || locked}
                        />
                      </label>
                      {inputError ? (
                        <small id={`${item.id}-input-error`} role="alert">
                          {inputError}
                        </small>
                      ) : null}
                      <label htmlFor={`${item.id}-expected`}>
                        <span>{t("evaluation.case.expectedOutcome")}</span>
                        <textarea
                          id={`${item.id}-expected`}
                          value={item.expectedOutcome}
                          onChange={(event) =>
                            updateCase(item.id, {
                              expectedOutcome: event.currentTarget.value,
                            })
                          }
                          placeholder={t(
                            "evaluation.case.expectedOutcomePlaceholder",
                          )}
                          aria-invalid={Boolean(expectedError)}
                          aria-describedby={
                            expectedError
                              ? `${item.id}-expected-error`
                              : undefined
                          }
                          disabled={disabled || locked}
                        />
                      </label>
                      {expectedError ? (
                        <small id={`${item.id}-expected-error`} role="alert">
                          {expectedError}
                        </small>
                      ) : null}
                      <div className="migration-evaluation-list-field">
                        <div>
                          <strong>{t("evaluation.case.criteria")}</strong>
                          {!locked ? (
                            <button
                              type="button"
                              onClick={() =>
                                updateCase(item.id, {
                                  criteria: [
                                    ...item.criteria,
                                    { id: stableId("criterion"), text: "" },
                                  ],
                                })
                              }
                              disabled={
                                disabled || item.criteria.length >= MAX_CRITERIA
                              }
                            >
                              {t("evaluation.case.addCriterion")}
                            </button>
                          ) : null}
                        </div>
                        {item.criteria.map((criterion, criterionIndex) => {
                          const error =
                            errors[`${item.id}:criterion:${criterion.id}`];
                          return (
                            <div
                              className="migration-evaluation-list-row"
                              key={criterion.id}
                            >
                              <label
                                htmlFor={`${criterion.id}-text`}
                                className="sr-only"
                              >
                                {t("evaluation.case.criterionLabel", {
                                  index: criterionIndex + 1,
                                })}
                              </label>
                              <input
                                id={`${criterion.id}-text`}
                                value={criterion.text}
                                onChange={(event) =>
                                  updateCase(item.id, {
                                    criteria: item.criteria.map((candidate) =>
                                      candidate.id === criterion.id
                                        ? {
                                            ...candidate,
                                            text: event.currentTarget.value,
                                          }
                                        : candidate,
                                    ),
                                  })
                                }
                                placeholder={t(
                                  "evaluation.case.criterionPlaceholder",
                                )}
                                aria-invalid={Boolean(error)}
                                aria-describedby={
                                  error ? `${criterion.id}-error` : undefined
                                }
                                disabled={disabled || locked}
                              />
                              {!locked ? (
                                <button
                                  type="button"
                                  onClick={() =>
                                    updateCase(item.id, {
                                      criteria: item.criteria.filter(
                                        (candidate) =>
                                          candidate.id !== criterion.id,
                                      ),
                                    })
                                  }
                                  disabled={disabled}
                                  aria-label={t(
                                    "evaluation.case.removeCriterion",
                                    { index: criterionIndex + 1 },
                                  )}
                                >
                                  <RemoveIcon />
                                </button>
                              ) : null}
                              {error ? (
                                <small id={`${criterion.id}-error`} role="alert">
                                  {error}
                                </small>
                              ) : null}
                            </div>
                          );
                        })}
                      </div>
                    </article>
                  );
                })}
              </div>
        </MigrationEvaluationDrawer>
      ) : null}
    </section>
  );
}

type EvaluationProgressTone =
  | "not-started"
  | "active"
  | "complete"
  | "waiting"
  | "issue";

interface EvaluationProgressState {
  tone: EvaluationProgressTone;
  label: string;
}

function migrationProgressState(
  state: MigrationTaskState | null,
  translate: EvaluationTranslate,
): EvaluationProgressState {
  if (!state || state === "awaiting_upload") {
    return {
      tone: "not-started",
      label: translate("evaluation.progress.notStarted"),
    };
  }
  if (["needs_input", "analysis_ready"].includes(state)) {
    return {
      tone: "waiting",
      label: translate("evaluation.progress.waitingConfiguration"),
    };
  }
  if (["analyzing", "migrating", "validating", "packaging"].includes(state)) {
    return {
      tone: "active",
      label: translate("evaluation.progress.inProgress"),
    };
  }
  if (["succeeded", "succeeded_with_warnings"].includes(state)) {
    return {
      tone: "complete",
      label: translate("evaluation.progress.completed"),
    };
  }
  return {
    tone: "issue",
    label: translate("evaluation.progress.issue"),
  };
}

function evaluationProgressState(
  evaluation: MigrationEvaluationStatus | null,
  translate: EvaluationTranslate,
): EvaluationProgressState {
  if (!evaluation || ["disabled", "pending"].includes(evaluation.state)) {
    return {
      tone: "not-started",
      label: translate("evaluation.progress.notStarted"),
    };
  }
  if (["waiting_dataset", "waiting_environment"].includes(evaluation.state)) {
    return {
      tone: "waiting",
      label: translate("evaluation.progress.waitingConfiguration"),
    };
  }
  if (
    [
      "preparing",
      "deploying",
      "executing",
      "judging",
      "aggregating",
    ].includes(evaluation.state)
  ) {
    return {
      tone: "active",
      label: translate("evaluation.progress.inProgress"),
    };
  }
  if (evaluation.state === "completed") {
    return {
      tone: "complete",
      label: translate("evaluation.progress.completed"),
    };
  }
  return {
    tone: "issue",
    label: translate("evaluation.progress.issue"),
  };
}

export function MigrationEvaluationProgress({
  taskState,
  evaluation,
}: {
  taskState: MigrationTaskState | null;
  evaluation: MigrationEvaluationStatus | null;
}) {
  const { t } = useTranslation("migrations");
  const migration = migrationProgressState(taskState, t);
  const effectEvaluation = evaluationProgressState(evaluation, t);
  const stages = [
    {
      id: "migration",
      title: t("evaluation.progress.migration"),
      ...migration,
    },
    {
      id: "evaluation",
      title: t("evaluation.progress.evaluation"),
      ...effectEvaluation,
    },
  ];
  return (
    <div
      className="migration-evaluation-progress"
      role="group"
      aria-label={t("evaluation.progress.label")}
    >
      {stages.map((stage, index) => (
        <div key={stage.id} className={`is-${stage.tone}`}>
          <span aria-hidden="true">{index + 1}</span>
          <div>
            <strong>{stage.title}</strong>
            <small>{stage.label}</small>
          </div>
        </div>
      ))}
    </div>
  );
}

interface ResultProps {
  evaluation: MigrationEvaluationStatus;
  report: string | null;
  reportLoading: boolean;
  reportError: string;
  actionError: string;
  busy: boolean;
  reportDownloading: boolean;
  onResume: (environment: Record<string, string>) => void;
  onRetry: () => void;
  onLoadReport: () => void;
  onDownloadReport: () => void;
}

const EVALUATION_EXECUTION_STATES = [
  "preparing",
  "deploying",
  "executing",
  "judging",
  "aggregating",
] as const;

function EvaluationExecutionProgress({
  evaluation,
}: {
  evaluation: MigrationEvaluationStatus;
}) {
  const { t } = useTranslation("migrations");
  const currentIndex = EVALUATION_EXECUTION_STATES.indexOf(
    evaluation.state as (typeof EVALUATION_EXECUTION_STATES)[number],
  );
  const caseCount = evaluation.dataset?.caseCount ?? 0;
  const dimensionCount = evaluation.dimensions?.length ?? 0;
  const details = {
    preparing: t("evaluation.execution.preparingDetail", { count: caseCount }),
    deploying: t("evaluation.execution.deployingDetail", {
      runtime: evaluation.runtimeName || t("evaluation.execution.runtimeFallback"),
    }),
    executing: t("evaluation.execution.executingDetail", { count: caseCount }),
    judging: t("evaluation.execution.judgingDetail", {
      cases: caseCount,
      dimensions: dimensionCount,
    }),
    aggregating: t("evaluation.execution.aggregatingDetail"),
  } satisfies Record<(typeof EVALUATION_EXECUTION_STATES)[number], string>;
  return (
    <div
      className="migration-evaluation-execution"
    >
      <div
        className="migration-evaluation-execution__summary"
        role="status"
        aria-live="polite"
        aria-atomic="true"
      >
        <TextShimmer>{t(`evaluation.state.${evaluation.state}`)}</TextShimmer>
        <small>{details[EVALUATION_EXECUTION_STATES[currentIndex]]}</small>
      </div>
      <ol>
        {EVALUATION_EXECUTION_STATES.map((state, index) => {
          const tone =
            index < currentIndex
              ? "complete"
              : index === currentIndex
                ? "active"
                : "pending";
          return (
            <li key={state} className={`is-${tone}`}>
              <span aria-hidden="true">{index + 1}</span>
              <div>
                <strong>{t(`evaluation.execution.${state}`)}</strong>
                <small>{details[state]}</small>
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

export function MigrationEvaluationResult({
  evaluation,
  report,
  reportLoading,
  reportError,
  actionError,
  busy,
  reportDownloading,
  onResume,
  onRetry,
  onLoadReport,
  onDownloadReport,
}: ResultProps) {
  const { t } = useTranslation("migrations");
  const [reportOpen, setReportOpen] = useState(false);
  const [environment, setEnvironment] = useState<Record<string, string>>(() =>
    initialEvaluationEnvironmentValues(evaluation.environment),
  );
  const required = evaluation.environment?.required ?? [];
  const optional = evaluation.environment?.optional ?? [];
  const environmentKeys = [...required, ...optional];
  const environmentSignature = JSON.stringify([
    environmentKeys,
    evaluation.environment?.defaults ?? {},
  ]);
  useEffect(() => {
    setEnvironment(initialEvaluationEnvironmentValues(evaluation.environment));
  }, [environmentSignature]);
  useEffect(() => {
    setReportOpen(false);
  }, [evaluation.report?.versionId]);
  if (!evaluation.enabled) return null;
  const active = [
    "preparing",
    "deploying",
    "executing",
    "judging",
    "aggregating",
  ].includes(evaluation.state);
  const environmentReady = required.every((key) => Boolean(environment[key]));
  return (
    <section
      className="migration-evaluation-result"
      aria-labelledby="migration-evaluation-result-title"
    >
      <header>
        <div>
          <strong id="migration-evaluation-result-title">
            {t("evaluation.result.title")}
          </strong>
        </div>
        {evaluation.attempt ? (
          <small>
            {t("evaluation.result.attempt", { attempt: evaluation.attempt })}
          </small>
        ) : null}
      </header>
      {active ? <EvaluationExecutionProgress evaluation={evaluation} /> : null}
      {evaluation.state === "pending" ? (
        <p>{t("evaluation.result.pending")}</p>
      ) : null}
      {evaluation.state === "waiting_environment" ? (
        <div className="migration-evaluation-environment">
          <p>{t("evaluation.environment.description")}</p>
          {environmentKeys.map((key) => (
            <label key={key}>
              <span>
                {key}
                {required.includes(key) ? (
                  <b aria-hidden="true">*</b>
                ) : (
                  <small>{t("evaluation.environment.optional")}</small>
                )}
              </span>
              <input
                type="text"
                value={environment[key] ?? ""}
                onChange={(event) =>
                  setEnvironment((current) => ({
                    ...current,
                    [key]: event.currentTarget.value,
                  }))
                }
                autoComplete="off"
                required={required.includes(key)}
                aria-required={required.includes(key)}
                disabled={busy}
              />
            </label>
          ))}
          <small>{t("evaluation.environment.security")}</small>
          <button
            type="button"
            className="is-primary"
            onClick={() =>
              onResume(
                Object.fromEntries(
                  Object.entries(environment).filter(([, value]) => value),
                ),
              )
            }
            disabled={busy || !environmentReady}
          >
            {busy
              ? t("evaluation.environment.submitting")
              : t("evaluation.environment.submit")}
          </button>
        </div>
      ) : null}
      {["failed", "blocked"].includes(evaluation.state) ? (
        <div className="migration-evaluation-failure" role="alert">
          <strong>{evaluation.error?.message || evaluation.message}</strong>
          {evaluation.canRetry ? (
            <button type="button" onClick={onRetry} disabled={busy}>
              {busy
                ? t("evaluation.result.retrying")
                : t("evaluation.result.retry")}
            </button>
          ) : null}
        </div>
      ) : null}
      {actionError ? (
        <div className="migration-evaluation-failure" role="alert">
          <span>{actionError}</span>
        </div>
      ) : null}
      {evaluation.state === "completed" ? (
        <div className="migration-evaluation-report-actions">
          <div>
            <strong>{t("evaluation.result.reportTitle")}</strong>
            <small>{t("evaluation.result.reportHtmlDescription")}</small>
          </div>
          <div>
            <button
              type="button"
              className="is-primary"
              onClick={() => {
                setReportOpen(true);
                onLoadReport();
              }}
              disabled={!evaluation.report?.viewReady}
            >
              {t("evaluation.result.viewReport")}
            </button>
            <button
              type="button"
              onClick={onDownloadReport}
              disabled={busy || !evaluation.report?.downloadReady}
            >
              {reportDownloading
                ? t("evaluation.result.downloadingReport")
                : t("evaluation.result.downloadReport")}
            </button>
          </div>
        </div>
      ) : null}
      {evaluation.state === "completed" && reportOpen ? (
        <MigrationEvaluationDrawer
          titleId="migration-evaluation-report-drawer-title"
          title={t("evaluation.result.reportTitle")}
          description={t("evaluation.result.reportDrawerDescription")}
          closeLabel={t("evaluation.result.closeReportAria")}
          onClose={() => setReportOpen(false)}
          variant="report"
          footer={
            <>
              <span>{t("evaluation.result.reportHtmlDescription")}</span>
              <div className="migration-evaluation-report-drawer__actions">
                <button
                  type="button"
                  onClick={onDownloadReport}
                  disabled={busy || !evaluation.report?.downloadReady}
                >
                  {reportDownloading
                    ? t("evaluation.result.downloadingReport")
                    : t("evaluation.result.downloadReport")}
                </button>
                <button
                  type="button"
                  className="is-primary"
                  onClick={() => setReportOpen(false)}
                >
                  {t("evaluation.result.closeReport")}
                </button>
              </div>
            </>
          }
        >
          {reportLoading || (!report && !reportError) ? (
            <TextShimmer>{t("evaluation.result.loadingReport")}</TextShimmer>
          ) : reportError ? (
            <div className="migration-evaluation-failure" role="alert">
              <span>{reportError}</span>
              <button
                type="button"
                onClick={onLoadReport}
                disabled={reportLoading}
              >
                {t("actions.reload")}
              </button>
            </div>
          ) : (
            <iframe
              className="migration-evaluation-report-html__preview"
              title={t("evaluation.result.reportPreviewTitle")}
              srcDoc={report ?? ""}
              sandbox=""
            />
          )}
        </MigrationEvaluationDrawer>
      ) : null}
    </section>
  );
}
