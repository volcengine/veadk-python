import { useId, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@openai/apps-sdk-ui/components/Button";
import { NativeSelect } from "./NativeSelect";
import {
  DSH_CONFIG_SOURCE, DSH_PROTOCOLS, NATIVE_SECTIONS,
  nativeProviderOptions, nativeModelOptions, resolveNativeField, updateNativeField,
  type NativeConfigDraft, type NativeConfigErrors, type NativeField,
  type NativeModelDraft, type NativeProviderDraft,
} from "./nativeConfig";

interface Props {
  draft: NativeConfigDraft;
  errors: NativeConfigErrors;
  onChange: (draft: NativeConfigDraft) => void;
}

function FieldRow({ field, value, onChange, label, error, placeholder, help, allowEmpty = true, disabled = false }: {
  field: NativeField;
  value: string;
  onChange: (value: string) => void;
  label: string;
  error?: string;
  placeholder?: string;
  help?: string;
  allowEmpty?: boolean;
  disabled?: boolean;
}) {
  const id = useId();
  const { t } = useTranslation("deepseek");
  const emptyLabel = t("optional");
  return (
    <tr data-invalid={Boolean(error)}>
      <th scope="row">
        <label htmlFor={field.kind === "select" ? undefined : id}>{label}</label>
        <span className="dsh-native-path">{field.path}</span>
      </th>
      <td>
        <div className="dsh-native-control" role={field.kind === "select" ? "group" : undefined} aria-label={field.kind === "select" ? label : undefined} aria-invalid={Boolean(error)} aria-describedby={help || error ? `${id}-help` : undefined}>
          {field.kind === "select" ? (
            <NativeSelect
              label={label}
              value={value}
              placeholder={placeholder ?? emptyLabel}
              options={field.options ?? []}
              allowCustom={field.allowCustom}
              allowEmpty={allowEmpty}
              disabled={disabled}
              error={error}
              describedBy={help || error ? `${id}-help` : undefined}
              onChange={onChange}
            />
          ) : (
            <input
              id={id}
              className="cw-input"
              type="text"
              inputMode={field.kind === "number" ? "decimal" : undefined}
              value={value}
              placeholder={placeholder ?? emptyLabel}
              autoComplete="off"
              spellCheck={false}
              aria-invalid={Boolean(error)}
              aria-describedby={help || error ? `${id}-help` : undefined}
              onChange={(event) => onChange(event.target.value)}
            />
          )}
          {(help || error) && <span id={`${id}-help`} className={error ? "cw-error-text" : "cw-help"}>{error ?? help}</span>}
        </div>
      </td>
    </tr>
  );
}

function ConfigSection({ title, path, children, open = false }: { title: string; path: string; children: ReactNode; open?: boolean }) {
  return (
    <details className="dsh-config-section" open={open}>
      <summary><span>{title}</span><span className="dsh-section-path">{path}</span></summary>
      <div className="dsh-config-section-body">{children}</div>
    </details>
  );
}

function newModel(): NativeModelDraft {
  return { key: crypto.randomUUID(), id: "", name: "", contextWindow: "", maxTokens: "" };
}

export function NativeConfigForm({ draft, errors, onChange }: Props) {
  const { t } = useTranslation("deepseek");
  const fieldLabel = (path: string) => t(`fields.${path.replace(/\./g, "_")}`);
  const errorText = (path: string) => errors[path] ? t(`errors.${errors[path]}`) : undefined;
  const providers = nativeProviderOptions(draft);
  const defaultProvider = (draft.fields["agent-default-model.provider"] ?? "").trim() || "deepseek-official";
  const updateProvider = (key: string, changes: Partial<NativeProviderDraft>) => onChange({
    ...draft, providers: draft.providers.map((item) => item.key === key ? { ...item, ...changes } : item),
  });

  function renderSection(section: (typeof NATIVE_SECTIONS)[number]) {
    return (
      <ConfigSection key={section.id} title={t(`sections.${section.id}`)} path={section.id === "defaults" ? "agent-default-model · agent-presets · permission" : section.fields[0].path.split(".")[0]} open={section.id === "defaults"}>
        {section.id === "defaults" && <p className="cw-help dsh-section-note">{t("defaultsHelp")}</p>}
        <table className="dsh-config-table" aria-label={t(`sections.${section.id}`)}><tbody>
          {section.fields.map((definition) => {
            const field = resolveNativeField(draft, definition);
            const noReasoning = field.path === "agent-default-model.reasoningEffort" && !field.options?.length;
            const noModels = field.path === "agent-default-model.model" && !field.options?.length && !field.allowCustom;
            return (
              <FieldRow key={field.path.startsWith("agent-default-model.") ? `${field.path}:${defaultProvider}` : field.path}
                field={field} label={fieldLabel(field.path)} value={draft.fields[field.path] ?? ""} error={errorText(field.path)}
                disabled={noReasoning || noModels} allowEmpty={field.path !== "agent-default-model.provider"}
                help={noReasoning ? t("reasoningUnavailable") : noModels ? t("modelsUnavailable") : field.check === "env" ? t("credentialHelp") : field.path === "permission.defaultPreset" ? t("permissionHelp") : undefined}
                onChange={(value) => onChange(updateNativeField(draft, field.path, value))} />
            );
          })}
        </tbody></table>
        {section.id === "subagents" && (
          <div className="dsh-model-routes" data-invalid={Boolean(errors["subagent-model-selection.allowedModels"])}>
            <p className="cw-help">{t("routesHelp")}</p>
            {draft.allowedModels.map((route, index) => (
              <div className="dsh-route" key={route.key}>
                {(["provider", "model"] as const).map((field) => (
                  <div key={field} className="dsh-route-field" role="group" aria-label={t(`route.${field}`, { index: index + 1 })}>
                    <span className="cw-label">{t(`route.${field}`, { index: index + 1 })}</span>
                    <NativeSelect key={field === "model" ? route.provider : field} label={t(`route.${field}`, { index: index + 1 })}
                      value={route[field]} options={field === "provider" ? providers : nativeModelOptions(draft, route.provider)}
                      allowEmpty={false}
                      allowCustom={field === "model" && route.provider === "deepseek-official"}
                      disabled={field === "model" && !route.provider}
                      placeholder={field === "model" && !route.provider ? t("selectProviderFirst") : t("selectOption")}
                      onChange={(value) => onChange({ ...draft, allowedModels: draft.allowedModels.map((item) => item.key === route.key
                        ? { ...item, [field]: value, ...(field === "provider" && value !== item.provider ? { model: nativeModelOptions(draft, value)[0] ?? "" } : {}) }
                        : item) })} />
                  </div>
                ))}
                <Button className="cw-btn cw-btn-ghost" color="secondary" variant="ghost" aria-label={t("removeRoute", { index: index + 1 })} onClick={() => onChange({ ...draft, allowedModels: draft.allowedModels.filter((item) => item.key !== route.key) })}>{t("remove")}</Button>
              </div>
            ))}
            {errors["subagent-model-selection.allowedModels"] && <p className="cw-error-text">{errorText("subagent-model-selection.allowedModels")}</p>}
            <Button className="cw-btn cw-btn-ghost" color="secondary" variant="outline" onClick={() => onChange({ ...draft, allowedModels: [...draft.allowedModels, { key: crypto.randomUUID(), provider: "", model: "" }] })}>{t("addRoute")}</Button>
          </div>
        )}
      </ConfigSection>
    );
  }

  return (
    <div className="dsh-native-form">
      {NATIVE_SECTIONS.slice(0, 2).map(renderSection)}
      <ConfigSection title={t("sections.providers")} path="llm-pi-ai.providers">
        <p className="cw-help dsh-section-note">{t("providersHelp")}</p>
        {draft.providers.map((provider, index) => {
          const path = `providers.${provider.key}`;
          return (
            <fieldset className="dsh-provider" key={provider.key}>
              <legend>{t("provider", { index: index + 1 })}</legend>
              <table className="dsh-config-table" aria-label={t("provider", { index: index + 1 })}><tbody>
                {(["id", "displayName", "baseURL", "api", "apiKeyEnv"] as const).map((name) => (
                  <FieldRow key={name} field={{ path: name, kind: name === "api" ? "select" : "text", options: name === "api" ? DSH_PROTOCOLS : undefined }}
                    label={t(`providerFields.${name}`)} value={provider[name]} error={errorText(`${path}.${name}`)} allowEmpty={false}
                    placeholder={t(`providerPlaceholders.${name}`)} help={name === "apiKeyEnv" ? t("credentialHelp") : undefined}
                    onChange={(value) => updateProvider(provider.key, { [name]: value })} />
                ))}
              </tbody></table>
              <div data-invalid={Boolean(errors[`${path}.models`])}>
                {provider.models.map((model, modelIndex) => (
                  <fieldset className="dsh-provider-model" key={model.key}>
                    <legend>{t("model", { index: modelIndex + 1 })}</legend>
                    <table className="dsh-config-table" aria-label={t("model", { index: modelIndex + 1 })}><tbody>
                      {(["id", "name", "contextWindow", "maxTokens"] as const).map((name) => (
                        <FieldRow key={name} field={{ path: name, kind: name === "contextWindow" || name === "maxTokens" ? "number" : "text" }}
                          label={t(`modelFields.${name}`)} value={model[name]} error={errorText(`${path}.models.${model.key}.${name}`)}
                          placeholder={name === "id" ? t("modelIdPlaceholder") : undefined}
                          onChange={(value) => updateProvider(provider.key, { models: provider.models.map((item) => item.key === model.key ? { ...item, [name]: value } : item) })} />
                      ))}
                    </tbody></table>
                    <Button className="cw-btn cw-btn-ghost" color="secondary" variant="ghost" aria-label={t("removeModel", { index: modelIndex + 1 })} onClick={() => updateProvider(provider.key, { models: provider.models.filter((item) => item.key !== model.key) })}>{t("removeModel", { index: modelIndex + 1 })}</Button>
                  </fieldset>
                ))}
                {errors[`${path}.models`] && <p className="cw-error-text">{errorText(`${path}.models`)}</p>}
                <div className="dsh-provider-actions">
                  <Button className="cw-btn cw-btn-ghost" color="secondary" variant="outline" onClick={() => updateProvider(provider.key, { models: [...provider.models, newModel()] })}>{t("addModel")}</Button>
                  <Button className="cw-btn cw-btn-ghost" color="secondary" variant="ghost" aria-label={t("removeProvider", { index: index + 1 })} onClick={() => onChange({ ...draft, providers: draft.providers.filter((item) => item.key !== provider.key) })}>{t("removeProvider", { index: index + 1 })}</Button>
                </div>
              </div>
            </fieldset>
          );
        })}
        <div className="dsh-section-actions"><Button className="cw-btn cw-btn-ghost" color="secondary" variant="outline" onClick={() => onChange({ ...draft, providers: [...draft.providers, {
          key: crypto.randomUUID(), id: "", displayName: "", baseURL: "", api: "openai-completions", apiKeyEnv: "", models: [newModel()],
        }] })}>{t("addProvider")}</Button></div>
      </ConfigSection>
      {NATIVE_SECTIONS.slice(2).map(renderSection)}
      <p className="cw-help dsh-source-note">{t("coverage")} <a href={`${DSH_CONFIG_SOURCE}/docs/config-catalog.md`} target="_blank" rel="noreferrer">{t("source")}</a></p>
    </div>
  );
}
