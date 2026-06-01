import { source } from '@/lib/source';
import { createFromSource } from 'fumadocs-core/search/server';
import { createTokenizer } from '@orama/tokenizers/mandarin';

export const revalidate = false;

// Static (build-time) search index, one per locale.
// Chinese uses Mandarin word segmentation so CJK terms are indexed correctly.
export const { staticGET: GET } = createFromSource(source, {
  localeMap: {
    cn: {
      components: { tokenizer: createTokenizer() },
      search: { threshold: 0, tolerance: 0 },
    },
    en: { language: 'english' },
  },
});
