/** Client SSE — Streaming token par token depuis FastAPI */

import type { StreamEvent } from "./types";

type SSECallback = (event: StreamEvent) => void;

interface StreamOptions {
  timeoutMs?: number;  // Timeout sans token (defaut 15s)
  onTimeout?: () => void;
  onError?: (error: Error) => void;
}

/**
 * Ouvre une connexion SSE pour le chat streaming.
 * Retourne un controller pour annuler.
 * 
 * Features :
 * - Timeout client (aucun token en 15s → erreur)
 * - Gestion propre des erreurs de connexion
 * - Callback onTimeout pour afficher un bouton "Réessayer"
 */
export function streamChat(
  question: string,
  sessionId: number,
  onEvent: SSECallback,
  options: StreamOptions = {}
): AbortController {
  const {
    timeoutMs = 15000,
    onTimeout,
    onError,
  } = options;
  
  const controller = new AbortController();
  let lastTokenTime = Date.now();
  let timeoutTimer: ReturnType<typeof setTimeout> | null = null;

  // Timer de timeout : declenche onTimeout si aucun token recu pendant timeoutMs
  const startTimeoutTimer = () => {
    if (timeoutTimer) clearTimeout(timeoutTimer);
    timeoutTimer = setTimeout(() => {
      if (Date.now() - lastTokenTime > timeoutMs) {
        controller.abort();
        onTimeout?.();
      }
    }, timeoutMs);
  };

  const resetTimeoutTimer = () => {
    lastTokenTime = Date.now();
    startTimeoutTimer();
  };

  fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, session_id: sessionId, streaming: true }),
    signal: controller.signal,
  })
    .then(async (response) => {
      if (!response.ok) {
        throw new Error(`SSE connection failed: ${response.status}`);
      }

      const reader = response.body?.getReader();
      if (!reader) throw new Error("No response body");

      const decoder = new TextDecoder();
      let buffer = "";

      // Demarrer le timeout apres le premier token
      let started = false;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              const data = JSON.parse(line.slice(6));
              onEvent(data as StreamEvent);
              
              // Reset timeout a chaque token recu
              if (!started) {
                started = true;
                startTimeoutTimer();
              } else {
                resetTimeoutTimer();
              }
            } catch {
              // Ignore malformed SSE lines
            }
          }
        }
      }
      
      // Clear timeout quand le stream est termine
      if (timeoutTimer) clearTimeout(timeoutTimer);
    })
    .catch((err) => {
      if (timeoutTimer) clearTimeout(timeoutTimer);
      if (err.name === "AbortError") {
        // Timeout ou abort explicite — deja gere par onTimeout
        return;
      }
      onError?.(err);
    });

  return controller;
}

// API_BASE pour le module SSE (meme logique que api.ts)
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api";

/**
 * Parse une réponse JSON normale en événements simulés.
 * Utile quand le backend ne fait pas du SSE.
 */
export function* parseJSONResponse(response: {
  answer: string;
  method?: string;
  tools_used?: unknown[];
  pending_confirmation?: boolean;
  confirmation_type?: string;
  confirmation_prompt?: string;
  artifacts?: unknown[];
}): Generator<StreamEvent> {
  if (response.pending_confirmation) {
    yield {
      event: "pending_confirmation",
      data: {
        prompt: response.confirmation_prompt || "",
        type: response.confirmation_type || "",
        message_id: 0,
      },
    };
    return;
  }

  // Simulate token-by-token
  const words = response.answer.split(" ");
  for (let i = 0; i < words.length; i++) {
    yield {
      event: "token",
      data: { text: (i === 0 ? "" : " ") + words[i], method: response.method },
    };
  }

  if (response.artifacts) {
    for (const artifact of response.artifacts) {
      yield { event: "artifact", data: artifact as StreamEvent["data"] };
    }
  }

  yield {
    event: "done",
    data: {
      session_id: 0,
      message_id: 0,
      tools_used: (response.tools_used || []) as StreamEvent["data"]["tools_used"],
    },
  };
}
