---
seo:
  title: 火山引擎 Agent 开发框架
  description: 为 Agent 开发提供开发、部署、观测等全流程支持。
---

::u-page-hero
#title
Volcengine Agent Development Kit

#description
火山引擎智能体开发框架为 Agent 应用构建提供开发、部署、观测等全流程支持

提供快速、便捷、开放兼容的智能体云原生解决方案

#links
  :::u-button
  ---
  color: neutral
  size: xl
  to: /introduction/overview
  trailing-icon: i-lucide-arrow-right
  ---
  官方文档
  :::

  :::u-button
  ---
  color: neutral
  size: xl
  target: _blank
  to: https://github.com/volcengine/veadk-python/blob/main/veadk_tutorial.ipynb
  icon: i-lucide-book-text
  variant: outline
  ---
  交互式教程
  :::

  :::u-button
  ---
  color: neutral
  icon: simple-icons-github
  size: xl
  target: _blank
  to: https://github.com/volcengine/veadk-python
  variant: outline
  ---
  GitHub
  :::
::

::u-page-section
#title
VeADK 特性

#features
  :::u-page-feature
  ---
  icon: i-lucide-sparkles
  target: _blank
  to: /tools/builtin-tools
  ---
  #title
  更丰富的[内置工具]{.text-primary}
  
  #description
  侧重头条、抖音搜索的WEB_SEARCH等；MCP工具，例如飞书Lark、数据湖LAS、优解PromptPilot等
  :::

  :::u-page-feature
  ---
  icon: i-lucide-sparkles
  target: _blank
  to: https://ui.nuxt.com/
  ---
  #title
  更灵活的[功能扩展]{.text-primary}
  
  #description
  提供Agent各类组件的基础实现，通过插件方式灵活扩展。
  :::

  :::u-page-feature
  ---
  icon: i-lucide-sparkles
  target: _blank
  to: /observation/tracing
  ---
  #title
  更完备的[观测评测]{.text-primary}
  
  #description
  运行时数据通过OpenTelemetry协议无缝衔接APMPlus、Cozeloop、TLS；运行时数据生成测试数据集文件，可直接在本地和Cozeloop中进行评估测试。
  :::

::
