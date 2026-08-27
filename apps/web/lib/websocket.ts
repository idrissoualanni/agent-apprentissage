// Client WebSocket de l'agent — reconnexion backoff + fallback HTTP.
// L'URL WS est derivee de NEXT_PUBLIC_API_URL :
//   https://host/api  →  wss://host

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api";
const WS_BASE = API_BASE
  .replace(/^https:/, "wss:")
  .replace(/^http:/, "ws:")
  .replace(/\/api\/?$/, "");

export interface AgentSocketHandlers {
  onToken: (text: string) => void;
  onMessage: (msg: Record<string, unknown>) => void;
  onConfirmationRequest: (confirmationType: string, prompt: string) => void;
  onNotification: (kind: string, data: Record<string, unknown>) => void;
  onError: (message: string) => void;
  onStatusChange: (connected: boolean) => void;
}

export interface AgentSocket {
  send: (payload: Record<string, unknown>) => boolean;
  close: () => void;
  isOpen: () => boolean;
}

export function createAgentSocket(
  sessionId: number,
  userId: string,
  handlers: AgentSocketHandlers,
  maxRetries: number = 3
): AgentSocket {
  let ws: WebSocket | null = null;
  let attempt = 0;
  let closedByUser = false;
  let pingTimer: ReturnType<typeof setInterval> | null = null;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  function clearTimers() {
    if (pingTimer) clearInterval(pingTimer);
    if (reconnectTimer) clearTimeout(reconnectTimer);
    pingTimer = null;
    reconnectTimer = null;
  }

  function connect() {
    try {
      ws = new WebSocket(
        `${WS_BASE}/ws/${sessionId}?user_id=${encodeURIComponent(userId)}`
      );
    } catch {
      handlers.onStatusChange(false);
      return;
    }

    ws.onopen = () => {
      attempt = 0;
      handlers.onStatusChange(true);
      pingTimer = setInterval(() => {
        if (ws?.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: "ping" }));
        }
      }, 25000);
    };

    ws.onmessage = (event) => {
      let msg: Record<string, unknown>;
      try {
        msg = JSON.parse(event.data);
      } catch {
        return;
      }
      switch (msg.type) {
        case "token":
          handlers.onToken(String(msg.text || ""));
          break;
        case "message":
          handlers.onMessage(msg);
          break;
        case "confirmation_request":
          handlers.onConfirmationRequest(
            String(msg.confirmation_type || ""),
            String(msg.confirmation_prompt || "")
          );
          break;
        case "notification":
          handlers.onNotification(
            String(msg.kind || ""),
            (msg.data as Record<string, unknown>) || {}
          );
          break;
        case "error":
          handlers.onError(String(msg.message || "erreur"));
          break;
        case "pong":
          break;
      }
    };

    ws.onclose = (event) => {
      clearTimers();
      handlers.onStatusChange(false);
      if (closedByUser) return;
      // 4000 = remplace par un autre onglet : ne pas reconnecter
      if (event.code === 4000) return;
      // Ne jamais abandonner : la machine Fly met 5-9s a se reveiller de
      // suspension. Retries rapides (1s/2s/4s) puis lentes (15s) en continu ;
      // le fallback HTTP assure les envois en attendant.
      const delay =
        attempt < maxRetries
          ? Math.min(15000, 1000 * Math.pow(2, attempt)) + Math.random() * 500
          : 15000;
      attempt += 1;
      reconnectTimer = setTimeout(connect, delay);
    };

    ws.onerror = () => {
      // onclose suivra et gerera la reconnexion
    };
  }

  connect();

  return {
    send: (payload) => {
      if (ws?.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify(payload));
        return true;
      }
      return false;
    },
    close: () => {
      closedByUser = true;
      clearTimers();
      ws?.close();
    },
    isOpen: () => ws?.readyState === WebSocket.OPEN,
  };
}
