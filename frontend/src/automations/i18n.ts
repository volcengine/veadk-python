import type { TOptions } from "i18next";

import { i18n } from "../i18n/runtime";
import enAutomations from "../i18n/resources/en-US/automations.json";
import zhAutomations from "../i18n/resources/zh-CN/automations.json";

if (!i18n.hasResourceBundle("en-US", "automations")) {
  i18n.addResourceBundle("en-US", "automations", enAutomations, true, true);
}
if (!i18n.hasResourceBundle("zh-CN", "automations")) {
  i18n.addResourceBundle("zh-CN", "automations", zhAutomations, true, true);
}

/** Translate automation-generated content at call time so locale changes apply immediately. */
export function automationT(key: string, options: TOptions = {}): string {
  return i18n.t(key, { ...options, ns: "automations" });
}
