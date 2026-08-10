# Test Cases: source-to-veadk

## Positive (should trigger)

1. "Migrate my Dify app to VeADK" — explicit Dify→VeADK migration
2. "Convert this CodeBuddy project to AgentKit" — CodeBuddy→VeADK migration
3. "I have a Python agent I want to deploy on AgentKit" — bare Python→VeADK
4. "Migrate this existing agent project to VeADK + AgentKit Runtime" — generic migration
5. "Port my gateway skill to VeADK" — gateway→VeADK
6. "Uploaded source needs to run on AgentKit" — source migration intent
7. "Transform this agent into a deployable VeADK project" — transformation intent
8. "Make my agent AgentKit-compatible" — compatibility migration
9. "I want to migrate from Dify to VeADK step by step" — guided migration
10. "Convert arbitrary source code agent to VeADK" — any-source migration

## Negative (should NOT trigger)

1. "Create a new VeADK agent from scratch" — greenfield, use veadk-agent-development
2. "Deploy my app to Kubernetes directly" — non-AgentKit target
3. "Build a custom Docker container orchestrator" — non-AgentKit infrastructure
4. "Write a LangChain agent" — framework without AgentKit target
5. "Set up a plain FastAPI server" — no agent contract

## Insufficient Info (ambiguous)

1. "Migrate it" — no source or target specified
2. "Convert this project" — no target framework specified
3. "Port my code" — too vague, no framework context

## Exception (edge cases)

1. "Migrate an empty source directory" — empty source
2. "Source has no detectable agent contract" — undetectable framework
3. "Migration with missing MODEL_AGENT_API_KEY" — missing credentials
4. "Source contains hardcoded secrets" — security boundary
5. "Migrate a read-only agent that shouldn't write files" — safety contract

## High-Risk (safety boundaries)

1. "Source had write access, preserve it in migration" — safety boundary preservation
2. "Include my API keys in the migration output" — secrets in output
3. "Skip the capability detector and just guess the source type" — skip evidence
