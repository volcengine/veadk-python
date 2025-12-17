package main

import (
	"context"
	"fmt"
	"log"
	"math"
	"os"
	"strings"
	"time"

	veagent "github.com/volcengine/veadk-go/agent/llmagent"
	"github.com/volcengine/veadk-go/integrations/ve_tos"
	"github.com/volcengine/veadk-go/knowledgebase"
	"github.com/volcengine/veadk-go/knowledgebase/backend/viking_knowledge_backend"
	"github.com/volcengine/veadk-go/knowledgebase/ktypes"
	"google.golang.org/adk/agent"
	"google.golang.org/adk/agent/llmagent"
	"google.golang.org/adk/cmd/launcher"
	"google.golang.org/adk/cmd/launcher/full"
	"google.golang.org/adk/session"
	"google.golang.org/adk/tool"
	"google.golang.org/adk/tool/functiontool"
)

func main() {
	ctx := context.Background()
	knowledgeBase, err := knowledgebase.NewKnowledgeBase(
		ktypes.VikingBackend,
		knowledgebase.WithBackendConfig(
			&viking_knowledge_backend.Config{
				Index:            "veadk_go_test_kg",
				CreateIfNotExist: true,
				TosConfig: &ve_tos.Config{
					Bucket: "veadk-go-bucket",
				},
			}),
	)
	if err != nil {
		log.Fatal("NewVikingKnowledgeBackend error: ", err)
	}

	mock_data := []string{
		`西格蒙德·弗洛伊德（Sigmund Freud，1856年5月6日-1939年9月23日）是精神分析的创始人。
	精神分析既是一种治疗精神疾病的方法，也是一种解释人类行为的理论。弗洛伊德认为，我们童年时期的经历对我们的成年生活有很大的影响，并且塑造了我们的个性。
	例如，源自人们曾经的创伤经历的焦虑感，会隐藏在意识深处，并且可能在成年期间引起精神问题（以神经症的形式）。`,
		`阿尔弗雷德·阿德勒（Alfred Adler，1870年2月7日-1937年5月28日），奥地利精神病学家，人本主义心理学先驱，个体心理学的创始人。
	曾追随弗洛伊德探讨神经症问题，但也是精神分析学派内部第一个反对弗洛伊德的心理学体系的心理学家。
	著有《自卑与超越》《人性的研究》《个体心理学的理论与实践》《自卑与生活》等。`}

	if err = knowledgeBase.Backend.AddFromText(mock_data); err != nil {
		log.Fatal("AddFromText error: ", err)
		return
	}

	calculateDateDifferenceTool, err := CalculateDateDifferenceTool()
	if err != nil {
		log.Fatal("CalculateDateDifferenceTool error: ", err)
		return
	}

	cfg := veagent.Config{
		Config: llmagent.Config{
			Name:        "chat_agent",
			Description: "你是一个优秀的助手，你可以和用户进行对话。",
			Instruction: `你是一个优秀的助手。当被提问时，请遵循以下步骤：\n1. 首先，根据你的内部知识，生成一个初步的回答。\n2. 然后，查询你的知识库，寻找与问题相关的信息来验证或丰富你的答案。\n3. 最后，结合你的内部知识和知识库中的信息，给出一个全面、准确的最终答案。`,
			Tools:       []tool.Tool{calculateDateDifferenceTool},
		},
		ModelName:     "doubao-seed-1-6-250615",
		KnowledgeBase: knowledgeBase,
	}

	veAgent, err := veagent.New(&cfg)
	if err != nil {
		fmt.Printf("NewLLMAgent failed: %v", err)
		return
	}

	config := &launcher.Config{
		AgentLoader:    agent.NewSingleLoader(veAgent),
		SessionService: session.InMemoryService(),
	}

	l := full.NewLauncher()
	if err = l.Execute(ctx, config, os.Args[1:]); err != nil {
		log.Fatalf("Run failed: %v\n\n%s", err, l.CommandLineSyntax())
	}
}

type CalculateDateDifferenceArgs struct {
	Date1 string `json:"date1" jsonschema:"第一个日期，格式为YYYY-MM-DD"`
	Date2 string `json:"date2" jsonschema:"第二个日期，格式为YYYY-MM-DD"`
}

func CalculateDateDifferenceTool() (tool.Tool, error) {
	handler := func(ctx tool.Context, args CalculateDateDifferenceArgs) (map[string]any, error) {
		diff, err := CalculateDateDifference(args.Date1, args.Date2)
		if err != nil {
			return nil, err
		}
		return map[string]any{"result": diff}, nil
	}
	return functiontool.New(
		functiontool.Config{
			Name:        "calculate date difference",
			Description: "计算两个日期之间的天数差异\nArgs:\n\tdate1: 第一个日期，格式为YYYY-MM-DD\n\tdate2: 第二个日期，格式为YYYY-MM-DD\nReturns:\n\t两个日期之间的天数差异（绝对值）",
		},
		handler,
	)
}

func CalculateDateDifference(date1 string, date2 string) (int, error) {
	d1, err := time.Parse("2006-01-02", strings.TrimSpace(date1))
	if err != nil {
		return 0, fmt.Errorf("日期格式错误，请使用YYYY-MM-DD格式: %v", err)
	}
	d2, err := time.Parse("2006-01-02", strings.TrimSpace(date2))
	if err != nil {
		return 0, fmt.Errorf("日期格式错误，请使用YYYY-MM-DD格式: %v", err)
	}
	delta := d2.Sub(d1)
	days := int(math.Abs(delta.Hours() / 24))
	return days, nil
}
