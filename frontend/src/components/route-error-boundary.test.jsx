import { render, screen } from "@testing-library/react";

import { RouteErrorBoundary } from "./route-error-boundary";

function CrashOnRender() {
  throw new Error("broken panel");
}

beforeEach(() => {
  jest.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  jest.restoreAllMocks();
});

test("shows a graceful fallback when a route panel crashes", () => {
  render(
    <RouteErrorBoundary>
      <CrashOnRender />
    </RouteErrorBoundary>,
  );

  expect(screen.getByText("Something went wrong.")).toBeInTheDocument();
  expect(screen.getByText(/this page hit a problem/i)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
});
