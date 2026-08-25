"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { MessageBubble } from "./MessageBubble";
import { StreamingText } from "./StreamingText";
import { ConfirmationButtons } from "./ConfirmationButtons";
import { ToolBadge } from "./ToolBadge";
import { sessions, chat } from "@/lib/api";
import { streamChat, parseJSONResponse } from "@/lib/sse";
import type { ChatMessage, ToolUsage, StreamEvent } from "@/lib/types";
import { Send, Loader2 } from "lucide-react";

interface ChatWindowProps {
  sessionId: number;
}

export function ChatWindow({ sessionId }: ChatWindowProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingText, setStreamingText] = useState("");
  const [streamingMethod, setStreamingMethod] = useState<string | undefined>();
  const [toolsUsed, setToolsUsed] = useState<ToolUsage[]>([]);
  const [pendingConfirmation, setPendingConfirmation] = useState<{
    type: string;
    prompt: string;
    messageId: number;
  } | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, streamingText]);

  // Load session messages
  useEffect(() => {
    if (!sessionId) return;
    setMessages([]);
    setStreamingText("");
    sessions.messages(sessionId).then((data) => {
      setMessages(data);
    }).catch(console.error);
  }, [sessionId]);

  const handleSend = useCallback(async () => {
    const question = input.trim();
    if (!question || isStreaming) return;

    setInput("");
    setIsStreaming(true);
    setStreamingText("");
    setToolsUsed([]);

    // Add user message immediately
    const userMsg: ChatMessage = {
      id: Date.now(),
      role: "user",
      content: question,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);

    try {
      const response = await chat.send({
        question,
        session_id: sessionId,
      });

      if (response.pending_confirmation) {
        setPendingConfirmation({
          type: response.confirmation_type || "",
          prompt: response.confirmation_prompt || "",
          messageId: response.message_id,
        });
        setIsStreaming(false);
        return;
      }

      // Simulate streaming from response
      let accumulated = "";
      const words = response.answer.split(" ");
      for (const word of words) {
        accumulated += (accumulated ? " " : "") + word;
        setStreamingText(accumulated);
        setStreamingMethod(response.method);
        await new Promise((r) => setTimeout(r, 20));
      }

      // Finalize message
      const assistantMsg: ChatMessage = {
        id: response.message_id || Date.now(),
        role: "assistant",
        content: response.answer,
        method: response.method,
        tools_used: response.tool_transparency,
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, assistantMsg]);
      setStreamingText("");
      if (response.tool_transparency) {
        setToolsUsed(response.tool_transparency);
      }
    } catch (err) {
      console.error("Chat error:", err);
      const errorMsg: ChatMessage = {
        id: Date.now(),
        role: "assistant",
        content: `Erreur: ${err instanceof Error ? err.message : "Erreur inconnue"}`,
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, errorMsg]);
      setStreamingText("");
    } finally {
      setIsStreaming(false);
    }
  }, [input, isStreaming, sessionId]);

  const handleConfirm = async (accepted: boolean) => {
    if (!pendingConfirmation) return;

    try {
      const response = await chat.confirm({
        message_id: pendingConfirmation.messageId,
        accepted,
        session_id: sessionId,
      });

      setPendingConfirmation(null);

      if (!accepted) {
        const msg: ChatMessage = {
          id: Date.now(),
          role: "assistant",
          content: "Pas de souci ! Pose-moi une autre question.",
          created_at: new Date().toISOString(),
        };
        setMessages((prev) => [...prev, msg]);
        return;
      }

      // Stream the response
      setIsStreaming(true);
      setStreamingText("");

      let accumulated = "";
      const words = response.answer.split(" ");
      for (const word of words) {
        accumulated += (accumulated ? " " : "") + word;
        setStreamingText(accumulated);
        setStreamingMethod(response.method);
        await new Promise((r) => setTimeout(r, 20));
      }

      const assistantMsg: ChatMessage = {
        id: response.message_id || Date.now(),
        role: "assistant",
        content: response.answer,
        method: response.method,
        tools_used: response.tool_transparency,
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, assistantMsg]);
      setStreamingText("");
    } catch (err) {
      console.error("Confirmation error:", err);
      setPendingConfirmation(null);
    } finally {
      setIsStreaming(false);
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Messages area */}
      <div className="flex-1 overflow-y-auto px-4 py-6 space-y-4">
        {messages.length === 0 && !streamingText && (
          <div className="flex flex-col items-center justify-center h-full text-zinc-500">
            <p className="text-lg">Pose-moi une question !</p>
            <p className="text-sm mt-1 text-zinc-600">
              Je peux t'aider avec tes cours, creer des quizzes, ou expliquer des concepts.
            </p>
          </div>
        )}

        {messages.map((msg) => (
          <div key={msg.id}>
            <MessageBubble message={msg} />
            {msg.tools_used && msg.tools_used.length > 0 && (
              <ToolBadge tools={msg.tools_used} />
            )}
          </div>
        ))}

        {/* Streaming text */}
        {streamingText && (
          <div>
            <StreamingText text={streamingText} method={streamingMethod} />
          </div>
        )}

        {/* Confirmation prompt */}
        {pendingConfirmation && (
          <ConfirmationButtons
            prompt={pendingConfirmation.prompt}
            type={pendingConfirmation.type}
            onConfirm={() => handleConfirm(true)}
            onCancel={() => handleConfirm(false)}
          />
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      <div className="border-t border-zinc-800 bg-surface-1/50 p-4">
        <div className="flex items-end gap-2 max-w-3xl mx-auto">
          <div className="flex-1 relative">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
              placeholder="Pose ta question..."
              rows={1}
              className="w-full resize-none rounded-xl bg-surface-2 border border-zinc-700 px-4 py-3 pr-12 text-sm text-zinc-100 placeholder-zinc-500 focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none transition-colors"
              disabled={isStreaming}
            />
          </div>
          <button
            onClick={handleSend}
            disabled={!input.trim() || isStreaming}
            className="p-3 rounded-xl bg-primary-600 hover:bg-primary-700 disabled:opacity-40 disabled:cursor-not-allowed text-white transition-colors"
          >
            {isStreaming ? (
              <Loader2 size={18} className="animate-spin" />
            ) : (
              <Send size={18} />
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
