import { uiTranslations } from 'fumadocs-ui/i18n';
import { i18n } from './i18n';

// Translations for the Fumadocs UI chrome (search box, TOC, theme toggle, ...)
// plus the `displayName` used by the language switcher.
// English (`en`) inherits the built-in defaults from `uiTranslations()`.
export const translations = i18n
  .translations()
  .extend(uiTranslations())
  .add('ui', {
    en: {
      displayName: 'English',
    },
    cn: {
      displayName: '中文',
      search: '搜索文档',
      searchNoResult: '没有找到结果',
      toc: '本页导航',
      tocNoHeadings: '本页无标题',
      lastUpdate: '最后更新于',
      chooseLanguage: '选择语言',
      nextPage: '下一页',
      previousPage: '上一页',
      chooseTheme: '主题',
      editOnGithub: '在 GitHub 上编辑',
      // page action buttons (Copy Markdown / View Options popover)
      pageActionsCopyMarkdown: '复制 Markdown',
      pageActionsOpen: '打开方式',
      pageActionsViewMarkdown: '查看 Markdown',
      pageActionsOpenGitHub: '在 GitHub 上打开',
      pageActionsOpenInLLMPrompt: '在 LLM 中打开',
      pageActionsOpenChatGPT: '在 ChatGPT 中打开',
      pageActionsOpenClaude: '在 Claude 中打开',
      pageActionsOpenCursor: '在 Cursor 中打开',
      pageActionsOpenScira: '在 Scira 中打开',
    },
  });
