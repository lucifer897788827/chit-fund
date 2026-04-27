import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { BellRing, CheckCheck, Clock3, Inbox } from "lucide-react";

import { PageErrorState, PageLoadingState } from "../../components/page-state";
import { useSignedInShellHeader } from "../../components/signed-in-shell";
import { getApiErrorMessage } from "../../lib/api-error";
import { getCurrentUser, getDashboardPath, sessionHasRole } from "../../lib/auth/store";
import { logoutUser } from "../auth/api";
import { fetchNotifications, markNotificationRead } from "./api";

function formatDateTime(value) {
  if (!value) {
    return "N/A";
  }

  const parsedDate = new Date(value);
  if (Number.isNaN(parsedDate.getTime())) {
    return "N/A";
  }

  return new Intl.DateTimeFormat("en-IN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(parsedDate);
}

const NOTIFICATION_PAGE_SIZE = 20;

function normalizeNotificationCopy(notification) {
  return `${notification?.title ?? ""} ${notification?.message ?? ""}`.trim().toLowerCase();
}

function inferNotificationType(notification) {
  const explicitType = String(notification?.notificationType ?? "").trim();
  if (explicitType) {
    return explicitType
      .replace(/[_-]+/g, " ")
      .replace(/\b\w/g, (character) => character.toUpperCase());
  }

  const normalizedCopy = normalizeNotificationCopy(notification);
  if (
    normalizedCopy.includes("auction started") ||
    normalizedCopy.includes("auction is live") ||
    normalizedCopy.includes("bidding open") ||
    normalizedCopy.includes("round started")
  ) {
    return "Auction started";
  }

  if (
    normalizedCopy.includes("auction ended") ||
    normalizedCopy.includes("auction finalized") ||
    normalizedCopy.includes("round finalized") ||
    normalizedCopy.includes("auction update")
  ) {
    return "Auction ended";
  }

  if (
    normalizedCopy.includes("payment due") ||
    normalizedCopy.includes("due payment reminder") ||
    normalizedCopy.includes("overdue payment reminder") ||
    normalizedCopy.includes("previous due")
  ) {
    return "Payment due";
  }

  if (
    normalizedCopy.includes("payment recorded") ||
    normalizedCopy.includes("payment received") ||
    normalizedCopy.includes("installment was recorded")
  ) {
    return "Payment recorded";
  }

  return "Account update";
}

function getNotificationTypeStyles(notificationType) {
  if (notificationType === "Auction started") {
    return "bg-sky-100 text-sky-900";
  }

  if (notificationType === "Auction ended") {
    return "bg-violet-100 text-violet-900";
  }

  if (notificationType === "Payment due") {
    return "bg-amber-100 text-amber-900";
  }

  if (notificationType === "Payment recorded") {
    return "bg-emerald-100 text-emerald-900";
  }

  return "bg-slate-100 text-slate-700";
}

function buildNotificationLink(notification, dashboardPath, role) {
  const explicitLink = notification?.deepLink;
  if (explicitLink) {
    return explicitLink;
  }

  const notificationType = inferNotificationType(notification);
  if ((notificationType === "Auction started" || notificationType === "Auction ended") && notification?.sessionId) {
    return role === "subscriber" ? `/auctions/${notification.sessionId}` : `${dashboardPath}#auctions`;
  }

  if (notificationType === "Auction started" || notificationType === "Auction ended") {
    return `${dashboardPath}#auctions`;
  }

  if (notificationType === "Payment due" || notificationType === "Payment recorded") {
    return `${dashboardPath}#payments`;
  }

  return dashboardPath;
}

function getNotificationLinkLabel(notificationType, linkTo) {
  if (!linkTo) {
    return "Open dashboard";
  }

  if (notificationType === "Auction started" || notificationType === "Auction ended") {
    return linkTo.startsWith("/auctions/") ? "Open auction" : "Open auctions";
  }

  if (notificationType === "Payment due" || notificationType === "Payment recorded") {
    return "Open payments";
  }

  return "Open dashboard";
}

function mergeNotifications(existingNotifications, incomingNotifications) {
  const mergedById = new Map();

  for (const notification of existingNotifications) {
    if (notification?.id != null) {
      mergedById.set(notification.id, notification);
    }
  }

  for (const notification of incomingNotifications) {
    if (notification?.id != null) {
      mergedById.set(notification.id, notification);
    }
  }

  return Array.from(mergedById.values());
}

function NotificationCard({ notification, onMarkRead, marking, dashboardPath, role }) {
  const isRead = Boolean(notification.isRead);
  const notificationType = inferNotificationType(notification);
  const deepLink = buildNotificationLink(notification, dashboardPath, role);
  const linkLabel = getNotificationLinkLabel(notificationType, deepLink);

  return (
    <article
      className={`rounded-xl border p-4 shadow-sm transition ${
        isRead ? "border-slate-200 bg-white" : "border-teal-200 bg-teal-50/70"
      }`}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={`rounded-full px-2.5 py-1 text-xs font-semibold uppercase tracking-wide ${getNotificationTypeStyles(notificationType)}`}
            >
              {notificationType}
            </span>
            <span
              className={`rounded-full px-2.5 py-1 text-xs font-semibold uppercase tracking-wide ${
                isRead ? "bg-slate-100 text-slate-600" : "bg-teal-100 text-teal-800"
              }`}
            >
              {isRead ? "Read" : "Unread"}
            </span>
          </div>
          <Link className="block text-lg font-semibold text-slate-950 hover:text-teal-800" to={deepLink}>
            {notification.title || "Notification"}
          </Link>
          <p className="text-sm leading-6 text-slate-700">{notification.message || "No message available."}</p>
        </div>
        <button
          className="action-button mt-0 shrink-0 disabled:cursor-not-allowed disabled:bg-slate-400"
          disabled={isRead || marking || !notification.id}
          onClick={() => onMarkRead(notification)}
          type="button"
        >
          {marking ? "Marking..." : isRead ? "Marked read" : "Mark read"}
        </button>
      </div>

      <dl className="mt-4 grid gap-3 text-sm text-slate-600 sm:grid-cols-3">
        <div>
          <dt className="font-medium text-slate-500">Channel</dt>
          <dd>{notification.channel || "in_app"}</dd>
        </div>
        <div>
          <dt className="font-medium text-slate-500">Created</dt>
          <dd>{formatDateTime(notification.createdAt)}</dd>
        </div>
        <div>
          <dt className="font-medium text-slate-500">Read at</dt>
          <dd>{formatDateTime(notification.readAt)}</dd>
        </div>
      </dl>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <Link
          className="inline-flex items-center rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-700 transition hover:border-teal-700 hover:text-teal-800"
          to={deepLink}
        >
          {linkLabel}
        </Link>
      </div>
    </article>
  );
}

export default function NotificationsPage() {
  const navigate = useNavigate();
  const currentUser = getCurrentUser();
  const isSignedIn = Boolean(currentUser?.access_token);
  const [notifications, setNotifications] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [filter, setFilter] = useState("all");
  const [markingNotificationId, setMarkingNotificationId] = useState(null);
  const [loadedPageCount, setLoadedPageCount] = useState(0);
  const [hasMoreNotifications, setHasMoreNotifications] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [refreshingNotifications, setRefreshingNotifications] = useState(false);

  async function loadNotificationPage(pageNumber, { append = false } = {}) {
    const data = await fetchNotifications({ page: pageNumber, pageSize: NOTIFICATION_PAGE_SIZE });
    const items = Array.isArray(data) ? data : [];

    setNotifications((currentNotifications) =>
      append ? mergeNotifications(currentNotifications, items) : items,
    );
    setLoadedPageCount(pageNumber);
    setHasMoreNotifications(items.length === NOTIFICATION_PAGE_SIZE);
    return items;
  }

  async function refreshNotificationsFeed(pageCount = loadedPageCount || 1, { surfaceErrors = false } = {}) {
    if (!isSignedIn) {
      return false;
    }

    setRefreshingNotifications(true);
    try {
      let combinedNotifications = [];
      let lastPageSize = 0;

      for (let pageNumber = 1; pageNumber <= pageCount; pageNumber += 1) {
        const pageItems = await fetchNotifications({ page: pageNumber, pageSize: NOTIFICATION_PAGE_SIZE });
        const items = Array.isArray(pageItems) ? pageItems : [];
        lastPageSize = items.length;
        combinedNotifications = mergeNotifications(combinedNotifications, items);
        if (items.length < NOTIFICATION_PAGE_SIZE) {
          break;
        }
      }

      setNotifications(combinedNotifications);
      setLoadedPageCount(pageCount);
      setHasMoreNotifications(lastPageSize === NOTIFICATION_PAGE_SIZE);
      return true;
    } catch (notificationError) {
      if (surfaceErrors) {
        setError(
          getApiErrorMessage(notificationError, {
            fallbackMessage: "Unable to refresh notifications right now.",
          }),
        );
      }
      return false;
    } finally {
      setRefreshingNotifications(false);
    }
  }

  useEffect(() => {
    let active = true;

    if (!isSignedIn) {
      setError("Sign in to view your notifications.");
      setLoading(false);
      return () => {
        active = false;
      };
    }

    setLoading(true);
    setError("");

    loadNotificationPage(1)
      .then(() => {
        if (active) {
          setLoadedPageCount(1);
        }
      })
      .catch((notificationError) => {
        if (active) {
          setError(
            getApiErrorMessage(notificationError, {
              fallbackMessage: "Unable to load notifications right now.",
            }),
          );
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [isSignedIn]);

  const unreadCount = useMemo(
    () => notifications.filter((notification) => !notification.isRead).length,
    [notifications],
  );

  const visibleNotifications = useMemo(() => {
    if (filter === "unread") {
      return notifications.filter((notification) => !notification.isRead);
    }

    return notifications;
  }, [filter, notifications]);

  async function handleLogout() {
    try {
      await logoutUser();
    } finally {
      navigate("/");
    }
  }

  async function handleMarkRead(notification) {
    if (!notification?.id || notification.isRead || markingNotificationId === notification.id) {
      return;
    }

    setMarkingNotificationId(notification.id);
    setMessage("");

    try {
      const updatedNotification = await markNotificationRead(notification.id);
      setNotifications((currentNotifications) =>
        currentNotifications.map((currentNotification) =>
          currentNotification.id === notification.id
            ? {
                ...currentNotification,
                ...updatedNotification,
                isRead: true,
                status: updatedNotification.status ?? "read",
                readAt: updatedNotification.readAt ?? new Date().toISOString(),
              }
            : currentNotification,
        ),
      );
      void refreshNotificationsFeed(loadedPageCount || 1);
      setMessage("Notification marked as read.");
    } catch (notificationError) {
      setMessage(
        getApiErrorMessage(notificationError, {
          fallbackMessage: "Unable to mark this notification as read right now.",
        }),
      );
    } finally {
      setMarkingNotificationId(null);
    }
  }

  async function handleLoadMore() {
    if (loadingMore || refreshingNotifications || !hasMoreNotifications) {
      return;
    }

    setLoadingMore(true);
    setMessage("");

    try {
      await loadNotificationPage(loadedPageCount + 1, { append: true });
    } catch (notificationError) {
      setError(
        getApiErrorMessage(notificationError, {
          fallbackMessage: "Unable to load more notifications right now.",
        }),
      );
    } finally {
      setLoadingMore(false);
    }
  }

  const totalCount = notifications.length;
  const readCount = totalCount - unreadCount;
  const dashboardPath = getDashboardPath(currentUser);
  const shellContextLabel =
    unreadCount > 0
      ? `${unreadCount} unread ${unreadCount === 1 ? "notification" : "notifications"}`
      : totalCount > 0
        ? `${totalCount} notifications in your feed`
        : "Auction and payment alerts";

  useSignedInShellHeader({
    title: "Notifications",
    contextLabel: shellContextLabel,
  });

  return (
    <main className="page-shell">
      <header className="space-y-3">
        <div className="flex flex-wrap items-center gap-3">
          <BellRing className="h-7 w-7 text-teal-700" aria-hidden="true" />
          <h1>Notifications</h1>
        </div>
        <p>Review alerts, updates, and reminders that belong to your signed-in account.</p>

        <div className="panel-grid sm:grid-cols-3">
          <article className="panel">
            <p className="text-sm uppercase tracking-wide text-slate-500">Total</p>
            <p className="mt-2 text-2xl font-semibold text-slate-950">{totalCount}</p>
          </article>
          <article className="panel">
            <p className="text-sm uppercase tracking-wide text-slate-500">Unread</p>
            <p className="mt-2 text-2xl font-semibold text-slate-950">{unreadCount}</p>
          </article>
          <article className="panel">
            <p className="text-sm uppercase tracking-wide text-slate-500">Read</p>
            <p className="mt-2 text-2xl font-semibold text-slate-950">{readCount}</p>
          </article>
        </div>

        {isSignedIn ? (
          <div className="flex flex-wrap items-center gap-3">
            <Link className="action-button mt-0 bg-slate-700 hover:bg-slate-800" to={dashboardPath}>
              Back to dashboard
            </Link>
            <button className="action-button mt-0" onClick={handleLogout} type="button">
              Log Out
            </button>
          </div>
        ) : null}
      </header>

      {loading ? (
        <PageLoadingState
          description="Fetching the latest notifications for your account."
          label="Loading notifications..."
        />
      ) : null}
      {!loading && error ? (
        <PageErrorState
          error={error}
          fallbackMessage="Unable to load notifications right now."
          onRetry={() => navigate(0)}
          title="We could not load notifications."
        />
      ) : null}

      {!loading && !error ? (
        <section className="panel space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="space-y-1">
              <h2>Your feed</h2>
              <p className="text-sm text-slate-600">Filter to the unread items you still need to review.</p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <button
                className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-700 transition hover:border-teal-700 hover:text-teal-800 disabled:cursor-not-allowed disabled:opacity-60"
                disabled={loadingMore || refreshingNotifications || loading}
                onClick={() => void refreshNotificationsFeed(loadedPageCount || 1, { surfaceErrors: true })}
                type="button"
              >
                {refreshingNotifications ? "Refreshing..." : "Refresh"}
              </button>
              <button
                className={`rounded-full border px-4 py-2 text-sm font-semibold transition ${
                  filter === "all"
                    ? "border-teal-700 bg-teal-700 text-white"
                    : "border-slate-200 bg-white text-slate-700"
                }`}
                onClick={() => setFilter("all")}
                type="button"
              >
                All
              </button>
              <button
                className={`rounded-full border px-4 py-2 text-sm font-semibold transition ${
                  filter === "unread"
                    ? "border-teal-700 bg-teal-700 text-white"
                    : "border-slate-200 bg-white text-slate-700"
                }`}
                onClick={() => setFilter("unread")}
                type="button"
              >
                Unread
              </button>
            </div>
          </div>

          {message ? (
            <p className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-900">
              {message}
            </p>
          ) : null}

          {visibleNotifications.length === 0 ? (
            <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 p-5 text-slate-700">
              <div className="flex items-start gap-3">
                <Inbox className="mt-0.5 h-5 w-5 text-slate-400" aria-hidden="true" />
                <div className="space-y-1">
                  <p className="font-semibold text-slate-900">
                    {filter === "unread" ? "No unread notifications." : "No notifications yet."}
                  </p>
                  <p className="text-sm text-slate-600">
                    {filter === "unread"
                      ? "Everything is up to date for now."
                      : "New account activity and reminders will appear here."}
                  </p>
                </div>
              </div>
            </div>
          ) : (
            <div className="grid gap-3">
              {visibleNotifications.map((notification) => (
                <NotificationCard
                  dashboardPath={dashboardPath}
                  key={notification.id}
                  marking={markingNotificationId === notification.id}
                  notification={notification}
                  onMarkRead={handleMarkRead}
              role={sessionHasRole(currentUser, "subscriber") ? "subscriber" : "owner"}
            />
              ))}
            </div>
          )}

          {hasMoreNotifications ? (
            <div className="flex justify-center pt-2">
              <button
                className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-700 transition hover:border-teal-700 hover:text-teal-800 disabled:cursor-not-allowed disabled:opacity-60"
                disabled={loadingMore || refreshingNotifications}
                onClick={() => void handleLoadMore()}
                type="button"
              >
                {loadingMore ? "Loading more..." : "Load more"}
              </button>
            </div>
          ) : null}
        </section>
      ) : null}

      {!loading && !error && unreadCount > 0 ? (
        <p className="text-sm text-slate-600">
          <CheckCheck className="mr-2 inline-block h-4 w-4 text-teal-700" aria-hidden="true" />
          You still have {unreadCount} unread {unreadCount === 1 ? "notification" : "notifications"}.
        </p>
      ) : null}
      {!loading && !error && totalCount > 0 ? (
        <p className="text-sm text-slate-600">
          <Clock3 className="mr-2 inline-block h-4 w-4 text-slate-500" aria-hidden="true" />
          Latest update loaded from the server feed.
        </p>
      ) : null}
      {!loading && !error && totalCount === 0 ? (
        <p className="text-sm text-slate-600">
          <span className="skeleton-card mr-2 inline-block h-3 w-10 rounded-full bg-slate-200 align-middle" aria-hidden="true" />
          Waiting for the first notification to arrive.
        </p>
      ) : null}
    </main>
  );
}
