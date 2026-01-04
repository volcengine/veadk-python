---
title: 长期记忆
---

本文档介绍 VeADK 系统中的**长期记忆（Long-term Memory）**概念及应用。长期记忆用于跨会话、跨时间保存重要信息，以增强智能体在连续交互中的一致性和智能性。

**定义**：长期记忆是智能体用于存储超出单次会话范围的重要信息的机制，可以包含用户偏好、任务历史、知识要点或长期状态。

**为什么重要**：

- 支持跨会话的连续对话体验；
- 允许智能体在多次交互中保留学习成果和用户特定信息；
- 减少重复询问，提升用户满意度和效率；
- 支持长期策略优化，例如个性化推荐或任务追踪。

智能体用户需要长期记忆来实现更智能、个性化和可持续的交互体验，尤其在多次会话或复杂任务场景中显著提高系统实用性。

## 支持后端类型

| 类别         | 说明                                                       |
| :----------- | :--------------------------------------------------------- |
| `local`      | 内存跨 Session 记忆，程序结束后即清空                      |
| `opensearch` | 使用 OpenSearch 作为长期记忆存储，可实现持久化和检索       |
| `redis`      | 使用 Redis 作为长期记忆存储，Redis 需要支持 Rediseach 功能 |
| `viking`     | 使用 VikingDB 记忆库产品作为长期记忆存储                   |
| `viking_mem` | 已废弃，设置后将会自动转为 `viking`                        |

## 初始化方法

在使用长期记忆之前，需要实例化 LongTermMemory 对象并指定后端类型。以下代码展示了如何初始化基于 VikingDB 的长期记忆模块，并将其绑定到 Agent：
=== "Python"

    ```python
    from veadk import Agent, Runner
    from veadk.memory import LongTermMemory
    
    # 初始化长期记忆
    # backend="viking" 指定使用 VikingDB
    # app_name 和 user_id 用于数据隔离
    long_term_memory = LongTermMemory(
        backend="viking", app_name="local_memory_demo", user_id="demo_user"
    )
    
    # 将长期记忆绑定到 Agent
    root_agent = Agent(
        name="minimal_agent",
        instruction="Acknowledge user input and maintain simple conversation.",
        long_term_memory=long_term_memory,  # 长期记忆实例
    )
    
    runner = Runner(agent=root_agent)
    ```

=== "Golang"

    ```go
    package main

    import (
        "log"
    
        veagent "github.com/volcengine/veadk-go/agent/llmagent"
        "github.com/volcengine/veadk-go/common"
        vem "github.com/volcengine/veadk-go/memory"
        "github.com/volcengine/veadk-go/tool/builtin_tools"
        "github.com/volcengine/veadk-go/utils"
        "google.golang.org/adk/runner"
        "google.golang.org/adk/session"
        "google.golang.org/adk/tool"
    )
    
    func main() {
        appName := "ve_agent"
        memorySearchTool, err := builtin_tools.LoadLongMemoryTool()
        if err != nil {
            log.Fatal(err)
            return
        }
    
        cfg := &veagent.Config{
            ModelName:    common.DEFAULT_MODEL_AGENT_NAME,
            ModelAPIBase: common.DEFAULT_MODEL_AGENT_API_BASE,
            ModelAPIKey:  utils.GetEnvWithDefault(common.MODEL_AGENT_API_KEY),
        }
        cfg.Name = "MemoryRecallAgent"
        cfg.Instruction = "Answer the user's question. Use the 'search_past_conversations' tools if the answer might be in past conversations."
    
        cfg.Tools = []tool.Tool{memorySearchTool}
    
        memorySearchAgent, err := veagent.New(cfg)
        if err != nil {
            log.Printf("NewLLMAgent failed: %v", err)
            return
        }
    
        sessionService := session.InMemoryService()
        memoryService, err := vem.NewLongTermMemoryService(vem.BackendLongTermViking, nil)
        if err != nil {
            log.Printf("NewLongTermMemoryService failed: %v", err)
            return
        }
    
        runner, err := runner.New(runner.Config{
            AppName:        appName,
            Agent:          memorySearchAgent,
            SessionService: sessionService,
            MemoryService:  memoryService,
        })
    }

    ```

## 记忆管理

### 添加会话到长期记忆

在会话（Session）结束或达到特定节点时，需要显式调用 add_session_to_memory 将会话数据持久化。对于 Viking 后端，这一步会触发数据的向量化处理。

=== "Python"

    ```python
    # 假设 runner1 已经完成了一次对话
    completed_session = await runner.session_service.get_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=session_id
    )
    
    # 将完整会话归档到长期记忆
    root_agent.long_term_memory.add_session_to_memory(completed_session)
    ```
=== "Golang"

    ```go
    appName := "ve_agent"
    userID := "user1111"
    sessionService := session.InMemoryService()
    s, err := sessionService.Create(ctx, &session.CreateRequest{
		AppName:   appName,
		UserID:    userID,
		SessionID: sessionID,
	})

	resp, err := sessionService.Get(ctx, &session.GetRequest{AppName: s.Session.AppName(), UserID: s.Session.UserID(), SessionID: s.Session.ID()})
	if err != nil {
		log.Fatalf("Failed to get completed session: %v", err)
	}
	if err := memoryService.AddSession(ctx, resp.Session); err != nil {
		log.Fatalf("Failed to add session to memory: %v", err)
	}
    ```

### 检索长期记忆

除了 Agent 在运行时自动检索外，开发者也可以调用 search_memory 接口直接进行语义搜索，用于调试或构建自定义的 RAG（检索增强生成）应用。

=== "Python"

    ```python
    query = "favorite project"
    res = await root_agent.long_term_memory.search_memory(
        app_name=APP_NAME,
        user_id=USER_ID,
        query=query
    )
    
    # 打印检索结果
    print(res)
    ```

=== "Golang"

    ```go
    query := "favorite project"
	memoryService.Search(ctx, &memory.SearchRequest{
		Query:   query,
		UserID:  userID,
		AppName: appName,
	})
    ```


## 使用长期记忆进行会话管理

在单租户场景中，长期记忆可用于管理同一用户的多次会话，确保智能体能够：

- 在新会话中记忆上一次交互内容；
- 根据历史信息做出个性化响应；
- 在多轮任务中累积进度信息或中间结果。

### 准备工作

- 为每个用户分配唯一标识（user_id 或 session_owner_id）；
- 设计长期记忆数据结构以支持多会话信息保存；
- 配合短期记忆使用，实现会话内上下文快速访问。

### 示例

以下示例演示了一个完整的流程：Runner1 告诉 Agent 一个信息（"My favorite project is Project Alpha"），将会话存入记忆，然后创建一个全新的 Runner2，验证其能否回答相关问题。

=== "Python"

    ```python
    # --- 阶段 1: 写入记忆 ---
    # Runner1 告诉 Agent 信息
    runner1_question = "My favorite project is Project Alpha."
    user_input = types.Content(role="user", parts=[types.Part(text=runner1_question)])
    
    async for event in runner1.run_async(user_id=USER_ID, session_id=session_id, new_message=user_input):
        pass # 处理 Runner1 的响应
    
    # 关键步骤：将会话归档到 VikingDB
    completed_session = await runner1.session_service.get_session(app_name=APP_NAME, user_id=USER_ID, session_id=session_id)
    root_agent.long_term_memory.add_session_to_memory(completed_session)
    
    # --- 阶段 2: 跨会话读取 ---
    # 初始化 Runner2 (模拟新的会话或后续交互)
    runner2 = Runner(
        agent=root_agent,
        app_name=APP_NAME,
        user_id=USER_ID,
        short_term_memory=short_term_memory
    )
    
    # Runner2 提问，依赖长期记忆回答
    qa_question = "favorite project"
    qa_content = types.Content(role="user", parts=[types.Part(text=qa_question)])
    
    final_text = None
    async for event in runner2.run_async(user_id=USER_ID, session_id=session_id, new_message=qa_content):
        if event.is_final_response():
             final_text = event.content.parts[0].text.strip()
    ```

=== "Golang"
    
    ```go
    package main

    import (
        "context"
        "log"
        "strings"
    
        veagent "github.com/volcengine/veadk-go/agent/llmagent"
        "github.com/volcengine/veadk-go/common"
        vem "github.com/volcengine/veadk-go/memory"
        "github.com/volcengine/veadk-go/tool/builtin_tools"
        "github.com/volcengine/veadk-go/utils"
        "google.golang.org/adk/agent"
        "google.golang.org/adk/agent/llmagent"
        "google.golang.org/adk/runner"
        "google.golang.org/adk/session"
        "google.golang.org/adk/tool"
        "google.golang.org/genai"
    )
    
    func main() {
        ctx := context.Background()
        appName := "ve_agent"
        userID := "user1111"
    
        // Define a tools that can search memory.
        memorySearchTool, err := builtin_tools.LoadLongMemoryTool()
        if err != nil {
            log.Fatal(err)
            return
        }
    
        infoCaptureAgent, err := veagent.New(&veagent.Config{
            Config: llmagent.Config{
                Name:        "InfoCaptureAgent",
                Instruction: "Acknowledge the user's statement.",
            },
            ModelName:    common.DEFAULT_MODEL_AGENT_NAME,
            ModelAPIBase: common.DEFAULT_MODEL_AGENT_API_BASE,
            ModelAPIKey:  utils.GetEnvWithDefault(common.MODEL_AGENT_API_KEY),
        })
        if err != nil {
            log.Printf("NewLLMAgent failed: %v", err)
            return
        }
    
        cfg := &veagent.Config{
            ModelName:    common.DEFAULT_MODEL_AGENT_NAME,
            ModelAPIBase: common.DEFAULT_MODEL_AGENT_API_BASE,
            ModelAPIKey:  utils.GetEnvWithDefault(common.MODEL_AGENT_API_KEY),
        }
        cfg.Name = "MemoryRecallAgent"
        cfg.Instruction = "Answer the user's question. Use the 'search_past_conversations' tools if the answer might be in past conversations."
    
        cfg.Tools = []tool.Tool{memorySearchTool}
    
        memorySearchAgent, err := veagent.New(cfg)
        if err != nil {
            log.Printf("NewLLMAgent failed: %v", err)
            return
        }
    
        // Use all default config
        //sessionService, err := vem.NewShortTermMemoryService(vem.BackendShortTermPostgreSQL, nil)
        //if err != nil {
        //	log.Printf("NewShortTermMemoryService failed: %v", err)
        //	return
        //}
        sessionService := session.InMemoryService()
        memoryService, err := vem.NewLongTermMemoryService(vem.BackendLongTermViking, nil)
        if err != nil {
            log.Printf("NewLongTermMemoryService failed: %v", err)
            return
        }
    
        runner1, err := runner.New(runner.Config{
            AppName:        appName,
            Agent:          infoCaptureAgent,
            SessionService: sessionService,
            MemoryService:  memoryService,
        })
        if err != nil {
            log.Fatal(err)
        }
    
        SessionID := "session123456789"
    
        s, err := sessionService.Create(ctx, &session.CreateRequest{
            AppName:   appName,
            UserID:    userID,
            SessionID: SessionID,
        })
        if err != nil {
            log.Fatalf("sessionService.Create error: %v", err)
        }
    
        s.Session.State()
    
        userInput1 := genai.NewContentFromText("My favorite project is Project Alpha.", "user")
        var finalResponseText string
        for event, err := range runner1.Run(ctx, userID, SessionID, userInput1, agent.RunConfig{}) {
            if err != nil {
                log.Printf("Agent 1 Error: %v", err)
                continue
            }
            if event.Content != nil && !event.LLMResponse.Partial {
                finalResponseText = strings.Join(textParts(event.LLMResponse.Content), "")
            }
        }
        log.Printf("Agent 1 Response: %s\n", finalResponseText)
    
        // Add the completed session to the Memory Service
        log.Println("\n--- Adding Session 1 to Memory ---")
        resp, err := sessionService.Get(ctx, &session.GetRequest{AppName: s.Session.AppName(), UserID: s.Session.UserID(), SessionID: s.Session.ID()})
        if err != nil {
            log.Fatalf("Failed to get completed session: %v", err)
        }
        if err := memoryService.AddSession(ctx, resp.Session); err != nil {
            log.Fatalf("Failed to add session to memory: %v", err)
        }
        log.Println("Session added to memory.")
    
        log.Println("\n--- Turn 2: Recalling Information ---")
    
        runner2, err := runner.New(runner.Config{
            AppName:        appName,
            Agent:          memorySearchAgent,
            SessionService: sessionService,
            MemoryService:  memoryService,
        })
        if err != nil {
            log.Fatal(err)
        }
    
        s, _ = sessionService.Create(ctx, &session.CreateRequest{
            AppName:   appName,
            UserID:    userID,
            SessionID: "session2222",
        })
    
        userInput2 := genai.NewContentFromText("What is my favorite project?", "user")
    
        var finalResponseText2 []string
        for event, err := range runner2.Run(ctx, s.Session.UserID(), s.Session.ID(), userInput2, agent.RunConfig{}) {
            if err != nil {
                log.Printf("Agent 2 Error: %v", err)
                continue
            }
            if event.Content != nil && !event.LLMResponse.Partial {
                for _, part := range event.Content.Parts {
                    finalResponseText2 = append(finalResponseText2, part.Text)
                }
            }
        }
        log.Printf("Agent 2 Response: %s\n", strings.Join(finalResponseText2, ""))
    
    }
    
    func textParts(Content *genai.Content) []string {
        var texts []string
        for _, part := range Content.Parts {
            texts = append(texts, part.Text)
        }
        return texts
    }
    ```

### 说明 / 结果展示

- 智能体能够识别并关联同一用户的历史交互；
- 提供连续性强、个性化的多会话交互体验；
- 为长期任务、学习型应用或持续监控场景提供基础能力。

```text
[Log Output]
Runner1 Question: My favorite project is Project Alpha.
Runner1 Answer: (Acknowledged)
...
[Step 4] Archiving session to Long-Term Memory via memory_service
Session archived to Long-Term Memory
...
Runner2 Question: favorite project
Runner2 Answer: Your favorite project is Project Alpha.
```

## 自动保存 session 到长期记忆

为简化操作流程，VeADK 的 Agent 模块支持将对话 Session 自动保存至长期记忆。只需在初始化 Agent 时，开启 auto_save_session 属性并完成长期记忆组件的初始化配置即可，具体示例如下：

```python
from veadk import Agent
from veadk.memory import LongTermMemory

# 初始化长期记忆组件
long_term_memory = LongTermMemory(
    backend="viking", app_name=APP_NAME, user_id=USER_ID
)

# 初始化 Agent 并开启 Session 自动保存
agent = Agent(
    auto_save_session=True,
    long_term_memory=long_term_memory
)
```

为避免索引被频繁初始化，VeADK 提供 MIN_MESSAGES_THRESHOLD 和 MIN_TIME_THRESHOLD 两个环境变量，支持自定义 Session 保存周期。其中，默认触发保存的条件为累计 10 条 event 或间隔 60 秒；此外，当切换 Session 并发起新的问答请求时，VeADK 会自动将旧 Session 的会话内容保存至长期记忆中。