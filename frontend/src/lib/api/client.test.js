describe("api client", () => {
  beforeEach(() => {
    jest.resetModules();
    delete process.env.REACT_APP_BACKEND_URL;
  });

  test("defaults to localhost backend in development", async () => {
    const { apiClient } = await import("./client");

    expect(apiClient.defaults.baseURL).toBe("http://localhost:8000/api");
  });
});
