export const DEFAULT_ADMIN_PAGE_SIZE = 20;

function normalizePositiveInteger(value, fallbackValue) {
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return fallbackValue;
  }
  return parsed;
}

export function readAdminPagination(searchParams) {
  return {
    page: normalizePositiveInteger(searchParams.get("page"), 1),
    limit: normalizePositiveInteger(searchParams.get("limit"), DEFAULT_ADMIN_PAGE_SIZE),
  };
}

export function buildAdminPaginationParams(searchParams, { page, limit }) {
  return buildAdminListParams(searchParams, { page, limit });
}

export function buildAdminListParams(searchParams, updates) {
  const nextParams = new URLSearchParams(searchParams);

  Object.entries(updates).forEach(([key, value]) => {
    if (value == null || value === "") {
      nextParams.delete(key);
      return;
    }
    if (key === "page" || key === "limit") {
      nextParams.set(key, String(Math.max(1, Number(value))));
      return;
    }
    nextParams.set(key, String(value));
  });

  if (!nextParams.has("page")) {
    nextParams.set("page", "1");
  }
  if (!nextParams.has("limit")) {
    nextParams.set("limit", String(DEFAULT_ADMIN_PAGE_SIZE));
  }

  return nextParams;
}

export function paginateAdminItems(items, { page, limit }) {
  const normalizedItems = Array.isArray(items) ? items : [];
  const totalCount = normalizedItems.length;
  const totalPages = totalCount > 0 ? Math.ceil(totalCount / limit) : 0;
  const safePage = totalPages > 0 ? Math.min(page, totalPages) : 1;
  const startIndex = totalCount > 0 ? (safePage - 1) * limit : 0;
  const pagedItems = normalizedItems.slice(startIndex, startIndex + limit);
  const visibleStart = totalCount > 0 ? startIndex + 1 : 0;
  const visibleEnd = totalCount > 0 ? startIndex + pagedItems.length : 0;

  return {
    items: pagedItems,
    page: safePage,
    limit,
    totalCount,
    totalPages,
    visibleStart,
    visibleEnd,
  };
}
