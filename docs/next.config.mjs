import { createMDX } from 'fumadocs-mdx/next';

const withMDX = createMDX();

// For GitHub Pages project sites, set NEXT_PUBLIC_BASE_PATH=/veadk-python at
// build time. Left empty for local dev so the site is served from `/`.
const basePath = process.env.NEXT_PUBLIC_BASE_PATH || '';

// Static export (GitHub Pages) is opt-in via NEXT_STATIC_EXPORT=1, because
// `output: 'export'` is incompatible with the dev-only /api/chat POST route
// and with middleware. A plain `next build` compiles & verifies every page.
const staticExport = process.env.NEXT_STATIC_EXPORT === '1';

/** @type {import('next').NextConfig} */
const config = {
  ...(staticExport ? { output: 'export' } : {}),
  reactStrictMode: true,
  trailingSlash: true,
  turbopack: {
    root: import.meta.dirname,
  },
  images: {
    unoptimized: true,
  },
  ...(basePath ? { basePath, assetPrefix: basePath } : {}),
};

export default withMDX(config);
