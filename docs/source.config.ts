import { defineConfig, defineDocs } from 'fumadocs-mdx/config';
import { metaSchema, pageSchema } from 'fumadocs-core/source/schema';
import { remarkMdxMermaid } from 'fumadocs-core/mdx-plugins';
import { visit } from 'unist-util-visit';

// You can customize Zod schemas for frontmatter and `meta.json` here
// see https://fumadocs.dev/docs/mdx/collections
export const docs = defineDocs({
  dir: 'content/docs',
  docs: {
    schema: pageSchema,
    postprocess: {
      includeProcessedMarkdown: true,
    },
  },
  meta: {
    schema: metaSchema,
  },
});

// GitHub Pages serves under a base path (e.g. /veadk-python). Next prefixes
// `_next/` assets and next/link hrefs automatically, but NOT raw <img src>
// from markdown. Prepend the base path to absolute image sources at build time.
const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH || '';

function rehypeBasePathImages() {
  // biome-ignore lint/suspicious/noExplicitAny: hast tree nodes
  return (tree: any) => {
    if (!BASE_PATH) return;
    // biome-ignore lint/suspicious/noExplicitAny: hast element node
    visit(tree, 'element', (node: any) => {
      const src = node.properties?.src;
      if (
        node.tagName === 'img' &&
        typeof src === 'string' &&
        src.startsWith('/') &&
        !src.startsWith(`${BASE_PATH}/`)
      ) {
        node.properties.src = `${BASE_PATH}${src}`;
      }
    });
  };
}

export default defineConfig({
  mdxOptions: {
    // Append to (not replace) Fumadocs' default plugin set.
    remarkPlugins: (v) => [...v, remarkMdxMermaid],
    rehypePlugins: (v) => [...v, rehypeBasePathImages],
  },
});
