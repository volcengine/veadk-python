import { defineI18n } from 'fumadocs-core/i18n';

// Chinese is the default language (unsuffixed files: `page.mdx`).
// English pages use the `.en.mdx` suffix.
export const i18n = defineI18n({
  defaultLanguage: 'cn',
  languages: ['cn', 'en'],
});
