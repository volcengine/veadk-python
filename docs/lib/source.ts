import { createElement } from 'react';
import { icons } from 'lucide-react';
import { docs } from 'collections/server';
import { loader } from 'fumadocs-core/source';
import { statusBadgesPlugin } from 'fumadocs-core/source/plugins/status-badges';
import { i18n } from './i18n';
import { docsContentRoute, docsImageRoute, docsRoute } from './shared';

// See https://fumadocs.dev/docs/headless/source-api for more info
export const source = loader({
  baseUrl: docsRoute,
  i18n,
  // Resolve `icon` strings in meta.json (root tabs, groups) to lucide icons.
  icon(name) {
    if (name && name in icons) {
      return createElement(icons[name as keyof typeof icons]);
    }
  },
  source: docs.toFumadocsSource(),
  // Render a sidebar badge for pages whose frontmatter sets `status` (e.g. `status: new`).
  plugins: [
    statusBadgesPlugin({
      renderBadge: (status) =>
        createElement(
          'span',
          {
            className:
              'ms-auto shrink-0 rounded-full bg-fd-primary/10 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-fd-primary',
          },
          status,
        ),
    }),
  ],
});

export function getPageImage(page: (typeof source)['$inferPage']) {
  const segments = [...page.slugs, 'image.png'];

  return {
    segments,
    url: `${docsImageRoute}/${segments.join('/')}`,
  };
}

export function getPageMarkdownUrl(page: (typeof source)['$inferPage']) {
  const segments = [...page.slugs, 'content.md'];

  return {
    segments,
    url: `${docsContentRoute}/${segments.join('/')}`,
  };
}

export async function getLLMText(page: (typeof source)['$inferPage']) {
  const processed = await page.data.getText('processed');

  return `# ${page.data.title} (${page.url})

${processed}`;
}
