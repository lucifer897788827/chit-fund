import { apiClient } from "../../lib/api/client";
import { clearSession, getRefreshToken } from "../../lib/auth/store";

export async function loginUser(payload) {
  const { data } = await apiClient.post("/auth/login", payload);
  return data;
}

export async function signupUser(payload) {
  const { data } = await apiClient.post("/auth/signup", payload);
  return data;
}

export async function requestPasswordReset(payload) {
  const { data } = await apiClient.post("/auth/request-reset", payload);
  return data;
}

export async function confirmPasswordReset(payload) {
  const { data } = await apiClient.post("/auth/confirm-reset", payload);
  return data;
}

export async function refreshSession(payload = {}) {
  const refreshToken = payload.refresh_token ?? payload.refreshToken ?? getRefreshToken();
  const { data } = await apiClient.post("/auth/refresh", {
    refresh_token: refreshToken,
  });
  return data;
}

export async function fetchCurrentUser() {
  const { data } = await apiClient.get("/auth/me");
  return data;
}

export async function logoutUser() {
  try {
    await apiClient.post("/auth/logout", {
      refresh_token: getRefreshToken(),
    });
  } finally {
    clearSession();
  }
}
