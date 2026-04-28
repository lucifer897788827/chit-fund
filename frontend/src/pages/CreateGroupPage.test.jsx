import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import CreateGroupPage from "./CreateGroupPage";
import { createGroup } from "../features/auctions/api";
import { getCurrentUser } from "../lib/auth/store";

const mockNavigate = jest.fn();

jest.mock("react-router-dom", () => ({
  ...jest.requireActual("react-router-dom"),
  useNavigate: () => mockNavigate,
}));

jest.mock("../components/app-shell", () => ({
  useAppShellHeader: jest.fn(),
}));

jest.mock("../features/auctions/api", () => ({
  createGroup: jest.fn(),
}));

jest.mock("../lib/auth/store", () => ({
  getCurrentUser: jest.fn(),
}));

beforeEach(() => {
  jest.clearAllMocks();
  getCurrentUser.mockReturnValue({ owner_id: 1 });
  createGroup.mockResolvedValue({ id: 42 });
});

test("submits group configuration fields with auto cycle calculation enabled", async () => {
  render(
    <MemoryRouter>
      <CreateGroupPage />
    </MemoryRouter>,
  );

  fireEvent.change(screen.getByLabelText("Group code"), { target: { value: "CFG-001" } });
  fireEvent.change(screen.getByLabelText("Title"), { target: { value: "Configured Group" } });
  fireEvent.change(screen.getByLabelText("Chit value"), { target: { value: "600000" } });
  fireEvent.change(screen.getByLabelText("Installment amount"), { target: { value: "25000" } });
  fireEvent.change(screen.getByLabelText("Member count"), { target: { value: "24" } });
  fireEvent.change(screen.getByLabelText("Cycle count"), { target: { value: "12" } });
  fireEvent.change(screen.getByLabelText("Cycle frequency"), { target: { value: "monthly" } });
  fireEvent.change(screen.getByLabelText("Commission type"), { target: { value: "FIRST_MONTH" } });
  fireEvent.change(screen.getByLabelText("Auction type"), { target: { value: "BLIND" } });
  fireEvent.change(screen.getByLabelText("Group type"), { target: { value: "MULTI_SLOT" } });
  fireEvent.click(screen.getByLabelText("Auto-calculate cycle count"));
  fireEvent.change(screen.getByLabelText("Start date"), { target: { value: "2026-05-01" } });
  fireEvent.change(screen.getByLabelText("First auction date"), { target: { value: "2026-05-10" } });

  fireEvent.click(screen.getByRole("button", { name: "Create group" }));

  await waitFor(() =>
    expect(createGroup).toHaveBeenCalledWith({
      ownerId: 1,
      groupCode: "CFG-001",
      title: "Configured Group",
      chitValue: 600000,
      installmentAmount: 25000,
      memberCount: 24,
      cycleCount: 12,
      autoCycleCalculation: true,
      cycleFrequency: "monthly",
      commissionType: "FIRST_MONTH",
      auctionType: "BLIND",
      groupType: "MULTI_SLOT",
      visibility: "private",
      startDate: "2026-05-01",
      firstAuctionDate: "2026-05-10",
    }),
  );
  expect(mockNavigate).toHaveBeenCalledWith("/groups/42");
});
