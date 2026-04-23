const mockAxiosPost = jest.fn();
const originalLocation = window.location;

function setWindowLocation(url) {
  Object.defineProperty(window, "location", {
    configurable: true,
    value: new URL(url),
  });
}

function mockCreateAxiosInstance() {
  const instance = jest.fn();
  instance.interceptors = {
    request: {
      use: jest.fn((handler) => {
        instance.requestHandler = handler;
      }),
    },
    response: {
      use: jest.fn((fulfilled, rejected) => {
        instance.responseRejectedHandler = rejected;
        instance.responseFulfilledHandler = fulfilled;
      }),
    },
  };
  return instance;
}

jest.mock("axios", () => {
  const create = jest.fn(() => mockCreateAxiosInstance());
  return {
    __esModule: true,
    default: {
      create,
      post: mockAxiosPost,
    },
    create,
    post: mockAxiosPost,
  };
});

jest.mock("../auth/store", () => ({
  clearSession: jest.fn(),
  getCurrentUser: jest.fn(),
  getRefreshToken: jest.fn(),
  saveSession: jest.fn(),
}));

jest.mock("../auth/session-events", () => ({
  notifySessionExpired: jest.fn(),
}));

describe("apiClient refresh handling", () => {
  beforeEach(() => {
    jest.resetModules();
    jest.clearAllMocks();
    setWindowLocation("http://localhost/");
  });

  afterAll(() => {
    Object.defineProperty(window, "location", {
      configurable: true,
      value: originalLocation,
    });
  });

  test("attaches the access token to outgoing requests", () => {
    const store = require("../auth/store");
    store.getCurrentUser.mockReturnValue({
      access_token: "access-token-1",
    });

    const { apiClient } = require("./client");
    const requestConfig = apiClient.requestHandler({
      url: "/groups",
      headers: {},
    });

    expect(requestConfig.headers.Authorization).toBe("Bearer access-token-1");
  });

  test("clears the session when refresh fails", async () => {
    const store = require("../auth/store");
    const sessionEvents = require("../auth/session-events");
    store.getCurrentUser.mockReturnValue({
      access_token: "expired-access",
      refresh_token: "refresh-token-1",
    });
    store.getRefreshToken.mockReturnValue("refresh-token-1");
    mockAxiosPost.mockRejectedValue(new Error("refresh failed"));

    const { apiClient } = require("./client");

    await expect(
      apiClient.responseRejectedHandler({
        response: { status: 401 },
        config: {
          url: "/payments",
          headers: {},
        },
      }),
    ).rejects.toMatchObject({
      response: { status: 401 },
    });

    expect(store.clearSession).toHaveBeenCalledTimes(1);
    expect(sessionEvents.notifySessionExpired).toHaveBeenCalledTimes(1);
  });

  test("uses the current local host for the backend fallback", () => {
    delete process.env.REACT_APP_BACKEND_URL;
    setWindowLocation("http://127.0.0.1:4173/");

    const axiosModule = require("axios");
    require("./client");

    expect(axiosModule.create).toHaveBeenCalledWith({
      baseURL: "http://127.0.0.1:8000/api",
    });
  });

  test("uses the current network host for frontend dev ports", () => {
    delete process.env.REACT_APP_BACKEND_URL;
    setWindowLocation("http://192.168.1.50:3000/");

    const axiosModule = require("axios");
    require("./client");

    expect(axiosModule.create).toHaveBeenCalledWith({
      baseURL: "http://192.168.1.50:8000/api",
    });
  });
});
