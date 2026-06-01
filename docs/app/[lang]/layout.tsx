import type { ReactNode } from 'react';
import { RootProvider } from 'fumadocs-ui/provider/next';
import { i18nProvider } from 'fumadocs-ui/i18n';
import SearchDialog from '@/components/search';
import { i18n } from '@/lib/i18n';
import { translations } from '@/lib/i18n-ui';
import { HtmlLang } from '@/components/html-lang';

export function generateStaticParams() {
  return i18n.languages.map((lang) => ({ lang }));
}

export default async function LangLayout({
  params,
  children,
}: {
  params: Promise<{ lang: string }>;
  children: ReactNode;
}) {
  const { lang } = await params;

  return (
    <RootProvider i18n={i18nProvider(translations, lang)} search={{ SearchDialog }}>
      <HtmlLang lang={lang} />
      {children}
    </RootProvider>
  );
}
