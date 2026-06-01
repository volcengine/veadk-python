'use client';

import { useEffect } from 'react';

/** Keeps <html lang> in sync with the active locale (root layout is static). */
export function HtmlLang({ lang }: { lang: string }) {
  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  return null;
}
