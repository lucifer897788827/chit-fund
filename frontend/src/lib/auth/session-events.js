export const SESSION_EXPIRED_EVENT = "chit-fund:session-expired";

export function notifySessionExpired() {
  if (typeof window === "undefined") {
    return;
  }

  window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
}

export function onSessionExpired(handler) {
  if (typeof window === "undefined") {
    return () => {};
  }

  window.addEventListener(SESSION_EXPIRED_EVENT, handler);
  return () => window.removeEventListener(SESSION_EXPIRED_EVENT, handler);
}
