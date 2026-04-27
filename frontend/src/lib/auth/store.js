const SESSION_KEY = "chit-fund-session";

function parseJson(rawSession) {
  try {
    return JSON.parse(rawSession);
  } catch (_error) {
    return null;
  }
}

function decodeBase64Url(input) {
  const normalized = input.replace(/-/g, "+").replace(/_/g, "/");
  const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, "=");

  try {
    if (typeof atob === "function") {
      return atob(padded);
    }

    if (typeof Buffer !== "undefined") {
      return Buffer.from(padded, "base64").toString("utf8");
    }
  } catch (_error) {
    return null;
  }

  return null;
}

function getJwtPayload(accessToken) {
  if (typeof accessToken !== "string") {
    return null;
  }

  const tokenParts = accessToken.split(".");
  if (tokenParts.length < 2) {
    return null;
  }

  const payload = decodeBase64Url(tokenParts[1]);
  if (!payload) {
    return null;
  }

  return parseJson(payload);
}

function toTimestampMillis(value) {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value > 1e12 ? value : value * 1000;
  }

  if (typeof value === "string" && value.trim()) {
    const parsed = Date.parse(value);
    if (!Number.isNaN(parsed)) {
      return parsed;
    }
  }

  return null;
}

function getRefreshTokenExpiresAt(session) {
  return (
    toTimestampMillis(session?.refresh_token_expires_at) ??
    toTimestampMillis(session?.refreshTokenExpiresAt) ??
    toTimestampMillis(session?.refresh_expires_at) ??
    toTimestampMillis(session?.refreshExpiresAt)
  );
}

function isSessionExpired(session) {
  const refreshTokenExpiresAt = getRefreshTokenExpiresAt(session);
  if (refreshTokenExpiresAt !== null) {
    return refreshTokenExpiresAt <= Date.now();
  }

  const accessToken = session?.access_token ?? session?.token;
  if (typeof accessToken !== "string" || !accessToken) {
    return false;
  }

  const tokenParts = accessToken.split(".");
  if (tokenParts.length < 2) {
    return false;
  }

  const payload = getJwtPayload(accessToken);
  if (!payload) {
    return true;
  }

  if (typeof payload.exp !== "number") {
    return false;
  }

  return payload.exp * 1000 <= Date.now();
}

function readSession() {
  if (typeof window === "undefined") {
    return null;
  }

  const rawSession = window.localStorage.getItem(SESSION_KEY);
  if (!rawSession) {
    return null;
  }

  const session = parseJson(rawSession);
  if (!session || typeof session !== "object" || Array.isArray(session)) {
    window.localStorage.removeItem(SESSION_KEY);
    return null;
  }

  if (isSessionExpired(session)) {
    window.localStorage.removeItem(SESSION_KEY);
    return null;
  }

  return session;
}

function normalizeRoles(value) {
  if (!Array.isArray(value)) {
    return [];
  }

  const seen = new Set();
  return value.filter((role) => {
    if (typeof role !== "string" || !role.trim() || seen.has(role)) {
      return false;
    }
    seen.add(role);
    return true;
  });
}

export function getUserRoles(session = readSession()) {
  const explicitRoles = normalizeRoles(session?.user?.roles);
  if (explicitRoles.includes("admin")) {
    return ["admin"];
  }
  if (explicitRoles.length > 0) {
    return explicitRoles;
  }

  if (session?.role === "admin") {
    return ["admin"];
  }

  const legacyRoles = [];
  if (
    session?.role === "subscriber" ||
    session?.subscriber_id ||
    session?.subscriberId ||
    session?.has_subscriber_profile ||
    session?.hasSubscriberProfile
  ) {
    legacyRoles.push("subscriber");
  }
  if (session?.role === "chit_owner" || session?.role === "owner" || session?.owner_id || session?.ownerId) {
    legacyRoles.push("owner");
  }
  return normalizeRoles(legacyRoles);
}

export function sessionHasRole(session, role) {
  return getUserRoles(session).includes(role);
}

export function getDashboardPath(session = readSession()) {
  if (sessionHasRole(session, "admin")) {
    return "/admin";
  }
  if (sessionHasRole(session, "owner")) {
    return "/home";
  }
  if (sessionHasRole(session, "subscriber")) {
    return "/home";
  }
  return "/";
}

export function getCurrentUser() {
  return readSession();
}

export function getAccessToken() {
  const session = readSession();
  return session?.access_token ?? session?.accessToken ?? session?.token ?? null;
}

export function getRefreshToken() {
  const session = readSession();
  return session?.refresh_token ?? session?.refreshToken ?? null;
}

export function isAuthenticated() {
  return Boolean(readSession());
}

export function saveSession(session) {
  if (typeof window === "undefined") {
    return;
  }

  if (!session || typeof session !== "object" || Array.isArray(session)) {
    window.localStorage.removeItem(SESSION_KEY);
    return;
  }

  window.localStorage.setItem(SESSION_KEY, JSON.stringify(session));
}

export function mergeSession(currentSession, nextSession) {
  if (!nextSession || typeof nextSession !== "object" || Array.isArray(nextSession)) {
    return currentSession ?? null;
  }

  return {
    ...(currentSession ?? {}),
    ...nextSession,
    user: {
      ...((currentSession ?? {}).user ?? {}),
      ...(nextSession.user ?? {}),
    },
  };
}

export function updateSession(nextSession) {
  if (typeof window === "undefined") {
    return mergeSession(null, nextSession);
  }

  const currentSession = readSession() ?? {};
  const mergedSession = mergeSession(currentSession, nextSession);
  saveSession(mergedSession);
  return mergedSession;
}

export function logout() {
  if (typeof window === "undefined") {
    return;
  }

  window.localStorage.removeItem(SESSION_KEY);
  window.sessionStorage.removeItem(SESSION_KEY);
}

export function clearSession() {
  logout();
}
