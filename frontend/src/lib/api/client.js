import axios from "axios";

function getBackendUrl() {
  if (process.env.REACT_APP_BACKEND_URL) {
    return process.env.REACT_APP_BACKEND_URL;
  }

  if (typeof window !== "undefined") {
    const hostname = window.location.hostname || "localhost";
    if (hostname === "localhost" || hostname === "127.0.0.1") {
      return "http://localhost:8000";
    }
  }

  return "";
}

const BACKEND_URL = getBackendUrl();

export const apiClient = axios.create({
  baseURL: `${BACKEND_URL}/api`,
});
