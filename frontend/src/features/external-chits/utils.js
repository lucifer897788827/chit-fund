function toText(value, fallback = "") {
  if (value === null || value === undefined) {
    return fallback;
  }

  return String(value);
}

function toNumber(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }

  const numericValue = Number(value);
  return Number.isNaN(numericValue) ? null : numericValue;
}

function toBoolean(value) {
  if (value === null || value === undefined) {
    return false;
  }

  return Boolean(value);
}

function toInteger(value) {
  const numericValue = toNumber(value);
  if (numericValue === null) {
    return null;
  }

  return Math.trunc(numericValue);
}

function padDatePart(value) {
  return String(value).padStart(2, "0");
}

function getTodayIsoDate() {
  const now = new Date();
  return `${now.getFullYear()}-${padDatePart(now.getMonth() + 1)}-${padDatePart(now.getDate())}`;
}

function buildMonthlyEntryDate(startDate, monthNumber) {
  if (!startDate || !monthNumber || monthNumber < 1) {
    return getTodayIsoDate();
  }

  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(startDate);
  if (!match) {
    return getTodayIsoDate();
  }

  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const targetMonthIndex = month - 1 + (monthNumber - 1);
  const resolvedYear = year + Math.floor(targetMonthIndex / 12);
  const resolvedMonth = (targetMonthIndex % 12) + 1;
  const derivedDate = `${resolvedYear}-${padDatePart(resolvedMonth)}-${padDatePart(day)}`;
  const today = getTodayIsoDate();

  return derivedDate > today ? today : derivedDate;
}

export function formatAmount(value) {
  const numericValue = toNumber(value);
  if (numericValue === null) {
    return "Not available";
  }

  return `Rs. ${new Intl.NumberFormat("en-IN", {
    maximumFractionDigits: 0,
  }).format(numericValue)}`;
}

export function formatDate(value) {
  if (!value) {
    return "Not available";
  }

  if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return value;
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return toText(value);
  }

  return date.toLocaleDateString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

export function formatDateTime(value) {
  if (!value) {
    return "Not available";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return toText(value);
  }

  return date.toLocaleString("en-IN", {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

export function normalizeExternalChitEntry(entry) {
  if (!entry || typeof entry !== "object") {
    return null;
  }

  return {
    id: entry.id,
    externalChitId: entry.externalChitId ?? entry.external_chit_id ?? null,
    monthNumber: entry.monthNumber ?? entry.month_number ?? null,
    bidAmount: entry.bidAmount ?? entry.bid_amount ?? null,
    winnerType: toText(entry.winnerType ?? entry.winner_type ?? "").toUpperCase(),
    winnerName: entry.winnerName ?? entry.winner_name ?? "",
    sharePerSlot: entry.sharePerSlot ?? entry.share_per_slot ?? null,
    myShare: entry.myShare ?? entry.my_share ?? null,
    myPayable: entry.myPayable ?? entry.my_payable ?? null,
    myPayout: entry.myPayout ?? entry.my_payout ?? null,
    isBidOverridden: toBoolean(entry.isBidOverridden ?? entry.is_bid_overridden),
    isShareOverridden: toBoolean(entry.isShareOverridden ?? entry.is_share_overridden),
    isPayableOverridden: toBoolean(entry.isPayableOverridden ?? entry.is_payable_overridden),
    isPayoutOverridden: toBoolean(entry.isPayoutOverridden ?? entry.is_payout_overridden),
    entryType: entry.entryType ?? entry.entry_type ?? "",
    entryDate: entry.entryDate ?? entry.entry_date ?? "",
    amount: entry.amount ?? null,
    description: entry.description ?? "",
    createdAt: entry.createdAt ?? entry.created_at ?? null,
    updatedAt: entry.updatedAt ?? entry.updated_at ?? null,
  };
}

export function normalizeExternalChit(chit) {
  if (!chit || typeof chit !== "object") {
    return null;
  }

  const entryHistory = Array.isArray(chit.entryHistory ?? chit.entry_history)
    ? (chit.entryHistory ?? chit.entry_history)
        .map(normalizeExternalChitEntry)
        .filter(Boolean)
    : [];

  return {
    id: chit.id,
    subscriberId: chit.subscriberId ?? chit.subscriber_id ?? null,
    userId: chit.userId ?? chit.user_id ?? null,
    title: chit.title ?? "",
    name: chit.name ?? "",
    organizerName: chit.organizerName ?? chit.organizer_name ?? "",
    chitValue: chit.chitValue ?? chit.chit_value ?? null,
    installmentAmount: chit.installmentAmount ?? chit.installment_amount ?? null,
    monthlyInstallment: chit.monthlyInstallment ?? chit.monthly_installment ?? null,
    totalMembers: chit.totalMembers ?? chit.total_members ?? null,
    totalMonths: chit.totalMonths ?? chit.total_months ?? null,
    userSlots: chit.userSlots ?? chit.user_slots ?? null,
    firstMonthOrganizer: toBoolean(chit.firstMonthOrganizer ?? chit.first_month_organizer),
    cycleFrequency: chit.cycleFrequency ?? chit.cycle_frequency ?? "",
    startDate: chit.startDate ?? chit.start_date ?? "",
    endDate: chit.endDate ?? chit.end_date ?? null,
    status: chit.status ?? "active",
    notes: chit.notes ?? "",
    entryHistory,
  };
}

export function normalizeExternalChitSummary(summary) {
  if (!summary || typeof summary !== "object") {
    return {
      totalPaid: 0,
      totalReceived: 0,
      profit: 0,
      winningMonth: null,
    };
  }

  return {
    totalPaid: toInteger(summary.totalPaid ?? summary.total_paid) ?? 0,
    totalReceived: toInteger(summary.totalReceived ?? summary.total_received) ?? 0,
    profit: toInteger(summary.profit) ?? 0,
    winningMonth: toInteger(summary.winningMonth ?? summary.winning_month),
  };
}

export function normalizeExternalChitList(items) {
  return (Array.isArray(items) ? items : []).map(normalizeExternalChit).filter(Boolean);
}

export function buildExternalChitPayload(draft, mode) {
  const payload = {
    title: draft.title.trim(),
    name: draft.name.trim(),
    organizerName: draft.organizerName.trim(),
    chitValue: toNumber(draft.chitValue),
    installmentAmount: toNumber(draft.installmentAmount),
    monthlyInstallment: toNumber(draft.monthlyInstallment),
    totalMembers: toNumber(draft.totalMembers),
    totalMonths: toNumber(draft.totalMonths),
    userSlots: toNumber(draft.userSlots),
    firstMonthOrganizer: toBoolean(draft.firstMonthOrganizer),
    cycleFrequency: draft.cycleFrequency,
    startDate: draft.startDate || null,
    endDate: draft.endDate || null,
    notes: draft.notes.trim(),
  };

  if (mode === "edit") {
    payload.status = draft.status;
  } else {
    payload.status = "active";
  }

  return payload;
}

export function buildExternalChitDraft(chit) {
  return {
    title: chit?.title ?? "",
    name: chit?.name ?? "",
    organizerName: chit?.organizerName ?? "",
    chitValue: chit?.chitValue ?? "",
    installmentAmount: chit?.installmentAmount ?? "",
    monthlyInstallment: chit?.monthlyInstallment ?? "",
    totalMembers: chit?.totalMembers ?? "",
    totalMonths: chit?.totalMonths ?? "",
    userSlots: chit?.userSlots ?? "",
    firstMonthOrganizer: toBoolean(chit?.firstMonthOrganizer),
    cycleFrequency: chit?.cycleFrequency ?? "monthly",
    startDate: chit?.startDate ?? "",
    endDate: chit?.endDate ?? "",
    notes: chit?.notes ?? "",
    status: chit?.status ?? "active",
  };
}

export function getExternalChitMonthlyEntries(chit) {
  return (Array.isArray(chit?.entryHistory) ? chit.entryHistory : [])
    .filter((entry) => entry?.monthNumber !== null && entry?.monthNumber !== undefined)
    .sort((leftEntry, rightEntry) => {
      const leftMonth = toInteger(leftEntry?.monthNumber) ?? 0;
      const rightMonth = toInteger(rightEntry?.monthNumber) ?? 0;

      if (leftMonth !== rightMonth) {
        return leftMonth - rightMonth;
      }

      return String(leftEntry?.entryDate ?? "").localeCompare(String(rightEntry?.entryDate ?? ""));
    });
}

export function getNextExternalChitMonthNumber(chit) {
  const monthlyEntries = getExternalChitMonthlyEntries(chit);

  return (
    monthlyEntries.reduce((highestMonth, entry) => {
      const monthNumber = toInteger(entry?.monthNumber) ?? 0;
      return monthNumber > highestMonth ? monthNumber : highestMonth;
    }, 0) + 1
  );
}

export function buildExternalChitEntryDraft(entry, chit) {
  return {
    monthNumber: entry?.monthNumber ?? getNextExternalChitMonthNumber(chit),
    bidAmount: entry?.bidAmount ?? "",
    winnerType: entry?.winnerType === "SELF" ? "SELF" : "OTHER",
    myShare: entry?.myShare ?? "",
    myPayable: entry?.myPayable ?? "",
    myPayout: entry?.myPayout ?? "",
  };
}

export function buildExternalChitEntryPayload(draft, chit) {
  const winnerType = draft.winnerType === "SELF" ? "SELF" : "OTHER";
  const monthNumber = toInteger(draft.monthNumber);
  const bidAmount = toInteger(draft.bidAmount);

  return {
    entryType: winnerType === "SELF" ? "won" : "paid",
    entryDate: buildMonthlyEntryDate(chit?.startDate, monthNumber),
    amount: bidAmount,
    description: `Month ${monthNumber ?? "?"} ledger entry`,
    monthNumber,
    bidAmount,
    winnerType,
    winnerName: winnerType === "SELF" ? null : "",
    myShare: toInteger(draft.myShare),
    myPayable: toInteger(draft.myPayable),
    myPayout: toInteger(draft.myPayout),
  };
}

export function getExternalChitOverrideStatus(entry, field) {
  if (!entry || typeof entry !== "object") {
    return {
      isManual: false,
      badge: "Auto",
      description: "Calculated automatically",
    };
  }

  const isManual =
    field === "bid"
      ? Boolean(entry.isBidOverridden)
      : field === "share"
        ? Boolean(entry.isShareOverridden)
        : field === "payable"
          ? Boolean(entry.isPayableOverridden)
          : field === "payout"
            ? Boolean(entry.isPayoutOverridden)
            : false;

  return {
    isManual,
    badge: isManual ? "Manual" : "Auto",
    description: isManual ? "Manually adjusted" : "Calculated automatically",
  };
}
