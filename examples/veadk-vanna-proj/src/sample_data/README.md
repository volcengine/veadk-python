# B2B Data Agent 样例问题集

本文档列出了10个典型的 B2B 业务场景问题，对比了使用本 Agent 前后的效果差异。为了展示 Agent 的高级分析能力，我们特别设计了多个需要结合 SQL 和 Python 脚本解决的复杂问题（Text-to-Python）。

## 场景 1: 客户名称模糊匹配

### 1. 小米客户近3个月的收入

**Bad Case (原逻辑):**
可能直接模糊匹配 `name LIKE '%小米%'`，导致将“宁波小米粒鞋业”的收入也计算在内，或者因为存在多个匹配项而报错。

**Expected (Agent 逻辑):**

1. **Thought**: 识别到“小米”可能存在歧义，优先查找 `customer` 表中 `is_main_customer=1` 的记录。
2. **Action**: `run_sql("SELECT customer_id FROM customer WHERE (name LIKE '%小米%' OR short_name = '小米') AND is_main_customer = 1")` -> 找到 ACC-001。
3. **Action**: `run_sql("SELECT sum(amount) FROM revenue WHERE customer_id = 'ACC-001' AND year_month >= ...")`
4. **Result**: 准确返回小米科技（主客户）的收入数据，排除干扰项。

### 2. 网易2025年的总收入

**Bad Case (原逻辑):**
可能无法区分“网易”是指集团还是某个子公司，或者漏掉某些月份的数据。

**Expected (Agent 逻辑):**

1. **Thought**: 查找“网易”对应的主客户 ID。
2. **Action**: 锁定 ACC-005 (网易（杭州）网络有限公司)。
3. **Action**: 聚合查询 2025 全年的 `revenue`。
4. **Result**: 返回网易 2025 年度的准确总收入。

## 场景 2: 复杂趋势与预测 (SQL + Python)

### 3. 小米最近的用量趋势（含可视化）

**Bad Case (原逻辑):**
仅返回一堆数字或 SQL 查询结果，用户无法直观理解趋势。

**Expected (Agent 逻辑):**

1. **Thought**: 用户需要“趋势”，意味着需要日粒度数据并生成图表。
2. **Action**: `run_sql` 查询 `resource_usage` 表获取近 30 天的 `usage_date` 和 `quantity`，保存为 CSV。
3. **Action**: 调用 `visualize_data` 工具，传入 CSV 数据生成折线图。
4. **Result**: 返回一张清晰的用量趋势折线图。

### 4. 预测小米下个月的用量增长

**Bad Case (原逻辑):**
无法处理“预测”请求，因为 SQL 无法进行时间序列预测。

**Expected (Agent 逻辑):**

1. **Thought**: 这是一个预测任务，需要提取历史数据并使用 Python 进行线性回归或简单外推。
2. **Action**: `run_sql` 导出小米过去 3 个月的用量数据到 CSV。
3. **Action**: `generate_document` 编写 Python 脚本：读取 CSV，使用 `scikit-learn` 或 `numpy` 拟合趋势线，预测下月总量。
4. **Action**: `run_python_file` 执行预测脚本。
5. **Result**: "基于过去3个月的增长趋势，预测小米下个月的用量约为 35,000,000 Tokens，环比增长 5%。"

## 场景 3: 复杂逻辑与异常检测 (SQL + Python)

### 5. 帮我分析一下小米的云资源使用异常

**Bad Case (原逻辑):**
不知道什么是“异常”，直接报错或返回空。

**Expected (Agent 逻辑):**

1. **Thought**: 这是一个复杂分析任务。需要定义异常（如 3-Sigma 准则或 IQR）。
2. **Action**: `run_sql` 获取小米的历史日用量数据。
3. **Action**: `generate_document` 编写 Python 脚本：计算均值和标准差，识别超过 `mean + 3*std` 的日期。
4. **Action**: `run_python_file` 执行脚本。
5. **Action**: `generate_document` 生成分析报告 `xiaomi_anomaly_analysis.md`。
6. **Result**: "检测到 15天前 用量激增，达到 3,000,000，超过平均值 3 倍，属于异常波动。详细分析请见报告：`xiaomi_anomaly_analysis.md`"

### 6. 计算网易 DeepSeek 调用的周环比增长率

**Bad Case (原逻辑):**
SQL 计算周环比（WoW）非常复杂，容易出错。

**Expected (Agent 逻辑):**

1. **Thought**: 使用 Python pandas 处理时间序列更高效。
2. **Action**: `run_sql` 获取网易 DeepSeek 的每日用量数据。
3. **Action**: `generate_document` 编写 Python 脚本：`df.resample('W').sum().pct_change()` 计算周环比。
4. **Action**: `run_python_file` 执行脚本。
5. **Result**: "上周对比上上周，DeepSeek 调用量增长了 15.2%。"

## 场景 4: 跨表关联与业务洞察

### 7. 哪些欠费客户还在大量使用资源？（风险预警）

**Bad Case (原逻辑):**
无法同时关联欠费状态和近期用量，或者 SQL 逻辑过于复杂导致超时。

**Expected (Agent 逻辑):**

1. **Thought**: 需要找到 `arrears_amount > 0` 的客户，并检查其最近 3 天的 `resource_usage` 是否超过阈值。
2. **Action**: `run_sql` 联查 `customer`, `account_credit`, `resource_usage`，筛选欠费且近3天有用量的客户。
3. **Result**: "警告：分期乐（ACC-004）当前欠费 74.8万元，但最近3天仍消耗了 500 GPU Hours，建议立即介入。"

### 8. 谁是 DeepSeek 模型最大的使用方？

**Bad Case (原逻辑):**
无法将“DeepSeek”映射到 `model_or_card` 字段，或者不知道如何定义“最大使用方”。

**Expected (Agent 逻辑):**

1. **Thought**: “DeepSeek” 对应 `resource_usage` 表中的 `model_or_card`。
2. **Action**: 按 `customer_id` 分组统计 `quantity` 总和，按降序排列，取第一名。
3. **Result**: "网易（ACC-005）是 DeepSeek 模型的最大使用方，累计消耗 Token 超过 6000 万。"

## 场景 5: 综合报告生成 (SQL + Python)

### 9. 生成一份小米的月度消费报告

**Bad Case (原逻辑):**
只能返回零散的数据，无法生成结构化报告。

**Expected (Agent 逻辑):**

1. **Thought**: 报告需要包含收入、用量、趋势图和关键指标。这是一个多步任务。
2. **Action 1**: `run_sql` 查询当月收入和用量总和。
3. **Action 2**: `run_sql` 查询日用量趋势，并调用 `visualize_data` 生成图表。
4. **Action 3**: `generate_document` 将上述数据和图表路径整合成 Markdown 格式的报告 `xiaomi_monthly_report.md`，报告中必须包含各步骤的详细分析。
5. **Result**: "报告已生成：`xiaomi_monthly_report.md`。摘要：小米本月总消费 xxx 元，趋势平稳，无异常波动。"

### 10. 今天的最新收入数据出来了吗？

**Bad Case (原逻辑):**
尝试查询数据库，返回空结果，用户不知道是没数据还是没发生交易。

**Expected (Agent 逻辑):**

1. **Thought**: 命中 Instruction 中的 "Missing Data" 策略。
2. **Result**: 直接回答：“根据数据库设计，`revenue` 表按月更新，`resource_usage` 按日更新。今天的实时收入数据尚未生成，通常需要在次月出账后查看。”
