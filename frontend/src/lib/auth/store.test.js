import {
  clearSession,
  getAccessToken,
  getCurrentUser,
  getUserRoles,
  isAuthenticated,
  logout,
  saveSession,
} from "./store";

function createJwt(payload) {
  const header = Buffer.from(JSON.stringify({ alg: "HS256", typ: "JWT" })).toString("base64url");
  const body = Buffer.from(JSON.stringify(payload)).toString("base64url");
  return `${header}.${body}.signature`;
}

beforeEach(() => {
  window.localStorage.clear();
});

afterEach(() => {
  window.localStorage.clear();
  jest.restoreAllMocks();
});

test("returns a saved session and exposes its access token", () => {
  const session = {
    access_token: "token-1",
    role: "chit_owner",
    owner_id: 4,
    subscriber_id: 7,
    has_subscriber_profile: true,
  };

  saveSession(session);

  expect(getCurrentUser()).toEqual(session);
  expect(getAccessToken()).toBe("token-1");
  expect(isAuthenticated()).toBe(true);
});

test("keeps a legacy session without an access token available", () => {
  const session = {
    role: "subscriber",
    subscriber_id: 7,
    has_subscriber_profile: true,
  };

  saveSession(session);

  expect(getCurrentUser()).toEqual(session);
  expect(getAccessToken()).toBeNull();
  expect(isAuthenticated()).toBe(true);
});

test("removes an expired jwt session when it is read", () => {
  jest.spyOn(Date, "now").mockReturnValue(new Date("2026-04-20T00:00:00Z").getTime());
  const session = {
    access_token: createJwt({ exp: Math.floor(new Date("2026-04-19T23:59:59Z").getTime() / 1000) }),
    role: "subscriber",
    subscriber_id: 7,
  };

  window.localStorage.setItem("chit-fund-session", JSON.stringify(session));

  expect(getCurrentUser()).toBeNull();
  expect(window.localStorage.getItem("chit-fund-session")).toBeNull();
  expect(isAuthenticated()).toBe(false);
});

test("keeps a session active while the refresh token is still valid", () => {
  jest.spyOn(Date, "now").mockReturnValue(new Date("2026-04-20T00:00:00Z").getTime());
  const session = {
    access_token: createJwt({ exp: Math.floor(new Date("2026-04-19T23:59:59Z").getTime() / 1000) }),
    refresh_token: "refresh-1",
    refresh_token_expires_at: "2026-04-21T00:00:00Z",
    role: "subscriber",
    subscriber_id: 7,
  };

  saveSession(session);

  expect(getCurrentUser()).toEqual(session);
  expect(isAuthenticated()).toBe(true);
});

test("removes a session when the refresh token expires", () => {
  jest.spyOn(Date, "now").mockReturnValue(new Date("2026-04-22T00:00:00Z").getTime());
  const session = {
    access_token: createJwt({ exp: Math.floor(new Date("2026-04-23T23:59:59Z").getTime() / 1000) }),
    refresh_token: "refresh-1",
    refresh_token_expires_at: "2026-04-21T00:00:00Z",
    role: "subscriber",
    subscriber_id: 7,
  };

  window.localStorage.setItem("chit-fund-session", JSON.stringify(session));

  expect(getCurrentUser()).toBeNull();
  expect(window.localStorage.getItem("chit-fund-session")).toBeNull();
  expect(isAuthenticated()).toBe(false);
});

test("removes a malformed session when it is read", () => {
  window.localStorage.setItem("chit-fund-session", "{not-json");

  expect(getCurrentUser()).toBeNull();
  expect(window.localStorage.getItem("chit-fund-session")).toBeNull();
  expect(getAccessToken()).toBeNull();
});

test("removes a malformed jwt session when it is read", () => {
  window.localStorage.setItem(
    "chit-fund-session",
    JSON.stringify({
      access_token: "abc.def.ghi",
      role: "subscriber",
      subscriber_id: 7,
    }),
  );

  expect(getCurrentUser()).toBeNull();
  expect(window.localStorage.getItem("chit-fund-session")).toBeNull();
});

test("logout clears the current session", () => {
  saveSession({
    access_token: "token-1",
    role: "subscriber",
    subscriber_id: 7,
  });

  logout();

  expect(getCurrentUser()).toBeNull();
  expect(isAuthenticated()).toBe(false);
  expect(window.localStorage.getItem("chit-fund-session")).toBeNull();
});

test("clearSession remains available as an alias for logout", () => {
  saveSession({
    access_token: "token-1",
    role: "subscriber",
    subscriber_id: 7,
  });

  clearSession();

  expect(getCurrentUser()).toBeNull();
});

test("treats admin as an exclusive role even when legacy owner or subscriber hints exist", () => {
  const session = {
    access_token: "token-admin",
    role: "admin",
    owner_id: 4,
    subscriber_id: 7,
    has_subscriber_profile: true,
    user: {
      roles: ["admin", "owner", "subscriber"],
    },
  };

  saveSession(session);

  expect(getUserRoles()).toEqual(["admin"]);
});
