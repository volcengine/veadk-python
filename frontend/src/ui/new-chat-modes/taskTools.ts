import type { NewChatTask } from "./types";

export const NEW_CHAT_TASK_TOOLS: Readonly<Record<NewChatTask, readonly string[]>> = {
  ppt: ["ppt_generate"],
  image: ["image_generate"],
  video: ["video_generate"],
};

export const NEW_CHAT_TASK_OPTIONAL_TOOLS: Readonly<Record<NewChatTask, readonly string[]>> = {
  ppt: [],
  image: [],
  video: ["video_task_query"],
};
