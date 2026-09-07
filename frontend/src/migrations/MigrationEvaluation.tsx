import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import type {
  MigrationCapabilities,
  MigrationEvaluationCase,
  MigrationEvaluationDataset,
  MigrationEvaluationDimensionId,
  MigrationEvaluationReport,
  MigrationEvaluationStatus,
} from "../adk/migrations";
import { TextShimmer } from "../ui/text-shimmer/TextShimmer";
import "./MigrationEvaluation.css";

const STANDARD_DIMENSIONS: MigrationEvaluationDimensionId[] = [
  "semantic_fidelity",
  "output_contract",
  "workflow_tool_fidelity",
];
const MAX_CASES = 100;
const MAX_MESSAGES = 20;
const MAX_MESSAGE_BYTES = 32 * 1024;
const MAX_REFERENCE_BYTES = 16 * 1024;
const MAX_CRITERIA = 20;
const MAX_CRITERION_BYTES = 2 * 1024;
const MAX_DATASET_BYTES = 10 * 1024 * 1024;

export interface EvaluationDraftMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
}

export interface EvaluationDraftCriterion {
  id: string;
  text: string;
}

export interface EvaluationDraftCase {
  id: string;
  userInput: string;
  expectedOutcome: string;
  criteria: EvaluationDraftCriterion[];
  priorMessages: EvaluationDraftMessage[];
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
    priorMessages: [],
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
    priorMessages: item.priorMessages.map((message) => ({
      role: message.role,
      content: message.content.trim(),
    })),
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
      priorMessages: item.priorMessages.map((message) => ({
        id: stableId("message"),
        ...message,
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
    if (item.priorMessages.length + 1 > MAX_MESSAGES) {
      errors[`${item.id}:messages`] = translate(
        "evaluation.validation.messageCount",
        { count: MAX_MESSAGES },
      );
    }
    const messageBytes = [
      ...item.priorMessages.map((message) => message.content.trim()),
      item.userInput.trim(),
    ].reduce((total, value) => total + utf8Bytes(value), 0);
    if (messageBytes > MAX_MESSAGE_BYTES) {
      errors[`${item.id}:messages`] = translate(
        "evaluation.validation.messageBytes",
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
    for (const message of item.priorMessages) {
      if (!message.content.trim()) {
        errors[`${item.id}:message:${message.id}`] = translate(
          "evaluation.validation.messageRequired",
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
            onChange={(event) =>
              onChange({
                ...value,
                enabled: event.currentTarget.checked,
              })
            }
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
        <div className="migration-evaluation-editor">
          <div className="migration-evaluation-editor__heading">
            <div>
              <strong>
                {locked
                  ? t("evaluation.setup.lockedTitle")
                  : t("evaluation.setup.casesTitle")}
              </strong>
              <span>
                {locked
                  ? t("evaluation.setup.lockedDescription")
                  : t("evaluation.setup.casesDescription")}
              </span>
            </div>
            {!locked ? (
              <div className="migration-evaluation-editor__actions">
                <button
                  type="button"
                  onClick={() => setBulkOpen((current) => !current)}
                  disabled={disabled}
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
          </div>
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
              const messagesError = errors[`${item.id}:messages`];
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
                                  criteria: item.criteria.map((criterion) => ({
                                    ...criterion,
                                    id: stableId("criterion"),
                                  })),
                                  priorMessages: item.priorMessages.map(
                                    (message) => ({
                                      ...message,
                                      id: stableId("message"),
                                    }),
                                  ),
                                },
                                ...value.cases.slice(index + 1),
                              ],
                            })
                          }
                          disabled={disabled || value.cases.length >= MAX_CASES}
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
                      placeholder={t("evaluation.case.userInputPlaceholder")}
                      required
                      aria-required="true"
                      aria-invalid={Boolean(inputError || messagesError)}
                      aria-describedby={
                        inputError || messagesError
                          ? `${item.id}-input-error`
                          : undefined
                      }
                      disabled={disabled || locked}
                    />
                  </label>
                  {inputError || messagesError ? (
                    <small id={`${item.id}-input-error`} role="alert">
                      {inputError || messagesError}
                    </small>
                  ) : null}
                  <details className="migration-evaluation-case__optional">
                    <summary>{t("evaluation.case.optional")}</summary>
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
                        aria-invalid={Boolean(
                          errors[`${item.id}:expectedOutcome`],
                        )}
                        aria-describedby={
                          errors[`${item.id}:expectedOutcome`]
                            ? `${item.id}-expected-error`
                            : undefined
                        }
                        disabled={disabled || locked}
                      />
                    </label>
                    {errors[`${item.id}:expectedOutcome`] ? (
                      <small id={`${item.id}-expected-error`} role="alert">
                        {errors[`${item.id}:expectedOutcome`]}
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
                    <div className="migration-evaluation-list-field">
                      <div>
                        <strong>
                          {t("evaluation.case.priorConversation")}
                        </strong>
                        {!locked ? (
                          <button
                            type="button"
                            onClick={() =>
                              updateCase(item.id, {
                                priorMessages: [
                                  ...item.priorMessages,
                                  {
                                    id: stableId("message"),
                                    role:
                                      item.priorMessages.length % 2
                                        ? "assistant"
                                        : "user",
                                    content: "",
                                  },
                                ],
                              })
                            }
                            disabled={
                              disabled ||
                              item.priorMessages.length >= MAX_MESSAGES - 1
                            }
                          >
                            {t("evaluation.case.addMessage")}
                          </button>
                        ) : null}
                      </div>
                      {item.priorMessages.map((message, messageIndex) => {
                        const error =
                          errors[`${item.id}:message:${message.id}`];
                        return (
                          <div
                            className="migration-evaluation-message-row"
                            key={message.id}
                          >
                            <select
                              aria-label={t("evaluation.case.messageRole", {
                                index: messageIndex + 1,
                              })}
                              value={message.role}
                              onChange={(event) =>
                                updateCase(item.id, {
                                  priorMessages: item.priorMessages.map(
                                    (candidate) =>
                                      candidate.id === message.id
                                        ? {
                                            ...candidate,
                                            role: event.currentTarget.value as
                                              | "user"
                                              | "assistant",
                                          }
                                        : candidate,
                                  ),
                                })
                              }
                              disabled={disabled || locked}
                            >
                              <option value="user">
                                {t("evaluation.case.userRole")}
                              </option>
                              <option value="assistant">
                                {t("evaluation.case.assistantRole")}
                              </option>
                            </select>
                            <textarea
                              aria-label={t("evaluation.case.messageContent", {
                                index: messageIndex + 1,
                              })}
                              value={message.content}
                              onChange={(event) =>
                                updateCase(item.id, {
                                  priorMessages: item.priorMessages.map(
                                    (candidate) =>
                                      candidate.id === message.id
                                        ? {
                                            ...candidate,
                                            content: event.currentTarget.value,
                                          }
                                        : candidate,
                                  ),
                                })
                              }
                              aria-invalid={Boolean(error)}
                              aria-describedby={
                                error ? `${message.id}-error` : undefined
                              }
                              disabled={disabled || locked}
                            />
                            {!locked ? (
                              <button
                                type="button"
                                onClick={() =>
                                  updateCase(item.id, {
                                    priorMessages: item.priorMessages.filter(
                                      (candidate) =>
                                        candidate.id !== message.id,
                                    ),
                                  })
                                }
                                disabled={disabled}
                                aria-label={t("evaluation.case.removeMessage", {
                                  index: messageIndex + 1,
                                })}
                              >
                                <RemoveIcon />
                              </button>
                            ) : null}
                            {error ? (
                              <small id={`${message.id}-error`} role="alert">
                                {error}
                              </small>
                            ) : null}
                          </div>
                        );
                      })}
                    </div>
                  </details>
                </article>
              );
            })}
          </div>
          {!locked && !configLocked ? (
            <details className="migration-evaluation-advanced">
              <summary>{t("evaluation.advanced.title")}</summary>
              <div className="migration-evaluation-preset">
                <label>
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
                    disabled={disabled}
                  />
                  <span>
                    <strong>{t("evaluation.advanced.standard")}</strong>
                    <small>
                      {t("evaluation.advanced.standardDescription")}
                    </small>
                  </span>
                </label>
                <label>
                  <input
                    type="radio"
                    name="migration-evaluation-preset"
                    value="custom"
                    checked={value.preset === "custom"}
                    onChange={() => onChange({ ...value, preset: "custom" })}
                    disabled={disabled}
                  />
                  <span>
                    <strong>{t("evaluation.advanced.custom")}</strong>
                    <small>{t("evaluation.advanced.customDescription")}</small>
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
                    <label key={dimension.id}>
                      <input
                        type="checkbox"
                        checked={value.dimensions.includes(dimension.id)}
                        onChange={() => toggleDimension(dimension.id)}
                        disabled={
                          disabled ||
                          (value.dimensions.length === 1 &&
                            value.dimensions.includes(dimension.id))
                        }
                      />
                      <span>
                        <strong>
                          {t(`evaluation.dimension.${dimension.id}`)}
                        </strong>
                        <small>
                          {t(`evaluation.dimensionDescription.${dimension.id}`)}
                        </small>
                      </span>
                    </label>
                  ))}
                </div>
              ) : null}
              {errors.dimensions ? (
                <small id="migration-evaluation-dimensions-error" role="alert">
                  {errors.dimensions}
                </small>
              ) : null}
            </details>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

interface ResultProps {
  evaluation: MigrationEvaluationStatus;
  report: MigrationEvaluationReport | null;
  reportLoading: boolean;
  reportError: string;
  busy: boolean;
  reportDownloading: boolean;
  onResume: (environment: Record<string, string>) => void;
  onRetry: () => void;
  onReloadReport: () => void;
  onDownloadReport: () => void;
}

function scoreLabel(score: number | null): string {
  return score === null ? "N/A" : String(score);
}

export function MigrationEvaluationResult({
  evaluation,
  report,
  reportLoading,
  reportError,
  busy,
  reportDownloading,
  onResume,
  onRetry,
  onReloadReport,
  onDownloadReport,
}: ResultProps) {
  const { t } = useTranslation("migrations");
  const [environment, setEnvironment] = useState<Record<string, string>>({});
  if (!evaluation.enabled) return null;
  const active = [
    "preparing",
    "deploying",
    "executing",
    "judging",
    "aggregating",
    "cleaning",
  ].includes(evaluation.state);
  const required = evaluation.requiredEnvironment ?? [];
  const environmentReady = required.every((key) => Boolean(environment[key]));
  const stateMessage = t(`evaluation.state.${evaluation.state}`);
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
          <span>{stateMessage}</span>
        </div>
        {evaluation.attempt ? (
          <small>
            {t("evaluation.result.attempt", { attempt: evaluation.attempt })}
          </small>
        ) : null}
      </header>
      <div
        className="migration-evaluation-stages"
        aria-label={t("evaluation.result.progressLabel")}
      >
        <div className="is-complete">
          <span aria-hidden="true">1</span>
          <strong>{t("evaluation.result.migrationStage")}</strong>
        </div>
        <i aria-hidden="true" />
        <div
          className={
            evaluation.state === "completed"
              ? "is-complete"
              : active
                ? "is-active"
                : ""
          }
        >
          <span aria-hidden="true">2</span>
          <strong>{t("evaluation.result.evaluationStage")}</strong>
        </div>
      </div>
      {active ? <TextShimmer>{stateMessage}</TextShimmer> : null}
      {evaluation.state === "pending" ? (
        <p>{t("evaluation.result.pending")}</p>
      ) : null}
      {evaluation.state === "waiting_environment" ? (
        <div className="migration-evaluation-environment">
          <p>{t("evaluation.environment.description")}</p>
          {required.map((key) => (
            <label key={key}>
              <span>
                {key}
                <b aria-hidden="true">*</b>
              </span>
              <input
                type="password"
                value={environment[key] ?? ""}
                onChange={(event) =>
                  setEnvironment((current) => ({
                    ...current,
                    [key]: event.currentTarget.value,
                  }))
                }
                autoComplete="off"
                required
                aria-required="true"
                disabled={busy}
              />
            </label>
          ))}
          <small>{t("evaluation.environment.security")}</small>
          <button
            type="button"
            className="is-primary"
            onClick={() => onResume(environment)}
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
      {reportError && evaluation.state !== "completed" ? (
        <div className="migration-evaluation-failure" role="alert">
          <span>{reportError}</span>
        </div>
      ) : null}
      {evaluation.state === "completed" ? (
        reportLoading ? (
          <TextShimmer>{t("evaluation.result.loadingReport")}</TextShimmer>
        ) : reportError ? (
          <div className="migration-evaluation-failure" role="alert">
            <span>{reportError}</span>
            <button type="button" onClick={onReloadReport}>
              {t("actions.reload")}
            </button>
          </div>
        ) : report ? (
          <div className="migration-evaluation-report">
            <div className="migration-evaluation-report__toolbar">
              <div>
                <strong>{t("evaluation.result.reportSummary")}</strong>
                <small>
                  {t("evaluation.result.reportVersion", {
                    version: report.dataset_version,
                    prompt: report.prompt_version,
                  })}
                </small>
              </div>
              <button
                type="button"
                onClick={onDownloadReport}
                disabled={busy || !report.asset.downloadReady}
              >
                {reportDownloading
                  ? t("evaluation.result.downloadingReport")
                  : t("evaluation.result.downloadReport")}
              </button>
            </div>
            <div className="migration-evaluation-report__metrics">
              <article className="is-primary">
                <span>{t("evaluation.result.overallScore")}</span>
                <strong>{scoreLabel(report.summary.score)}</strong>
                <small>{t("evaluation.result.scoreScale")}</small>
              </article>
              <article>
                <span>{t("evaluation.result.evidenceCoverage")}</span>
                <strong>{report.evidence_coverage.rate}%</strong>
                <small>
                  {t("evaluation.result.coverageDetail", {
                    scored: report.evidence_coverage.scored,
                    total: report.evidence_coverage.total,
                  })}
                </small>
              </article>
              <article>
                <span>{t("evaluation.result.executionSuccess")}</span>
                <strong>{report.execution.success_rate}%</strong>
                <small>
                  {t("evaluation.result.executionDetail", {
                    succeeded: report.execution.succeeded,
                    total: report.execution.total,
                  })}
                </small>
              </article>
              <article>
                <span>{t("evaluation.result.naCount")}</span>
                <strong>{report.evidence_coverage.na}</strong>
                <small>{t("evaluation.result.naDescription")}</small>
              </article>
            </div>
            <div className="migration-evaluation-report__dimensions">
              {report.summary.dimensions.map((dimension) => (
                <article key={dimension.id}>
                  <span>{t(`evaluation.dimension.${dimension.id}`)}</span>
                  <strong>{scoreLabel(dimension.score)}</strong>
                  <p>{dimension.reason}</p>
                </article>
              ))}
            </div>
            <div className="migration-evaluation-gap">
              <strong>{t("evaluation.result.gapDescription")}</strong>
              <p>{report.migration_gap_description}</p>
            </div>
            {report.lowest_scoring_cases.length ||
            report.execution_failures.length ||
            report.critical_mismatches.length ? (
              <div className="migration-evaluation-report__findings">
                {report.lowest_scoring_cases.length ? (
                  <section>
                    <strong>{t("evaluation.result.lowestScoringCases")}</strong>
                    <ul>
                      {report.lowest_scoring_cases.map((item) => (
                        <li key={item.case_id}>
                          <span>{item.case_id}</span>
                          <b>{item.score}</b>
                        </li>
                      ))}
                    </ul>
                  </section>
                ) : null}
                {report.execution_failures.length ? (
                  <section>
                    <strong>{t("evaluation.result.executionFailures")}</strong>
                    <ul>
                      {report.execution_failures.map((item) => (
                        <li key={item.case_id}>
                          <span>{item.case_id}</span>
                          <small>{item.message}</small>
                        </li>
                      ))}
                    </ul>
                  </section>
                ) : null}
                {report.critical_mismatches.length ? (
                  <section>
                    <strong>{t("evaluation.result.criticalEvidence")}</strong>
                    <ul>
                      {report.critical_mismatches.map((item) => (
                        <li key={`${item.case_id}-${item.dimension_id}`}>
                          <span>
                            {item.case_id} · {t(`evaluation.dimension.${item.dimension_id}`)}
                          </span>
                          <small>{item.reason}</small>
                        </li>
                      ))}
                    </ul>
                  </section>
                ) : null}
              </div>
            ) : null}
            {report.limitations.length ? (
              <div className="migration-evaluation-limitations">
                <strong>{t("evaluation.result.limitations")}</strong>
                <ul>
                  {report.limitations.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
            ) : null}
            <details className="migration-evaluation-evidence">
              <summary>
                {t("evaluation.result.viewEvidence", {
                  count: report.cases.length,
                })}
              </summary>
              {report.cases.map((item, index) => (
                <article key={item.case_id}>
                  <header>
                    <strong>
                      {t("evaluation.case.title", { index: index + 1 })}
                    </strong>
                    <span>
                      <small>
                        {t(`evaluation.result.executionState.${item.execution.state}`)}
                      </small>
                      {item.output.truncated ? (
                        <small>{t("evaluation.result.outputTruncated")}</small>
                      ) : null}
                    </span>
                  </header>
                  {item.execution.error ? (
                    <p className="migration-evaluation-evidence__error">
                      {item.execution.error.message}
                    </p>
                  ) : null}
                  <pre>{item.output.text}</pre>
                  <ul>
                    {item.dimensions.map((dimension) => (
                      <li key={dimension.id}>
                        <strong>
                          {t(`evaluation.dimension.${dimension.id}`)} ·{" "}
                          {scoreLabel(dimension.score)}
                        </strong>
                        <span>{dimension.reason}</span>
                        <small>
                          {t("evaluation.result.severityLabel", {
                            severity: t(
                              `evaluation.result.severity.${dimension.severity}`,
                            ),
                          })}
                          {dimension.evidence_sources.length
                            ? ` · ${dimension.evidence_sources
                                .map((source) =>
                                  t(`evaluation.result.evidenceSource.${source}`),
                                )
                                .join(t("evaluation.result.listSeparator"))}`
                            : ""}
                        </small>
                        {dimension.evidence.length ? (
                          <ul>
                            {dimension.evidence.map((evidence) => (
                              <li key={evidence}>{evidence}</li>
                            ))}
                          </ul>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                </article>
              ))}
            </details>
          </div>
        ) : null
      ) : null}
    </section>
  );
}
