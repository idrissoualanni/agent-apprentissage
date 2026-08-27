"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { MessageBubble } from "./MessageBubble";
import { StreamingText } from "./StreamingText";
import { ConfirmationButtons } from "./ConfirmationButtons";
import { ToolBadge } from "./ToolBadge";
import { Composer } from "./Composer";
import { ArtifactRenderer } from "@/components/artifacts/ArtifactRenderer";
import { sessions, chat } from "@/lib/api";
import { streamChat, parseJSONResponse } from "@/lib/sse";
import { createAgentSocket, type AgentSocket } from "@/lib/websocket";
import type { ChatMessage, ToolUsage, StreamEvent } from "@/lib/types";

interface ChatWindowProps {
  sessionId: number;
  cachedMessages?: ChatMessage[];
  onCacheMessages?: (id: number, msgs: ChatMessage[]) => void;
}

export function ChatWindow({ sessionId, cachedMessages, onCacheMessages }: ChatWindowProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingText, setStreamingText] = useState("");
  const [streamingMethod, setStreamingMethod] = useState<string | undefined>();
  const [toolsUsed, setToolsUsed] = useState<ToolUsage[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [pendingConfirmation, setPendingConfirmation] = useState<{
    type: string;
    prompt: string;
    messageId: number;
  } | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  // WebSocket : streaming reel + confirmations sur la meme connexion
  const socketRef = useRef<AgentSocket | null>(null);
  const streamingRef = useRef("");
  const [socketConnected, setSocketConnected] = useState(false);
  const [notification, setNotification] = useState<string | null>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, streamingText]);

  // Load session messages (re-run on sessionId change + retry via loadAttempt).
  // Si les messages sont deja en cache : affichage instantane, aucun appel reseau.
  useEffect(() => {
    if (!sessionId) return;
    setStreamingText("");
    setPendingConfirmation(null);
    setLoadError(null);
    if (cachedMessages && cachedMessages.length > 0) {
      setMessages(cachedMessages);
      return;
    }
    setMessages([]);
    sessions.messages(sessionId).then((data) => {
      setMessages(data);
      onCacheMessages?.(sessionId, data);
    }).catch((err) => {
      console.error(err);
      setLoadError(
        "Impossible de charger les messages (le serveur démarre peut-être). "
      );
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, loadAttempt]);

  // Garde le cache parent synchronise (nouveaux messages envoyes/recus).
  useEffect(() => {
    if (sessionId && messages.length > 0) {
      onCacheMessages?.(sessionId, messages);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages]);

  // Connexion WebSocket par session (streaming reel + HITL + notifications).
  useEffect(() => {
    if (!sessionId) return;
    const socket = createAgentSocket(sessionId, "default_user", {
      onToken: (text) => {
        streamingRef.current += text;
        setStreamingText(streamingRef.current);
      },
      onMessage: (msg) => {
        const assistantMsg: ChatMessage = {
          id: Date.now(),
          role: "assistant",
          content: String(msg.answer || ""),
          method: msg.method as string | undefined,
          tools_used: msg.tool_transparency as ToolUsage[] | undefined,
          artifacts: msg.artifacts as ChatMessage["artifacts"],
          created_at: new Date().toISOString(),
        };
        setMessages((prev) => [...prev, assistantMsg]);
        setStreamingText("");
        streamingRef.current = "";
        setIsStreaming(false);
      },
      onConfirmationRequest: (type, prompt) => {
        setPendingConfirmation({ type, prompt, messageId: Date.now() });
        setIsStreaming(false);
        setStreamingText("");
        streamingRef.current = "";
      },
      onNotification: (kind, data) => {
        if (kind === "revision_due") {
          setNotification(`📅 ${data.count} révision(s) due(s)`);
        }
      },
      onError: (message) => {
        if (message === "agent_busy") return; // l'UI desactive deja l'envoi
        console.error("WS error:", message);
      },
      onStatusChange: setSocketConnected,
    });
    socketRef.current = socket;
    return () => {
      socket.close();
      socketRef.current = null;
    };
  }, [sessionId]);

  const handleSend = useCallback(async (question: string, forceWebSearch: boolean = false) => {
    const trimmed = question.trim();
    if (!trimmed || isStreaming) return;

    setIsStreaming(true);
    setStreamingText("");
    setToolsUsed([]);

    // Add user message immediately
    const userMsg: ChatMessage = {
      id: Date.now(),
      role: "user",
      content: trimmed,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);

    // Chemin WebSocket (streaming reel) si connecte
    const sent = socketRef.current?.send({
      type: "chat",
      question: trimmed,
      force_web_search: forceWebSearch,
    });
    if (sent) {
      streamingRef.current = "";
      setStreamingMethod(undefined);
      return; // la reponse arrive par onToken/onMessage
    }

    // Sinon : fallback HTTP
    try {
      const response = await chat.send({
        question: trimmed,
        session_id: sessionId,
        force_web_search: forceWebSearch,
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
        artifacts: response.artifacts,
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
  }, [isStreaming, sessionId]);

  const handleConfirm = async (accepted: boolean) => {
    if (!pendingConfirmation) return;

    // Chemin WebSocket si connecte (reprise HITL temps reel)
    const sent = socketRef.current?.send({ type: "confirm", accepted });
    if (sent) {
      setPendingConfirmation(null);
      if (!accepted) {
        const msg: ChatMessage = {
          id: Date.now(),
          role: "assistant",
          content: "Pas de souci ! Pose-moi une autre question.",
          created_at: new Date().toISOString(),
        };
        setMessages((prev) => [...prev, msg]);
      } else {
        setIsStreaming(true);
        streamingRef.current = "";
        setStreamingText("");
      }
      return;
    }

    // Sinon : fallback HTTP
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
        {loadError && (
          <div className="flex flex-col items-center justify-center gap-3 p-6 rounded-lg border border-red-900/50 bg-red-950/20 text-center">
            <p className="text-sm text-red-300">{loadError}</p>
            <button
              onClick={() => setLoadAttempt((n) => n + 1)}
              className="px-3 py-1.5 rounded-md bg-red-900/40 hover:bg-red-900/60 text-red-200 text-sm transition-colors"
            >
              Réessayer
            </button>
          </div>
        )}

        {/* Statut de la connexion temps reel */}
        {!socketConnected && !loadError && (
          <div className="text-xs text-amber-400/80 px-1">
            ⚡ Connexion temps réel indisponible — mode classique
          </div>
        )}

        {/* Notification (revisions dues) */}
        {notification && (
          <div className="flex items-center justify-between px-3 py-2 rounded-lg border border-primary-900/50 bg-primary-950/20 text-xs text-primary-300">
            <span>{notification}</span>
            <button
              onClick={() => setNotification(null)}
              className="ml-2 text-primary-400 hover:text-primary-200"
            >
              ✕
            </button>
          </div>
        )}

        {messages.length === 0 && !streamingText && !loadError && (
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
            {/* Correctif 2 : afficher les artefacts (quiz interactif, etc.) */}
            {msg.artifacts && msg.artifacts.length > 0 && (
              <div className="mt-2 space-y-2">
                {msg.artifacts.map((artifact, ai) => (
                  <ArtifactRenderer
                    key={ai}
                    artifact={artifact}
                    sessionId={sessionId}
                  />
                ))}
              </div>
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

      {/* Input area — Composer avec bouton + (upload) et toggle recherche web */}
      <Composer onSend={handleSend} disabled={isStreaming} />
    </div>
  );
}
