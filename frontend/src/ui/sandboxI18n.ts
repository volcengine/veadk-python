import type { TOptions } from "i18next";

import { i18n } from "../i18n/runtime";
import enSandbox from "../i18n/resources/en-US/sandbox.json";
import zhSandbox from "../i18n/resources/zh-CN/sandbox.json";

if (!i18n.hasResourceBundle("en-US", "sandbox")) {
  i18n.addResourceBundle("en-US", "sandbox", enSandbox, true, true);
}
if (!i18n.hasResourceBundle("zh-CN", "sandbox")) {
  i18n.addResourceBundle("zh-CN", "sandbox", zhSandbox, true, true);
}

/** Translate Sandbox-generated content at call time so locale changes apply immediately. */
export function sandboxT(key: string, options: TOptions = {}): string {
  return i18n.t(key, { ...options, ns: "sandbox" });
}
