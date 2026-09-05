import type { TOptions } from "i18next";

import { i18n } from "../i18n/runtime";
import enCreate from "../i18n/resources/en-US/create.json";
import zhCreate from "../i18n/resources/zh-CN/create.json";

if (!i18n.hasResourceBundle("en-US", "create")) {
  i18n.addResourceBundle("en-US", "create", enCreate, true, true);
}
if (!i18n.hasResourceBundle("zh-CN", "create")) {
  i18n.addResourceBundle("zh-CN", "create", zhCreate, true, true);
}

/** Translate non-React create-flow copy at call time so locale changes apply immediately. */
export function createT(key: string, options: TOptions = {}): string {
  return i18n.t(key, { ...options, ns: "create" });
}
