import { getApiErrorMessage, normalizeApiError } from "./api-error";

describe("api error normalization", () => {
  test("prefers backend response messages", () => {
    const normalized = normalizeApiError({
      response: {
        status: 503,
        data: {
          error: "Service is temporarily unavailable.",
          detail: "Service is temporarily unavailable.",
        },
      },
    });

    expect(normalized.message).toBe("Service is temporarily unavailable.");
    expect(normalized.status).toBe(503);
    expect(normalized.details).toContain("503");
  });

  test("prefers standardized backend error fields over detail payloads", () => {
    const normalized = normalizeApiError({
      response: {
        status: 422,
        data: {
          error: "Request validation failed.",
          detail: [{ msg: "Field required" }],
        },
      },
    });

    expect(normalized.message).toBe("Request validation failed.");
    expect(normalized.details).toContain("Field required");
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
