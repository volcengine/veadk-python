import { useEffect, useRef, useState } from "react";
import { Loader2, Send, X, AlertCircle } from "lucide-react";
import {
  createSession,
  deleteTempAgent,
  deployTempAgent,
  runSSE,
} from "../adk/client";
import type { ProjectFile } from "../create/project";
import { applyEvent, emptyAcc, type Block } from "../blocks";
import { Blocks } from "./Blocks";
import "./AgentTest.css";

interface AgentTestProps {
  projectName: string;
  files: ProjectFile[];
  onClose: () => void;
}

interface Message {
  role: "user" | "assistant";
  content: string;
  blocks?: Block[];
  error?: string;
}

export function AgentTest({ projectName, files, onClose }: AgentTestProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [deploying, setDeploying] = useState(true);
  const [deployError, setDeployError] = useState<string | null>(null);
  const [appName, setAppName] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Deploy agent on mount
  useEffect(() => {
    async function deploy() {
      try {
        setDeploying(true);
        setDeployError(null);

        // Transform multi-agent structure to single-agent for testing
        // agents/{name}/agent.py -> agent.py
        // agents/{name}/__init__.py -> __init__.py
        const testFiles = files.map(f => {
          if (f.path.startsWith(`agents/${projectName}/`)) {
            return { ...f, path: f.path.replace(`agents/${projectName}/`, '') };
          }
          return f;
        });

        // Deploy the agent
        const name = await deployTempAgent(projectName, testFiles);
        setAppName(name);

        // Create a session
        const sid = await createSession(name, "test_user");
        setSessionId(sid);

        setDeploying(false);
      } catch (err) {
        console.error("Deploy failed:", err);
        setDeployError(err instanceof Error ? err.message : String(err));
        setDeploying(false);
      }
    }

    deploy();

    // Cleanup on unmount
    return () => {
      if (appName) {
        deleteTempAgent(appName).catch((err) =>
          console.error("Failed to cleanup temp agent:", err)
        );
      }
    };
  }, [projectName, files]);

  async function handleSend() {
    if (!input.trim() || loading || !appName || !sessionId) return;

    const userMessage: Message = { role: "user", content: input };
    const userInput = input;
    setInput("");
    setLoading(true);

    const assistantMessage: Message = {
      role: "assistant",
      content: "",
      blocks: [],
    };

    // Add both user and assistant messages at once to avoid state update race
    setMessages((prev) => [...prev, userMessage, assistantMessage]);

    try {
      let acc = emptyAcc();
      let fullText = "";

      for await (const event of runSSE({
        appName,
        userId: "test_user",
        sessionId,
        text: userInput,
      })) {
        // Check for errors
        const error = event.error || event.errorMessage || event.error_message;
        if (error) {
          assistantMessage.error = String(error);
          break;
        }

        // Apply event to accumulator
        acc = applyEvent(acc, event);

        // Extract text content from blocks
        fullText = acc.blocks
          .filter((b) => b.kind === "text")
          .map((b) => (b as { text: string }).text)
          .join("");

        // Update message with streaming content
        setMessages((prev) => {
          const updated = [...prev];
          const lastMsg = updated[updated.length - 1];
          if (lastMsg && lastMsg.role === "assistant") {
            lastMsg.content = fullText;
            lastMsg.blocks = acc.blocks;
          }
          return updated;
        });
      }
    } catch (err) {
      console.error("Run failed:", err);
      assistantMessage.error = err instanceof Error ? err.message : String(err);
      setMessages((prev) => {
        const updated = [...prev];
        const lastMsg = updated[updated.length - 1];
        if (lastMsg && lastMsg.role === "assistant") {
          lastMsg.error = assistantMessage.error;
        }
        return updated;
      });
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="agent-test">
      <div className="agent-test-header">
        <h3 className="agent-test-title">测试运行: {projectName}</h3>
        <button
          type="button"
          className="agent-test-close"
          onClick={onClose}
          aria-label="关闭"
        >
          <X className="icon" />
        </button>
      </div>

      {deploying ? (
        <div className="agent-test-loading">
          <Loader2 className="icon spin" />
          <span>正在部署 Agent...</span>
        </div>
      ) : deployError ? (
        <div className="agent-test-error">
          <AlertCircle className="icon" />
          <div>
            <div className="error-title">部署失败</div>
            <div className="error-message">{deployError}</div>
          </div>
        </div>
      ) : (
        <>
          <div className="agent-test-messages">
            {messages.length === 0 && (
              <div className="agent-test-empty">
                输入消息开始测试你的 Agent
              </div>
            )}
            {messages.map((msg, i) => (
              <div
                key={i}
                className={`agent-test-message ${
                  msg.role === "user" ? "user" : "assistant"
                }`}
              >
                <div className="message-role">
                  {msg.role === "user" ? "你" : projectName}
                </div>
                <div className="message-content">
                  {msg.role === "user" ? (
                    <div className="message-text">{msg.content}</div>
                  ) : msg.error ? (
                    <div className="message-error">
                      <AlertCircle className="icon" />
                      {msg.error}
                    </div>
                  ) : msg.blocks && msg.blocks.length > 0 ? (
                    <Blocks blocks={msg.blocks} onAction={() => {}} />
                  ) : (
                    <div className="message-text">{msg.content || "..."}</div>
                  )}
                </div>
              </div>
            ))}
            <div ref={messagesEndRef} />
          </div>

          <div className="agent-test-input">
            <input
              type="text"
              className="input"
              placeholder="输入消息..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
              disabled={loading}
            />
            <button
              type="button"
              className="send-button"
              onClick={handleSend}
              disabled={loading || !input.trim()}
            >
              {loading ? (
                <Loader2 className="icon spin" />
              ) : (
                <Send className="icon" />
              )}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
