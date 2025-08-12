# 介绍

## 关于VeADK

**VeADK（Volcengine Agent Development Kit）** 是由[火山引擎](https://www.volcengine.com/)推出的一套面向智能体（Agent）开发的全流程框架，旨在为开发者提供一套面向智能体构建、云端部署、评测与优化的全流程开发框架。

VeADK 相较于现有的智能体开发框架，具备与火山引擎产品体系深度融合的优势，帮助开发者更高效地构建企业级 AI 智能体应用。

## VeADK 核心优势

### 更快速的企业级部署

- 通过云部署项目模板支持 CloudEngine 的一键部署和发布能力
- 支持 [VeFaaS](https://www.volcengine.com/product/vefaas) 与[火山引擎APIG](https://www.volcengine.com/product/apig)，实现高可用、高弹性的服务托管
- 提供简易的 CLI 工具与编程化发布

### 更安全的企业级部署

- 支持 Identity 管理
- 支持 API Key 服务鉴权与 OAuth2 用户鉴权能力

### 更完备的可观测性和评估能力

- 运行时数据无缝衔接 [APMPlus](https://www.volcengine.com/product/apmplus)、[CozeLoop](https://www.coze.cn/loop), [TLS](https://www.volcengine.com/product/tls) 等云观测平台，提供可视化监控
- 运行时数据直接落地为测试数据集文件， 支持离线和在线的评估能力

### 更丰富的内置工具

- 内置头条、抖音搜索工具，实现实时信息获取与内容聚合
- 集成飞书 Lark（协同办公）、[LAS（AI 数据湖服务）](https://www.volcengine.com/product/las)等工具，增强 Agent 实用性

### 更灵活的功能扩展

- 提供 Agent 构建所需核心组件的基础实现，支持开发者根据需求灵活组合与扩展

### 更强大的知识管理

- 支持连接火山引擎各类现有数据库，包括[关系型数据库](https://www.volcengine.com/product/rds-mysql)、[缓存数据库](https://www.volcengine.com/product/redis)等
- 集成 [Viking DB](https://www.volcengine.com/docs/84313/1254437) 等火山引擎云知识库，实现知识的高效存储、检索与更新

### 更友好的最佳实践

- 提供贴近实际工业场景的各类开发和部署用例，涵盖数据库访问、数据湖读写、复杂任务编排等多样场景。
- 提供可直接复用的代码模板与配置示例，帮助开发者快速上手并解决实际业务问题。

## 整体方案

在 VeADK 中，智能体的构建与生命周期的管理围绕`Agent`，`Runner`等核心组件进行：

### Agent

`Agent`是智能体的主体，基于大模型处理用户输入，调用不同的组件及各类工具，最终返回给用户结果。

### Runner

`Runner`是智能体的执行器，负责智能体运行时的生命周期管理。

在多租场景下，`Runner`通过三个属性来确定资源空间：

- `app_name`：应用名称
- `user_id`：用户ID
- `session_id`：某个用户某次会话的ID

VeADK 的组件会利用这三个属性来构建某些数据的索引，例如知识库组件将会根据`app_name`与`user_id`来进行空间数据的索引，实现多租场景下数据空间的安全隔离。

## Milestone

| 时间节点 | 事件 |
| --- | --- |
| 2025/08/01 | V0.1.0版本发布 |
