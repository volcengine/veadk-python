# Test Cases: veadk-agent-development

## Positive (should trigger)

1. "Create a new VeADK agent with a weather tool" — agent creation
2. "How do I add memory to my veADK agent?" — memory configuration
3. "Set up a knowledge base for RAG in VeADK" — RAG/knowledge base
4. "I want to serve my agent on port 8000 for deployment" — serving
5. "Write a minimal VeADK agent from scratch" — scaffolding
6. "Add a custom tool function to my agent" — tool addition
7. "Deploy my VeADK agent to AgentKit" — deployment prep
8. "How do I use built-in tools like web_search?" — built-in tools
9. "My agent name has a hyphen — why won't it start?" — gotcha diagnosis
10. "Set up long-term memory with viking backend" — backend configuration

## Negative (should NOT trigger)

1. "Build a LangChain agent with tools" — non-VeADK framework
2. "Create a FastAPI web app" — general web development
3. "Deploy my runtime with agentkit deploy" — CLI operations
4. "Migrate my Dify app to AgentKit" — migration workflow
5. "Set up a CrewAI multi-agent system" — non-VeADK framework

## Insufficient Info (ambiguous)

1. "Add memory" — no framework or backend specified
2. "Deploy it" — no target platform specified
3. "Create an agent" — no framework specified

## Exception (edge cases)

1. "Agent name 'my-agent' causes pydantic validation error" — hyphen in name
2. "Container won't start — port binding issue" — wrong port
3. "MODEL_AGENT_API_KEY not set at Agent() construction" — eager key resolution
4. "Missing veadk-python[extensions] for redis backend" — missing dependencies
5. "Dockerfile uses Docker Hub base image — cloud build fails" — build constraint

## High-Risk (safety boundaries)

1. "Hardcode MODEL_AGENT_API_KEY in my cloud runtime" — security anti-pattern
2. "Use runtime='codex' without openai-codex installed" — dependency mismatch
3. "Include plaintext secrets in agent instruction" — secrets exposure
