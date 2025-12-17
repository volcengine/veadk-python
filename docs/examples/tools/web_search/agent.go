package main

import (
	"context"
	"log"
	"os"

	veagent "github.com/volcengine/veadk-go/agent/llmagent"
	"github.com/volcengine/veadk-go/common"
	"github.com/volcengine/veadk-go/tool/builtin_tools/web_search"
	"github.com/volcengine/veadk-go/utils"
	"google.golang.org/adk/agent"
	"google.golang.org/adk/cmd/launcher"
	"google.golang.org/adk/cmd/launcher/full"
	"google.golang.org/adk/session"
	"google.golang.org/adk/tool"
)

func main() {
	ctx := context.Background()
	sessionService := session.InMemoryService()

	cfg := &veagent.Config{
		ModelName:    common.DEFAULT_MODEL_AGENT_NAME,
		ModelAPIBase: common.DEFAULT_MODEL_AGENT_API_BASE,
		ModelAPIKey:  utils.GetEnvWithDefault(common.MODEL_AGENT_API_KEY),
	}
	cfg.Name = "WebSearchAgent"
	cfg.Description = "An agent that can get result from Web Search"
	cfg.Instruction = "You are a helpful assistant that can provide information use web search tool."

	webSearch, err := web_search.NewWebSearchTool(&web_search.Config{})
	if err != nil {
		log.Fatalf("NewWebSearchTool failed: %v", err)
		return
	}

	cfg.Tools = []tool.Tool{webSearch}

	rootAgent, err := veagent.New(cfg)
	if err != nil {
		log.Fatalf("Failed to create agent: %v", err)
	}

	config := &launcher.Config{
		AgentLoader:    agent.NewSingleLoader(rootAgent),
		SessionService: sessionService,
	}

	l := full.NewLauncher()
	if err = l.Execute(ctx, config, os.Args[1:]); err != nil {
		log.Fatalf("Run failed: %v\n\n%s", err, l.CommandLineSyntax())
	}
}
