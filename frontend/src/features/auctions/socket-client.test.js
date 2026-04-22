import { saveSession } from "../../lib/auth/store";
import { createAuctionSocket } from "./socket-client";

const originalLocation = window.location;

function setWindowLocation(url) {
  Object.defineProperty(window, "location", {
    configurable: true,
    value: new URL(url),
  });
}

class MockWebSocket {
  static instances = [];

  static reset() {
    MockWebSocket.instances = [];
  }

  constructor(url, protocols = []) {
    this.url = url;
    this.protocols = protocols;
    this.readyState = MockWebSocket.CONNECTING;
    this.sentMessages = [];
    this.closeCalls = [];
    MockWebSocket.instances.push(this);
  }

  triggerOpen() {
    this.readyState = MockWebSocket.OPEN;
    this.onopen?.({ type: "open" });
  }

  triggerMessage(data) {
    this.onmessage?.({ data });
  }

  triggerClose(event = { code: 1000, reason: "closed", wasClean: true }) {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.(event);
  }

  send(message) {
    this.sentMessages.push(message);
  }

  close(code = 1000, reason = "") {
    this.closeCalls.push({ code, reason });
    this.triggerClose({ code, reason, wasClean: code === 1000 });
  }
}

MockWebSocket.CONNECTING = 0;
MockWebSocket.OPEN = 1;
MockWebSocket.CLOSING = 2;
MockWebSocket.CLOSED = 3;

describe("createAuctionSocket", () => {
  const originalWebSocket = global.WebSocket;
  const originalBackendUrl = process.env.REACT_APP_BACKEND_URL;

  beforeEach(() => {
    window.localStorage.clear();
    MockWebSocket.reset();
    global.WebSocket = MockWebSocket;
    process.env.REACT_APP_BACKEND_URL = "https://api.example.com";
    saveSession({ access_token: "token-abc", role: "chit_owner" });
    setWindowLocation("http://localhost/");
  });

  afterEach(() => {
    global.WebSocket = originalWebSocket;
    process.env.REACT_APP_BACKEND_URL = originalBackendUrl;
    window.localStorage.clear();
    Object.defineProperty(window, "location", {
      configurable: true,
      value: originalLocation,
    });
  });

  test("builds the websocket url from the backend origin and sends auth via subprotocol", () => {
    const socket = createAuctionSocket({ sessionId: 42 });

    socket.connect();

    expect(MockWebSocket.instances).toHaveLength(1);
    expect(MockWebSocket.instances[0].url).toBe("wss://api.example.com/ws/auction/42");
    expect(MockWebSocket.instances[0].protocols).toEqual(["access-token", "token-abc"]);
  });

  test("dispatches lifecycle callbacks and named events", () => {
    const onConnect = jest.fn();
    const onDisconnect = jest.fn();
    const onReconnect = jest.fn();
    const onEvent = jest.fn();
    const bidUpdated = jest.fn();

    const socket = createAuctionSocket({
      sessionId: 42,
      onConnect,
      onDisconnect,
      onReconnect,
      onEvent,
    });

    const unsubscribe = socket.on("auction.updated", bidUpdated);
    const firstSocket = socket.connect();

    expect(firstSocket).toBe(MockWebSocket.instances[0]);
    firstSocket.triggerOpen();
    firstSocket.triggerMessage(
      JSON.stringify({
        event: "auction.updated",
        data: { bidAmount: 12000 },
      }),
    );

    unsubscribe();
    socket.reconnect();
    const secondSocket = MockWebSocket.instances[1];
    secondSocket.triggerOpen();
    secondSocket.triggerMessage(
      JSON.stringify({
        type: "auction.updated",
        payload: { bidAmount: 9000 },
      }),
    );

    socket.disconnect();

    expect(onConnect).toHaveBeenCalledTimes(1);
    expect(onReconnect).toHaveBeenCalledTimes(1);
    expect(onDisconnect).toHaveBeenCalledTimes(1);
    expect(onEvent).toHaveBeenCalledWith(
      expect.objectContaining({
        eventName: "auction.updated",
        payload: { bidAmount: 12000 },
      }),
    );
    expect(bidUpdated).toHaveBeenCalledWith(
      expect.objectContaining({
        eventName: "auction.updated",
        payload: { bidAmount: 12000 },
      }),
    );
    expect(onEvent).toHaveBeenCalledWith(
      expect.objectContaining({
        eventName: "auction.updated",
        payload: { bidAmount: 9000 },
      }),
    );
    expect(bidUpdated).toHaveBeenCalledTimes(1);
    expect(secondSocket.closeCalls).toHaveLength(1);
  });

  test("falls back to the current origin when no backend url is configured", () => {
    delete process.env.REACT_APP_BACKEND_URL;

    const socket = createAuctionSocket({ sessionId: 7 });
    socket.connect();

    expect(MockWebSocket.instances[0].url).toBe("ws://localhost:8000/ws/auction/7");
    expect(MockWebSocket.instances[0].protocols).toEqual(["access-token", "token-abc"]);
  });

  test("keeps 127.0.0.1 aligned for local websocket fallback", () => {
    delete process.env.REACT_APP_BACKEND_URL;
    setWindowLocation("http://127.0.0.1:4173/");

    const socket = createAuctionSocket({ sessionId: 7 });
    socket.connect();

    expect(MockWebSocket.instances[0].url).toBe("ws://127.0.0.1:8000/ws/auction/7");
    expect(MockWebSocket.instances[0].protocols).toEqual(["access-token", "token-abc"]);
  });
});
