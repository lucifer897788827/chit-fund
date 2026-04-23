import axios from "axios";

import { clearSession, getCurrentUser, getRefreshToken, updateSession } from "../auth/store";
import { notifySessionExpired } from "../auth/session-events";

function getBackendUrl() {
  if (process.env.REACT_APP_BACKEND_URL) {
    return process.env.REACT_APP_BACKEND_URL.trim().replace(/\/+$/, "");
  }

  if (typeof window !== "undefined") {
    const hostname = window.location.hostname || "localhost";
    const frontendPort = window.location.port;
    const isFrontendDevPort = frontendPort === "3000" || frontendPort === "4173";
    if (hostname === "localhost" || hostname === "127.0.0.1" || isFrontendDevPort) {
      return `${window.location.protocol}//${hostname}:8000`;
    }
  }

  return "";
}

const BACKEND_URL = getBackendUrl();

function getAccessToken() {
  const session = getCurrentUser();
  if (!session) {
    return null;
  }

  return session.access_token || session.token || null;
}

function shouldSkipRefresh(config) {
  const url = config?.url || "";
  return (
    url.includes("/auth/login") ||
    url.includes("/auth/signup") ||
    url.includes("/auth/request-reset") ||
    url.includes("/auth/confirm-reset") ||
    url.includes("/auth/refresh") ||
    url.includes("/auth/logout")
  );
}

function attachAuthorizationHeader(config) {
  const token = getAccessToken();
  if (!token) {
    return config;
  }

  if (!config.headers) {
    config.headers = {};
  }

  if (typeof config.headers.set === "function") {
    config.headers.set("Authorization", `Bearer ${token}`);
    return config;
  }

  config.headers.Authorization = `Bearer ${token}`;
  return config;
}

let refreshPromise = null;

async function refreshAccessToken() {
  const refreshToken = getRefreshToken();
  if (!refreshToken) {
    throw new Error("Missing refresh token");
  }

  if (!refreshPromise) {
    refreshPromise = axios
      .post(`${BACKEND_URL}/api/auth/refresh`, {
        refresh_token: refreshToken,
      })
      .then((response) => {
        updateSession(response.data);
        return response.data;
      })
      .finally(() => {
        refreshPromise = null;
      });
  }

  return refreshPromise;
}

async function handleUnauthorizedResponse(error) {
  const statusCode = error?.response?.status;
  const originalRequest = error?.config;
  const currentSession = getCurrentUser();

  if (statusCode !== 401 || !originalRequest || !currentSession || originalRequest._retry || shouldSkipRefresh(originalRequest)) {
    return Promise.reject(error);
  }

  try {
    originalRequest._retry = true;
    const refreshedSession = await refreshAccessToken();

    if (!originalRequest.headers) {
      originalRequest.headers = {};
    }

    originalRequest.headers.Authorization = `Bearer ${refreshedSession.access_token}`;
    return apiClient(originalRequest);
  } catch (_refreshError) {
    clearSession();
    notifySessionExpired();
    return Promise.reject(error);
  }
}

export const apiClient = axios.create({
  baseURL: `${BACKEND_URL}/api`,
});

apiClient.interceptors.request.use(attachAuthorizationHeader);
apiClient.interceptors.response.use((response) => response, handleUnauthorizedResponse);
