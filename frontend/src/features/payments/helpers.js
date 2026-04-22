export function formatAmount(value) {
  const numericValue = Number(value);
  if (Number.isNaN(numericValue)) {
    return value === null || value === undefined || value === "" ? "Not available" : String(value);
  }

  return `Rs. ${new Intl.NumberFormat("en-IN", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(numericValue)}`;
}

function titleCase(value) {
  if (!value) {
    return "Not available";
  }

  return String(value)
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function getOptionalNumber(value) {
  if (value == null || value === "") {
    return null;
  }

  const numericValue = Number(value);
  return Number.isNaN(numericValue) ? null : numericValue;
}

function getFirstDefinedValue(source, keys) {
  for (const key of keys) {
    if (source?.[key] != null && source[key] !== "") {
      return source[key];
    }
  }

  return null;
}

export function formatPaymentType(value) {
  return titleCase(value);
}

export function formatPaymentMethod(value) {
  if (!value) {
    return "Not available";
  }

  if (String(value).toLowerCase() === "upi") {
    return "UPI";
  }

  return titleCase(value);
}

export function formatPaymentDate(value) {
  if (!value) {
    return "Not available";
  }

  return String(value);
}

export function formatStatusText(value) {
  return titleCase(value);
}

export function getPaymentStatus(payment = {}) {
  const rawStatus = getFirstDefinedValue(payment, [
    "paymentStatus",
    "payment_state",
    "paymentState",
    "collectionStatus",
    "installmentStatus",
  ]);

  if (!rawStatus) {
    return null;
  }

  const normalizedStatus = String(rawStatus).trim().toUpperCase();
  if (["FULL", "PAID", "COMPLETE", "COMPLETED", "SETTLED"].includes(normalizedStatus)) {
    return "FULL";
  }
  if (["PARTIAL", "PARTIALLY_PAID"].includes(normalizedStatus)) {
    return "PARTIAL";
  }
  if (["PENDING", "DUE", "UNPAID"].includes(normalizedStatus)) {
    return "PENDING";
  }

  return normalizedStatus;
}

export function getPaymentDuesBreakdown(payment = {}) {
  const installmentBalanceAmount = getOptionalNumber(
    getFirstDefinedValue(payment, [
      "installmentBalanceAmount",
      "installmentBalance",
      "remainingInstallmentAmount",
      "balanceAmount",
    ]),
  );
  const penaltyAmount = getOptionalNumber(
    getFirstDefinedValue(payment, ["penaltyAmount", "latePenaltyAmount", "appliedPenaltyAmount"]),
  );
  const arrearsAmount = getOptionalNumber(
    getFirstDefinedValue(payment, ["arrearsAmount", "totalArrearsAmount", "overdueAmount"]),
  );
  const nextDueDate = getFirstDefinedValue(payment, [
    "nextDueDate",
    "upcomingDueDate",
    "nextInstallmentDueDate",
  ]);
  const nextDueAmount = getOptionalNumber(
    getFirstDefinedValue(payment, ["nextDueAmount", "upcomingDueAmount", "nextInstallmentDueAmount"]),
  );

  if (
    installmentBalanceAmount == null &&
    penaltyAmount == null &&
    arrearsAmount == null &&
    !nextDueDate &&
    nextDueAmount == null
  ) {
    return null;
  }

  return {
    installmentBalanceAmount,
    penaltyAmount,
    arrearsAmount,
    nextDueDate,
    nextDueAmount,
  };
}

export function toOptionalNumber(value) {
  if (value === "" || value === null || value === undefined) {
    return null;
  }

  const numericValue = Number(value);
  return Number.isNaN(numericValue) ? null : numericValue;
}

export function todayInputValue() {
  return new Date().toISOString().slice(0, 10);
}
