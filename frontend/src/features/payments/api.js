import { apiClient } from "../../lib/api/client";
import { extractListItems } from "../../lib/api/list-response";

async function requestWithNotFoundFallback(primaryRequest, fallbackRequest) {
  try {
    const { data } = await primaryRequest();
    return data;
  } catch (error) {
    if (error?.response?.status !== 404 || typeof fallbackRequest !== "function") {
      throw error;
    }

    const { data } = await fallbackRequest();
    return data;
  }
}

export async function recordPayment(payload) {
  const { data } = await apiClient.post("/payments", payload);
  return data;
}

export async function fetchPayments(filters = {}) {
  const { data } = await apiClient.get("/payments", { params: filters });
  return extractListItems(data);
}

export async function fetchPaymentBalances(filters = {}) {
  const { data } = await apiClient.get("/payments/balances", { params: filters });
  return extractListItems(data);
}

export async function fetchOwnerPayouts(filters = {}) {
  const data = await requestWithNotFoundFallback(
    () => apiClient.get("/payments/payouts", { params: filters }),
    () => apiClient.get("/payouts", { params: filters }),
  );
  if (Array.isArray(data?.payouts)) {
    return data.payouts;
  }
  return extractListItems(data);
}

export async function settleOwnerPayout(payoutId, payload = {}) {
  return requestWithNotFoundFallback(
    () => apiClient.post(`/payments/payouts/${payoutId}/settle`, payload),
    () => apiClient.post(`/payouts/${payoutId}/settle`, payload),
  );
}

export async function markOwnerPayoutPaid(payoutId) {
  const { data } = await apiClient.post(`/payouts/${payoutId}/mark-paid`);
  return data;
}
