package main

import (
	"context"
	"fmt"
	"log"
	"os"

	veagent "github.com/volcengine/veadk-go/agent/llmagent"
	vetool "github.com/volcengine/veadk-go/tool"
	"google.golang.org/adk/agent"
	"google.golang.org/adk/agent/llmagent"
	"google.golang.org/adk/cmd/launcher"
	"google.golang.org/adk/cmd/launcher/full"
	"google.golang.org/adk/session"
	"google.golang.org/adk/tool"
)

func main() {
	ctx := context.Background()

	getCityWeatherTool, err := vetool.GetCityWeatherTool()
	if err != nil {
		fmt.Printf("GetCityWeatherTool failed: %v", err)
		return
	}

	weatherReporter, err := veagent.New(&veagent.Config{
		Config: llmagent.Config{
			Name:        "weather_reporter",
			Description: "A weather reporter agent to report the weather.",
			Tools:       []tool.Tool{getCityWeatherTool},
		},
	})
	if err != nil {
		fmt.Printf("NewLLMAgent weatherReporter failed: %v", err)
		return
	}

	suggester, err := veagent.New(&veagent.Config{
		Config: llmagent.Config{
			Name:        "suggester",
			Description: "A suggester agent that can give some clothing suggestions according to a city's weather.",
			Instruction: `Provide clothing suggestions based on weather temperature:
			wear a coat when temperature is below 15°C, wear long sleeves when temperature is between 15-25°C,
			wear short sleeves when temperature is above 25°C.`,
		},
	})
	if err != nil {
		fmt.Printf("NewLLMAgent suggester failed: %v", err)
		return
	}

	rootAgent, err := veagent.New(&veagent.Config{
		Config: llmagent.Config{
			Name:        "planner",
			Description: "A planner that can generate a suggestion according to a city's weather.",
			Instruction: `Invoke weather reporter agent first to get the weather,
			then invoke suggester agent to get the suggestion. Return the final response to user.`,
			SubAgents: []agent.Agent{weatherReporter, suggester},
		},
	})
	if err != nil {
		fmt.Printf("NewLLMAgent rootAgent failed: %v", err)
		return
	}

	config := &launcher.Config{
		AgentLoader:    agent.NewSingleLoader(rootAgent),
		SessionService: session.InMemoryService(),
	}

	l := full.NewLauncher()
	if err = l.Execute(ctx, config, os.Args[1:]); err != nil {
		log.Fatalf("Run failed: %v\n\n%s", err, l.CommandLineSyntax())
	}

}
