import type { TOptions } from "i18next";

import { i18n } from "../../i18n/runtime";
import enSkills from "../../i18n/resources/en-US/skills.json";
import zhSkills from "../../i18n/resources/zh-CN/skills.json";

if (!i18n.hasResourceBundle("en-US", "skills")) {
  i18n.addResourceBundle("en-US", "skills", enSkills, true, true);
}
if (!i18n.hasResourceBundle("zh-CN", "skills")) {
  i18n.addResourceBundle("zh-CN", "skills", zhSkills, true, true);
}

/** Translate non-React Skill copy at call time so locale changes apply immediately. */
export function skillT(key: string, options: TOptions = {}): string {
  return i18n.t(key, { ...options, ns: "skills" });
}
