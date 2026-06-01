export const appName = 'Volcengine ADK';

// GitHub Pages project sites are served under a sub-path (e.g. /veadk-python).
// Set NEXT_PUBLIC_BASE_PATH at build time for production; empty in local dev.
export const basePath = process.env.NEXT_PUBLIC_BASE_PATH ?? '';

/** Prefix a /public asset with the deployment base path. */
export function assetPath(path: string): string {
  return `${basePath}${path}`;
}

export const docsRoute = '/docs';
export const docsImageRoute = '/og/docs';
export const docsContentRoute = '/llms.mdx/docs';

export const gitConfig = {
  user: 'volcengine',
  repo: 'veadk-python',
  branch: 'main',
};
