import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import {
  createSubscriber,
  deactivateSubscriber,
  fetchSubscribers,
  updateSubscriber,
} from "./api";

jest.mock("./api", () => ({
  createSubscriber: jest.fn(),
  deactivateSubscriber: jest.fn(),
  fetchSubscribers: jest.fn(),
  updateSubscriber: jest.fn(),
}));

import SubscriberManagementPanel from "./SubscriberManagementPanel";

beforeEach(() => {
  jest.clearAllMocks();
  window.confirm = jest.fn();
});

test("loads subscribers and creates a new subscriber without leaving the list", async () => {
  const user = userEvent.setup();

  fetchSubscribers.mockResolvedValueOnce([
    {
      id: 1,
      fullName: "Asha",
      phone: "9000000000",
      email: "asha@example.com",
      status: "active",
    },
  ]);
  createSubscriber.mockResolvedValueOnce({
    id: 2,
    ownerId: 17,
    fullName: "Leela",
    phone: "8111111111",
    email: "leela@example.com",
    status: "active",
  });

  render(<SubscriberManagementPanel ownerId={17} />);

  expect(screen.getByRole("status", { name: "Loading subscribers..." })).toBeInTheDocument();
  expect(await screen.findByRole("heading", { name: "Subscribers" })).toBeInTheDocument();

  await user.type(screen.getByLabelText("Full name"), "Leela");
  await user.type(screen.getByLabelText("Phone"), "8111111111");
  await user.type(screen.getByLabelText("Email"), "leela@example.com");
  await user.type(screen.getByLabelText("Temporary password"), "starter-pass");
  await user.click(screen.getByRole("button", { name: "Create subscriber" }));

  await waitFor(() => {
    expect(createSubscriber).toHaveBeenCalledWith(
      expect.objectContaining({
        ownerId: 17,
        fullName: "Leela",
        phone: "8111111111",
        email: "leela@example.com",
        password: "starter-pass",
      }),
    );
  });

  expect(await screen.findByText(/Subscriber created/i)).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Leela" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Asha" })).toBeInTheDocument();
});

test("edits a subscriber in place and keeps the row visible after save", async () => {
  const user = userEvent.setup();

  fetchSubscribers.mockResolvedValueOnce([
    {
      id: 7,
      fullName: "Ravi Kumar",
      phone: "8888888888",
      email: "ravi@example.com",
      status: "active",
    },
  ]);
  updateSubscriber.mockResolvedValueOnce({
    id: 7,
    ownerId: 17,
    fullName: "Ravi K",
    phone: "8888888888",
    email: "ravi@example.com",
    status: "active",
  });

  render(<SubscriberManagementPanel ownerId={17} />);

  await screen.findByRole("heading", { name: "Subscribers" });
  await user.click(screen.getByRole("button", { name: "Edit Ravi Kumar" }));

  expect(screen.getByRole("heading", { name: "Edit subscriber" })).toBeInTheDocument();
  expect(screen.getByLabelText("Full name")).toHaveValue("Ravi Kumar");

  await user.clear(screen.getByLabelText("Full name"));
  await user.type(screen.getByLabelText("Full name"), "Ravi K");
  await user.click(screen.getByRole("button", { name: "Save changes" }));

  await waitFor(() => {
    expect(updateSubscriber).toHaveBeenCalledWith(
      7,
      expect.objectContaining({
        ownerId: 17,
        fullName: "Ravi K",
        phone: "8888888888",
        email: "ravi@example.com",
      }),
    );
  });

  expect(await screen.findByText(/Subscriber updated/i)).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Ravi K" })).toBeInTheDocument();
});

test("soft-deletes a subscriber after confirmation and keeps it visible", async () => {
  const user = userEvent.setup();

  fetchSubscribers.mockResolvedValueOnce([
    {
      id: 9,
      fullName: "Asha",
      phone: "9000000000",
      email: "asha@example.com",
      status: "active",
    },
  ]);
  deactivateSubscriber.mockResolvedValueOnce({
    id: 9,
    ownerId: 17,
    fullName: "Asha",
    phone: "9000000000",
    email: "asha@example.com",
    status: "deleted",
  });
  window.confirm.mockReturnValueOnce(true);

  render(<SubscriberManagementPanel ownerId={17} />);

  await screen.findByRole("heading", { name: "Subscribers" });
  await user.click(screen.getByRole("button", { name: "Deactivate Asha" }));

  expect(window.confirm).toHaveBeenCalled();
  await waitFor(() => {
    expect(deactivateSubscriber).toHaveBeenCalledWith(9);
  });

  expect(await screen.findByText(/Subscriber deactivated/i)).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Asha" })).toBeInTheDocument();
  expect(screen.getByText("Deleted")).toBeInTheDocument();
});

test("shows a retryable error when loading fails", async () => {
  const user = userEvent.setup();

  fetchSubscribers.mockRejectedValueOnce({
    response: {
      data: {
        detail: "Unable to load subscribers right now.",
      },
    },
  });
  fetchSubscribers.mockResolvedValueOnce([]);

  render(<SubscriberManagementPanel ownerId={17} />);

  expect(await screen.findByText(/Unable to load subscribers right now/i)).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Retry" }));

  expect(await screen.findByRole("heading", { name: "Subscribers" })).toBeInTheDocument();
});
