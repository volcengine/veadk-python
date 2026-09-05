import type { TOptions } from "i18next";

import { i18n } from "../i18n/runtime";
import enWorkspaceTools from "../i18n/resources/en-US/workspaceTools.json";
import zhWorkspaceTools from "../i18n/resources/zh-CN/workspaceTools.json";

if (!i18n.hasResourceBundle("en-US", "workspaceTools")) {
  i18n.addResourceBundle("en-US", "workspaceTools", enWorkspaceTools, true, true);
}
if (!i18n.hasResourceBundle("zh-CN", "workspaceTools")) {
  i18n.addResourceBundle("zh-CN", "workspaceTools", zhWorkspaceTools, true, true);
}

/** Translate non-React workspace copy at call time so locale changes apply immediately. */
export function workspaceToolsT(key: string, options: TOptions = {}): string {
  return i18n.t(key, { ...options, ns: "workspaceTools" });
}
