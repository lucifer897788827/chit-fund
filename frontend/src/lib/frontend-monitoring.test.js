import { installFrontendErrorCapture } from "./frontend-monitoring";

describe("frontend error capture", () => {
  test("captures console errors with a lightweight tagged log", () => {
    const originalConsoleError = jest.fn();
    const consoleRef = { error: originalConsoleError };

    const uninstall = installFrontendErrorCapture({ consoleRef, windowRef: undefined });
    consoleRef.error("render failed", { detail: "boom" });
    uninstall();

    expect(originalConsoleError).toHaveBeenCalledWith("CONSOLE ERROR:", "render failed", { detail: "boom" });
  });
});
