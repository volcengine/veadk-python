<!--
 * @Author: haoxingjun
 * @Date: 2026-01-27 13:10:41
 * @Email: haoxingjun@bytedance.com
 * @LastEditors: haoxingjun
 * @LastEditTime: 2026-01-27 13:11:01
 * @Description: file information
 * @Company: ByteDance
-->
# Intent Tool

本模块提供基于意图识别的股票因子检索能力。

## 快速开始

```python
from veadk.tools.builtin_tools.intent_tool.governance import IntentGovernor
from veadk.tools.builtin_tools.intent_tool.retriever import StockRetriever

# 1. 初始化
governor = IntentGovernor()
# 指定 VikingDB 中的 Collection 名称
retriever = StockRetriever(collection_name="stock_factors_kb")

# 2. 用户提问
query = "前2月销额累计值同比稳增的半导体股"

# 3. 意图识别
intent_result = governor.process(query)

if intent_result["status"] == "PROCEED":
    # 4. 执行检索
    context_data = retriever.retrieve(intent_result["payload"])
    
    print("检索到的上下文:")
    print(context_data["context_str"])
    
    # 5. (可选) 发送给 LLM 生成最终回答
    # llm.chat(query, context=context_data["context_str"])
else:
    print("需澄清:", intent_result["message"])
```

## ⚙️ 关键配置说明

### IntentGovernor
*   **默认值注入**: 在 `process` 方法中，针对 `industry` 和 `time_window` 为空的情况做了默认值处理（全市场/最新）。
*   **指标清洗**: 内置 `_clean_indicator` (内部逻辑) 函数，防止“半导体”同时出现在行业和指标列表中。

### StockRetriever
*   **search_knowledge**: 调用 VikingDB 的标准接口。
*   **Limit**: 默认每个指标检索 `TOP_K=1` 条最相关定义（因为使用了强时间约束，召回精度较高）。

## ❓ 常见问题

**Q: 为什么检索结果里还是有“前3月”的数据？**
A: 请检查 `GoalFrame` 中的 `time_window` 是否被正确提取。如果提取正确，可能需要调整 VikingDB 的 Embedding 模型或增加 Rerank 步骤。

**Q: 离线编译报错 "Reasoning mismatch"？**
A: 这是因为 LLM 的思维链与生成的 JSON 不一致。请检查 `builder.py` 中的 Labeler Prompt，确保约束条件明确。我们已在最新版中放宽了校验逻辑。

**Q: 如何更新意图识别能力？**
A: 只需在 CSV 中添加新的典型 Case，重新运行 `builder.py`，然后重启在线服务即可。无需修改 Python 代码。
