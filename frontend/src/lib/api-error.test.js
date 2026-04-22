import { getApiErrorMessage, normalizeApiError } from "./api-error";

describe("api error normalization", () => {
  test("prefers backend response messages", () => {
    const normalized = normalizeApiError({
      response: {
        status: 503,
        data: {
          detail: "Service is temporarily unavailable.",
        },
      },
    });

    expect(normalized.message).toBe("Service is temporarily unavailable.");
    expect(normalized.status).toBe(503);
    expect(normalized.details).toContain("503");
  });

  test("falls back to generic error messages", () => {
    const error = new Error("Request failed");

    expect(getApiErrorMessage(error, { fallbackMessage: "Try again later." })).toBe("Request failed");
  });

  test("keeps string errors unchanged", () => {
    const normalized = normalizeApiError("Something went wrong.");

    expect(normalized.message).toBe("Something went wrong.");
    expect(normalized.details).toBe("");
  });
});

