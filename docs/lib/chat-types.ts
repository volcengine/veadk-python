import type { Tool, UIMessage } from 'ai';

// Shared Ask-AI chat types. Kept out of the API route so the route can be
// excluded from the static export build (GitHub Pages) without breaking the
// chat UI, which only needs the types.
export type ChatUIMessage = UIMessage<
  never,
  {
    client: {
      location: string;
    };
  }
>;

export type SearchTool = Tool;
