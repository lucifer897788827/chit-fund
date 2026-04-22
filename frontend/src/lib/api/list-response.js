function collectArrayCandidates(data) {
  if (!data || typeof data !== "object" || Array.isArray(data)) {
    return [];
  }

  return [
    data.items,
    data.results,
    data.data,
    data.records,
    data.rows,
    data.notifications,
    data.payments,
    data.payouts,
    data.groups,
    data.subscribers,
    data.balances,
    data.chits,
    data.externalChits,
  ];
}

export function extractListItems(data) {
  if (Array.isArray(data)) {
    return data;
  }

  for (const candidate of collectArrayCandidates(data)) {
    if (Array.isArray(candidate)) {
      return candidate;
    }
  }

  return [];
}
