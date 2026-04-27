let installed = false;

export function installFrontendErrorCapture({
  consoleRef = console,
  windowRef = typeof window !== "undefined" ? window : undefined,
} = {}) {
  if (installed || !consoleRef?.error) {
    return () => {};
  }

  installed = true;
  const originalConsoleError = consoleRef.error.bind(consoleRef);

  consoleRef.error = (...args) => {
    if (args[0] === "CONSOLE ERROR:" || (typeof args[0] === "string" && args[0].startsWith("API ERROR:"))) {
      originalConsoleError(...args);
      return;
    }
    originalConsoleError("CONSOLE ERROR:", ...args);
  };

  const onWindowError = (event) => {
    originalConsoleError("CONSOLE ERROR:", event?.message || "Window error");
  };
  const onUnhandledRejection = (event) => {
    originalConsoleError("CONSOLE ERROR:", event?.reason?.message || event?.reason || "Unhandled rejection");
  };

  windowRef?.addEventListener?.("error", onWindowError);
  windowRef?.addEventListener?.("unhandledrejection", onUnhandledRejection);

  return () => {
    consoleRef.error = originalConsoleError;
    windowRef?.removeEventListener?.("error", onWindowError);
    windowRef?.removeEventListener?.("unhandledrejection", onUnhandledRejection);
    installed = false;
  };
}
