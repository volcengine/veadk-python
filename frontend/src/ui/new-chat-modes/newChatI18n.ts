import type { TOptions } from "i18next";

import { i18n } from "../../i18n/runtime";
import enNewChat from "../../i18n/resources/en-US/newChat.json";
import zhNewChat from "../../i18n/resources/zh-CN/newChat.json";

if (!i18n.hasResourceBundle("en-US", "newChat")) {
  i18n.addResourceBundle("en-US", "newChat", enNewChat, true, true);
}
if (!i18n.hasResourceBundle("zh-CN", "newChat")) {
  i18n.addResourceBundle("zh-CN", "newChat", zhNewChat, true, true);
}

/** Translate non-React new-chat content at call time so language changes apply immediately. */
export function newChatT(key: string, options: TOptions = {}): string {
  return i18n.t(key, { ...options, ns: "newChat" });
}
