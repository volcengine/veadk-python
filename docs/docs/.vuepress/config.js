import { viteBundler } from '@vuepress/bundler-vite'
import { defaultTheme } from '@vuepress/theme-default'
import { defineUserConfig } from 'vuepress'

export default defineUserConfig({
  lang: 'en-US',

  title: 'Volcengine Agent Development Kit',
  description: '火山引擎智能体开发框架',

  theme: defaultTheme({
    logo: '/images/VEADK.png',

    navbar: ['/', '/introduction'],

    sidebar: ['introduction', 'installation', 'get-started', 'agent', 'memory', 'tool', 'knowledgebase', 'tracing', 'evaluation', 'deploy', 'cli', 'veadk-studio']
  }),

  bundler: viteBundler(),

  base: '/veadk-python/', // GitHub Pages required
})
