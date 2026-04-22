function collectErrorMessages(value) {
  if (!value) {
    return [];
  }

  if (typeof value === "string") {
    return [value];
  }

  if (Array.isArray(value)) {
    return value.flatMap((item) => collectErrorMessages(item));
  }

  if (typeof value === "object") {
    return ["message", "detail", "error", "non_field_errors"]
      .flatMap((key) => collectErrorMessages(value[key]))
      .filter(Boolean);
  }

  return [String(value)];
}

export function normalizeApiError(error, options = {}) {
  const fallbackMessage =
    options.fallbackMessage ?? "Unable to complete your request right now.";

  if (typeof error === "string") {
    return {
      message: error,
      details: "",
      status: null,
      isNetworkError: false,
      raw: error,
    };
  }

  const response = error?.response;
  const data = response?.data;
  const status = response?.status ?? null;
  const messages = collectErrorMessages(data);
  const message =
    messages[0] ??
    error?.message ??
    fallbackMessage;

  const details = [
    status ? `Request failed with status ${status}.` : "",
    messages.length > 1 ? messages.slice(1).join(" ") : "",
    !status && error?.message && error.message !== message ? error.message : "",
  ]
    .filter(Boolean)
    .join(" ");

  return {
    message,
    details,
    status,
    isNetworkError:
      error?.code === "ERR_NETWORK" ||
      error?.message === "Network Error" ||
      error?.name === "TypeError",
    raw: error,
  };
}

export function getApiErrorMessage(error, options = {}) {
  return normalizeApiError(error, options).message;
}
