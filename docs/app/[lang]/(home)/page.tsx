import Link from 'next/link';

const copy = {
  cn: {
    title: 'Volcengine Agent Development Kit',
    subtitle: '火山引擎智能体开发套件',
    desc: '构建、部署、观测、评测企业级 AI 智能体的一站式云原生框架。',
    cta: '阅读文档',
  },
  en: {
    title: 'Volcengine Agent Development Kit',
    subtitle: 'Build production-ready AI agents',
    desc: 'A cloud-native framework to build, deploy, observe, and evaluate enterprise-grade AI agents.',
    cta: 'Read the docs',
  },
} as const;

export default async function HomePage({ params }: { params: Promise<{ lang: string }> }) {
  const { lang } = await params;
  const t = copy[lang as keyof typeof copy] ?? copy.cn;

  return (
    <main className="flex flex-1 flex-col items-center justify-center text-center px-4 py-24">
      <h1 className="text-4xl md:text-5xl font-bold mb-3 bg-gradient-to-r from-blue-500 to-cyan-400 bg-clip-text text-transparent">
        {t.title}
      </h1>
      <p className="text-lg text-fd-muted-foreground mb-2">{t.subtitle}</p>
      <p className="max-w-2xl text-fd-muted-foreground mb-8">{t.desc}</p>
      <Link
        href={`/${lang}/docs/framework`}
        className="rounded-full bg-fd-primary text-fd-primary-foreground px-6 py-2.5 font-medium hover:opacity-90 transition"
      >
        {t.cta}
      </Link>
    </main>
  );
}
