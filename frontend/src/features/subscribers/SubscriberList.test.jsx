import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import SubscriberList from "./SubscriberList";

beforeEach(() => {
  jest.clearAllMocks();
});

test("renders active and deleted subscribers with persistent status badges", async () => {
  const user = userEvent.setup();
  const onEdit = jest.fn();
  const onDeactivate = jest.fn();

  render(
    <SubscriberList
      subscribers={[
        {
          id: 1,
          fullName: "Asha",
          phone: "9000000000",
          email: "asha@example.com",
          status: "active",
        },
        {
          id: 2,
          fullName: "Ravi",
          phone: "8888888888",
          email: "ravi@example.com",
          status: "deleted",
        },
      ]}
      onDeactivate={onDeactivate}
      onEdit={onEdit}
    />,
  );

  expect(screen.getByRole("heading", { name: "Asha" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Ravi" })).toBeInTheDocument();
  expect(screen.getAllByText("Active")[0]).toBeInTheDocument();
  expect(screen.getByText(/Deleted/i)).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "Edit Asha" }));
  await user.click(screen.getByRole("button", { name: "Deactivate Asha" }));

  expect(onEdit).toHaveBeenCalledWith(
    expect.objectContaining({
      id: 1,
      fullName: "Asha",
    }),
  );
  expect(onDeactivate).toHaveBeenCalledWith(
    expect.objectContaining({
      id: 1,
      fullName: "Asha",
    }),
  );
  expect(screen.getByRole("button", { name: "Deactivate Ravi" })).toBeDisabled();
});
