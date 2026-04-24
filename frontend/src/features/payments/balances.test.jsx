import { render, screen } from "@testing-library/react";

import {
  buildMemberBalanceSummary,
  formatMoney,
  MemberBalanceSummary,
} from "./balances";

test("formatMoney renders Indian rupee amounts with grouping", () => {
  expect(formatMoney(12500)).toBe("Rs. 12,500");
});

test("buildMemberBalanceSummary calculates outstanding and credit amounts", () => {
  expect(
    buildMemberBalanceSummary({
      memberName: "Anita",
      groupTitle: "April Prosperity Chit",
      totalDue: 25000,
      totalPaid: 15750,
    }),
  ).toEqual({
    memberName: "Anita",
    groupTitle: "April Prosperity Chit",
    slotCount: null,
    totalDue: 25000,
    totalPaid: 15750,
    outstandingAmount: 9250,
    creditAmount: 0,
    balanceState: "outstanding",
    paymentStatus: null,
    penaltyAmount: 0,
    arrearsAmount: 0,
    nextDueAmount: null,
    nextDueDate: null,
    monthlyInstallmentAmount: null,
    shareReceivedAmount: null,
    finalPayableAmount: 9250,
    totalPayableAmount: 9250,
    remainingAmount: 0,
    progress: {
      totalDue: 9250,
      totalPaid: 15750,
      remainingAmount: 0,
      percent: 100,
      percentLabel: "100%",
    },
    tone: {
      badge: "border-rose-200 bg-rose-50 text-rose-900",
      amount: "text-rose-700",
      accent: "bg-rose-500",
      surface: "border-rose-200 bg-rose-50/60",
    },
    dueLabel: "Rs. 25,000",
    paidLabel: "Rs. 15,750",
    outstandingLabel: "Rs. 9,250",
    creditLabel: null,
    penaltyLabel: null,
    arrearsLabel: "Rs. 0",
    nextDueAmountLabel: null,
    nextDueDateLabel: null,
    monthlyInstallmentLabel: null,
    shareReceivedLabel: null,
    finalPayableLabel: "Rs. 9,250",
    totalPayableLabel: "Rs. 9,250",
    remainingAmountLabel: "Rs. 0",
    progressLabel: "Rs. 15,750 paid / Rs. 0 remaining",
  });
});

test("buildMemberBalanceSummary reports credit when paid exceeds due", () => {
  expect(
    buildMemberBalanceSummary({
      memberName: "Ravi",
      groupTitle: "July Chit",
      totalDue: 10000,
      totalPaid: 12500,
    }),
  ).toEqual({
    memberName: "Ravi",
    groupTitle: "July Chit",
    slotCount: null,
    totalDue: 10000,
    totalPaid: 12500,
    outstandingAmount: 0,
    creditAmount: 2500,
    balanceState: "credit",
    paymentStatus: null,
    penaltyAmount: 0,
    arrearsAmount: 0,
    nextDueAmount: null,
    nextDueDate: null,
    monthlyInstallmentAmount: null,
    shareReceivedAmount: null,
    finalPayableAmount: 0,
    totalPayableAmount: 0,
    remainingAmount: 0,
    progress: {
      totalDue: 10000,
      totalPaid: 12500,
      remainingAmount: 0,
      percent: 100,
      percentLabel: "100%",
    },
    tone: {
      badge: "border-emerald-200 bg-emerald-50 text-emerald-900",
      amount: "text-emerald-700",
      accent: "bg-emerald-500",
      surface: "border-emerald-200 bg-emerald-50/60",
    },
    dueLabel: "Rs. 10,000",
    paidLabel: "Rs. 12,500",
    outstandingLabel: "Rs. 0",
    creditLabel: "Rs. 2,500",
    penaltyLabel: null,
    arrearsLabel: "Rs. 0",
    nextDueAmountLabel: null,
    nextDueDateLabel: null,
    monthlyInstallmentLabel: null,
    shareReceivedLabel: null,
    finalPayableLabel: "Rs. 0",
    totalPayableLabel: "Rs. 0",
    remainingAmountLabel: "Rs. 0",
    progressLabel: "Rs. 12,500 paid / Rs. 0 remaining",
  });
});

test("buildMemberBalanceSummary preserves provided dues fields and labels", () => {
  expect(
    buildMemberBalanceSummary({
      memberName: "Farah",
      groupTitle: "Harvest Chit",
      totalDue: 24000,
      totalPaid: 18000,
      outstandingAmount: 6000,
      paymentStatus: "partial",
      penaltyAmount: 1200,
      arrearsAmount: 2500,
      nextDueAmount: 3500,
      nextDueDate: "2026-04-25",
      outstandingLabel: "Rs. 6,000 custom",
    }),
  ).toMatchObject({
    slotCount: null,
    paymentStatus: "PARTIAL",
    penaltyAmount: 1200,
    arrearsAmount: 2500,
    nextDueAmount: 3500,
    nextDueDate: "2026-04-25",
      monthlyInstallmentAmount: null,
      shareReceivedAmount: null,
      finalPayableAmount: 6000,
      totalPayableAmount: 6000,
      outstandingLabel: "Rs. 6,000 custom",
      penaltyLabel: "Rs. 1,200",
      arrearsLabel: "Rs. 2,500",
      nextDueAmountLabel: "Rs. 3,500",
      nextDueDateLabel: "25 Apr 2026",
  });
});

test("buildMemberBalanceSummary does not double count arrears when outstanding already includes the rolled-up due", () => {
  expect(
    buildMemberBalanceSummary({
      memberName: "Nila",
      totalDue: 2000,
      totalPaid: 600,
      outstandingAmount: 1400,
      arrearsAmount: 400,
      nextDueAmount: 1400,
    }),
  ).toMatchObject({
    outstandingAmount: 1400,
    arrearsAmount: 400,
    nextDueAmount: 1400,
    finalPayableAmount: 1400,
    totalPayableAmount: 1400,
    totalPayableLabel: "Rs. 1,400",
  });
});

test("MemberBalanceSummary presents the summary without recalculating it", () => {
  const summary = buildMemberBalanceSummary({
    memberName: "Anita",
    groupTitle: "April Prosperity Chit",
    totalDue: 25000,
    totalPaid: 15750,
  });

  render(<MemberBalanceSummary summary={summary} />);

  expect(screen.getByRole("heading", { name: /Anita/i })).toBeInTheDocument();
  expect(screen.getByText("April Prosperity Chit")).toBeInTheDocument();
  expect(screen.getByText("Final payable")).toBeInTheDocument();
  expect(screen.getAllByText("Rs. 9,250").length).toBeGreaterThan(0);
  expect(screen.getByText("Paid")).toBeInTheDocument();
  expect(screen.getByText("Rs. 15,750")).toBeInTheDocument();
  expect(screen.getByText(/paid \/ Rs\. 0 remaining/i)).toBeInTheDocument();
});
