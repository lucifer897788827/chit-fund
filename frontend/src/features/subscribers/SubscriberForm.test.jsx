import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import SubscriberForm from "./SubscriberForm";

beforeEach(() => {
  jest.clearAllMocks();
});

test("submits a new subscriber draft including the owner id and password", async () => {
  const user = userEvent.setup();
  const onSubmit = jest.fn();

  render(<SubscriberForm mode="create" ownerId={17} onSubmit={onSubmit} />);

  await user.type(screen.getByLabelText("Full name"), "Asha");
  await user.type(screen.getByLabelText("Phone"), "9000000000");
  await user.type(screen.getByLabelText("Email"), "asha@example.com");
  await user.type(screen.getByLabelText("Temporary password"), "starter-pass");

  await user.click(screen.getByRole("button", { name: "Create subscriber" }));

  expect(onSubmit).toHaveBeenCalledWith({
    ownerId: 17,
    fullName: "Asha",
    phone: "9000000000",
    email: "asha@example.com",
    password: "starter-pass",
  });
});

test("prefills the edit form and omits the password field", async () => {
  const user = userEvent.setup();
  const onSubmit = jest.fn();

  render(
    <SubscriberForm
      mode="edit"
      ownerId={17}
      subscriber={{
        id: 9,
        fullName: "Ravi Kumar",
        phone: "8888888888",
        email: "ravi@example.com",
        status: "active",
      }}
      onSubmit={onSubmit}
    />,
  );

  expect(screen.queryByLabelText("Temporary password")).not.toBeInTheDocument();
  expect(screen.getByLabelText("Full name")).toHaveValue("Ravi Kumar");
  expect(screen.getByLabelText("Phone")).toHaveValue("8888888888");
  expect(screen.getByLabelText("Email")).toHaveValue("ravi@example.com");

  await user.clear(screen.getByLabelText("Full name"));
  await user.type(screen.getByLabelText("Full name"), "Ravi K");
  await user.click(screen.getByRole("button", { name: "Save changes" }));

  expect(onSubmit).toHaveBeenCalledWith({
    ownerId: 17,
    fullName: "Ravi K",
    phone: "8888888888",
    email: "ravi@example.com",
  });
});
