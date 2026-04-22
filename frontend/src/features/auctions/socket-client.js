import { getAccessToken } from "../../lib/auth/store";

function getBackendUrl() {
  if (process.env.REACT_APP_BACKEND_URL) {
    return process.env.REACT_APP_BACKEND_URL.trim().replace(/\/+$/, "");
  }

  if (typeof window !== "undefined") {
    const hostname = window.location.hostname || "localhost";
    if (hostname === "localhost" || hostname === "127.0.0.1") {
      return `${window.location.protocol}//${hostname}:8000`;
    }

    return window.location.origin || "";
  }

  return "";
}

function toWebSocketUrl(baseUrl, sessionId) {
  const endpoint = new URL(`/ws/auction/${sessionId}`, baseUrl || "http://localhost:8000");
  endpoint.protocol = endpoint.protocol === "https:" ? "wss:" : "ws:";
  return endpoint.toString();
}

function getWebSocketProtocols(token) {
  if (!token) {
    return [];
  }

  return ["access-token", token];
}

function parseMessage(data) {
  if (typeof data !== "string") {
    return { raw: data, eventName: null, payload: data };
  }

  try {
    const parsed = JSON.parse(data);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      return { raw: data, eventName: null, payload: parsed };
    }

    const eventName = parsed.event ?? parsed.eventType ?? parsed.type ?? parsed.name ?? null;
    const payload = parsed.data ?? parsed.payload ?? parsed.body ?? parsed;

    return { raw: data, eventName, payload };
  } catch (_error) {
    return { raw: data, eventName: null, payload: data };
  }
}

export function createAuctionSocket({
  sessionId,
  onConnect,
  onDisconnect,
  onReconnect,
  onEvent,
  onError,
} = {}) {
  if (sessionId === undefined || sessionId === null || sessionId === "") {
    throw new Error("sessionId is required");
  }

  const eventHandlers = new Map();
  const anyHandlers = new Set();
  let socket = null;
  let reconnecting = false;
  let manualClose = false;

  function emit(eventName, detail) {
    anyHandlers.forEach((handler) => {
      handler(detail);
    });

    const handlers = eventHandlers.get(eventName);
    if (!handlers) {
      return;
    }

    handlers.forEach((handler) => {
      handler(detail);
    });
  }

  function bindSocket(nextSocket) {
    nextSocket.onopen = (event) => {
      emit("connect", { event, socket: nextSocket });
      if (reconnecting) {
        reconnecting = false;
        onReconnect?.(event);
        emit("reconnect", { event, socket: nextSocket });
        return;
      }

      onConnect?.(event);
    };

    nextSocket.onmessage = (event) => {
      const message = parseMessage(event.data);
      const detail = {
        ...message,
        socket: nextSocket,
        event: message.eventName,
      };

      onEvent?.(detail);
      if (message.eventName) {
        emit(message.eventName, detail);
      }
    };

    nextSocket.onerror = (event) => {
      onError?.(event);
      emit("error", { event, socket: nextSocket });
      emit("connect_error", { event, socket: nextSocket });
    };

    nextSocket.onclose = (event) => {
      const wasReconnect = reconnecting;
      if (manualClose) {
        manualClose = false;
      }

      if (!wasReconnect) {
        onDisconnect?.(event);
      }
      emit("disconnect", { event, socket: nextSocket });

      if (socket === nextSocket) {
        socket = null;
      }
    };
  }

  function connect() {
    if (socket && socket.readyState === WebSocket.OPEN) {
      return socket;
    }

    if (socket && socket.readyState === WebSocket.CONNECTING) {
      return socket;
    }

    const token = getAccessToken();
    const wsUrl = toWebSocketUrl(getBackendUrl(), sessionId);
    socket = new WebSocket(wsUrl, getWebSocketProtocols(token));
    bindSocket(socket);
    return socket;
  }

  function disconnect(code = 1000, reason = "client disconnect") {
    if (!socket) {
      return;
    }

    manualClose = true;
    socket.close(code, reason);
  }

  function reconnect() {
    reconnecting = true;
    if (socket) {
      socket.close(1000, "client reconnect");
    }

    return connect();
  }

  function send(eventName, payload = {}) {
    const activeSocket = connect();
    const message = JSON.stringify({
      event: eventName,
      data: payload,
    });

    activeSocket.send(message);
    return message;
  }

  function on(eventName, handler) {
    const handlers = eventHandlers.get(eventName) ?? new Set();
    handlers.add(handler);
    eventHandlers.set(eventName, handlers);

    return () => off(eventName, handler);
  }

  function off(eventName, handler) {
    const handlers = eventHandlers.get(eventName);
    if (!handlers) {
      return;
    }

    handlers.delete(handler);
    if (handlers.size === 0) {
      eventHandlers.delete(eventName);
    }
  }

  function onAny(handler) {
    anyHandlers.add(handler);
    return () => offAny(handler);
  }

  function offAny(handler) {
    anyHandlers.delete(handler);
  }

  function getReadyState() {
    return socket?.readyState ?? WebSocket.CLOSED;
  }

  return {
    connect,
    disconnect,
    reconnect,
    send,
    on,
    off,
    onAny,
    offAny,
    getReadyState,
    get socket() {
      return socket;
    },
  };
}
