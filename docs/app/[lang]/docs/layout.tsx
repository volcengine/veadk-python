import type { ReactNode } from 'react';
import { source } from '@/lib/source';
import { DocsLayout } from 'fumadocs-ui/layouts/docs';
import { baseOptions } from '@/lib/layout.shared';
import { BookMarked, LayoutGrid, Terminal } from 'lucide-react';

export default async function Layout({
  params,
  children,
}: {
  params: Promise<{ lang: string }>;
  children: ReactNode;
}) {
  const { lang } = await params;
  const zh = lang === 'cn';

  // Root dropdown (sidebar RootToggle): Framework / CLI / Reference.
  const tabs = [
    {
      title: zh ? '框架' : 'Framework',
      description: zh ? 'SDK 与核心概念' : 'SDK & core concepts',
      url: `/${lang}/docs/framework`,
      icon: <LayoutGrid className="size-full" />,
    },
    {
      title: zh ? '命令行工具' : 'CLI',
      description: zh ? '命令行参考' : 'Command-line reference',
      url: `/${lang}/docs/cli`,
      icon: <Terminal className="size-full" />,
    },
    {
      title: zh ? '参考' : 'Reference',
      description: zh ? 'API · 贡献 · 许可' : 'API · Contributing · License',
      url: `/${lang}/docs/references`,
      icon: <BookMarked className="size-full" />,
    },
  ];

  return (
    <DocsLayout
      tree={source.getPageTree(lang)}
      tabMode="auto"
      tabs={tabs}
      {...baseOptions(lang)}
    >
      {children}
    </DocsLayout>
  );
}
