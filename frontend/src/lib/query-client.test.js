import { queryClient } from "./query-client";

test("configures React Query with fast cached defaults", () => {
  const defaultOptions = queryClient.getDefaultOptions();

  expect(defaultOptions.queries.staleTime).toBe(30_000);
  expect(defaultOptions.queries.retry).toBe(1);
  expect(defaultOptions.queries.refetchOnWindowFocus).toBe(true);
});
