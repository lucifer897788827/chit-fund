import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import {
  AsyncSectionState,
  PageErrorState,
  PageLoadingState,
  SectionEmptyState,
  SectionErrorState,
  SectionLoadingState,
} from "./page-state";

test("renders a loading state with a label and description", () => {
  render(<PageLoadingState label="Loading groups..." description="Fetching the latest group list." />);

  expect(screen.getByRole("status", { name: "Loading groups..." })).toBeInTheDocument();
  expect(screen.queryByText("Loading groups...")).not.toBeInTheDocument();
  expect(screen.queryByText("Fetching the latest group list.")).not.toBeInTheDocument();
  expect(document.querySelectorAll(".skeleton-card").length).toBeGreaterThan(0);
});

test("renders a section empty state with an action button", async () => {
  const user = userEvent.setup();
  const onRefresh = jest.fn();

  render(
    <SectionEmptyState
      actionLabel="Refresh list"
      description="There are no payment entries yet."
      onAction={onRefresh}
      title="No payments yet"
    />,
  );

  expect(screen.getByText("No payments yet")).toBeInTheDocument();
  expect(screen.getByText("There are no payment entries yet.")).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "Refresh list" }));
  expect(onRefresh).toHaveBeenCalledTimes(1);
});

test("renders a section error state with a retry button", async () => {
  const user = userEvent.setup();
  const onRetry = jest.fn();

  render(
    <SectionErrorState
      error={{
        response: {
          status: 503,
          data: { message: "Service is unavailable." },
        },
      }}
      onRetry={onRetry}
      retryLabel="Reload history"
      title="History failed to load."
    />,
  );

  expect(screen.getByText("History failed to load.")).toBeInTheDocument();
  expect(screen.getByText("Service is unavailable.")).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "Reload history" }));
  expect(onRetry).toHaveBeenCalledTimes(1);
});

test("switches between loading, empty, and content in async section state", () => {
  const { rerender } = render(
    <AsyncSectionState
      empty
      emptyDescription="Add the first record to get started."
      emptyTitle="Nothing to show"
      loading
      loadingDescription="Fetching records."
      loadingLabel="Loading records..."
      onEmptyAction={jest.fn()}
      onRetry={jest.fn()}
    >
      <p>Rendered content</p>
    </AsyncSectionState>,
  );

  expect(screen.getByRole("status", { name: "Loading records..." })).toBeInTheDocument();
  expect(screen.queryByText("Loading records...")).not.toBeInTheDocument();
  expect(screen.queryByText("Nothing to show")).not.toBeInTheDocument();
  expect(screen.queryByText("Rendered content")).not.toBeInTheDocument();

  rerender(
    <AsyncSectionState
      empty
      emptyDescription="Add the first record to get started."
      emptyTitle="Nothing to show"
      loading={false}
      onEmptyAction={jest.fn()}
      onRetry={jest.fn()}
    >
      <p>Rendered content</p>
    </AsyncSectionState>,
  );

  expect(screen.getByText("Nothing to show")).toBeInTheDocument();
  expect(screen.getByText("Add the first record to get started.")).toBeInTheDocument();
  expect(screen.queryByText("Rendered content")).not.toBeInTheDocument();

  rerender(
    <AsyncSectionState loading={false} empty={false}>
      <p>Rendered content</p>
    </AsyncSectionState>,
  );

  expect(screen.getByText("Rendered content")).toBeInTheDocument();
});

test("renders a normalized error and retry action", async () => {
  const user = userEvent.setup();
  const onRetry = jest.fn();

  render(
    <PageErrorState
      error={{
        response: {
          status: 500,
          data: { message: "Unable to load groups right now." },
        },
      }}
      onRetry={onRetry}
    />,
  );

  expect(screen.getByText("We could not load this page.")).toBeInTheDocument();
  expect(screen.getByText("Unable to load groups right now.")).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "Retry" }));
  expect(onRetry).toHaveBeenCalledTimes(1);
});

test("renders section loading state with section-scoped copy", () => {
  render(
    <SectionLoadingState
      description="Fetching the latest payment entries for this panel."
      label="Loading payment history..."
    />,
  );

  expect(screen.getByRole("status", { name: "Loading payment history..." })).toBeInTheDocument();
  expect(screen.queryByText("Loading payment history...")).not.toBeInTheDocument();
  expect(screen.queryByText("Fetching the latest payment entries for this panel.")).not.toBeInTheDocument();
});
