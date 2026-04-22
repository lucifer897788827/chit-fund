import { apiClient } from "../../lib/api/client";
import { extractListItems } from "../../lib/api/list-response";

function isReadStatus(status) {
  const normalizedStatus = String(status ?? "").toLowerCase();
  return ["read", "seen", "acknowledged", "delivered"].includes(normalizedStatus);
}

export function normalizeNotification(notification = {}) {
  const status = notification.status ?? notification.readStatus ?? "pending";
  const readAt = notification.readAt ?? notification.read_at ?? null;
  const metadata = notification.metadata ?? notification.meta ?? null;

  return {
    id: notification.id ?? null,
    userId: notification.userId ?? notification.user_id ?? null,
    ownerId: notification.ownerId ?? notification.owner_id ?? null,
    channel: notification.channel ?? "in_app",
    title: notification.title ?? "",
    message: notification.message ?? "",
    status,
    createdAt: notification.createdAt ?? notification.created_at ?? null,
    sentAt: notification.sentAt ?? notification.sent_at ?? null,
    readAt,
    metadata,
    notificationType: notification.notificationType ?? notification.notification_type ?? null,
    deepLink:
      notification.deepLink ??
      notification.deep_link ??
      notification.linkTo ??
      notification.link_to ??
      notification.href ??
      notification.url ??
      metadata?.deepLink ??
      metadata?.deep_link ??
      metadata?.linkTo ??
      metadata?.href ??
      null,
    sessionId:
      notification.sessionId ??
      notification.session_id ??
      notification.auctionSessionId ??
      notification.auction_session_id ??
      metadata?.sessionId ??
      metadata?.auctionSessionId ??
      null,
    groupId: notification.groupId ?? notification.group_id ?? metadata?.groupId ?? null,
    paymentId: notification.paymentId ?? notification.payment_id ?? metadata?.paymentId ?? null,
    isRead:
      typeof notification.isRead === "boolean" ? notification.isRead : Boolean(readAt) || isReadStatus(status),
  };
}

async function requestNotificationAction(primaryRequest, fallbackRequests = []) {
  try {
    return await primaryRequest();
  } catch (error) {
    if (![404, 405].includes(error?.response?.status)) {
      throw error;
    }

    for (const fallbackRequest of fallbackRequests) {
      if (typeof fallbackRequest !== "function") {
        continue;
      }

      try {
        return await fallbackRequest();
      } catch (fallbackError) {
        if (![404, 405].includes(fallbackError?.response?.status)) {
          throw fallbackError;
        }
      }
    }

    throw error;
  }
}

export async function fetchNotifications(filters = {}) {
  const { data } = await apiClient.get("/notifications", { params: filters });
  return extractListItems(data).map((notification) => normalizeNotification(notification));
}

export async function markNotificationRead(notificationId, payload = {}) {
  const response = await requestNotificationAction(
    () => apiClient.patch(`/notifications/${notificationId}/read`, payload),
    [
      () => apiClient.post(`/notifications/${notificationId}/read`, payload),
      () => apiClient.post(`/notifications/${notificationId}/mark-read`, payload),
      () => apiClient.patch(`/notifications/${notificationId}`, {
        ...payload,
        status: "read",
      }),
    ],
  );

  return normalizeNotification(response.data);
}
