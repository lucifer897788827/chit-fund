export default function AdminTablePagination({ page, limit, totalCount, totalPages, onPageChange }) {
  if (!totalCount) {
    return null;
  }

  const lastPage = Math.max(totalPages, 1);
  const safePage = Math.min(Math.max(page, 1), lastPage);
  const startItem = (safePage - 1) * limit + 1;
  const endItem = Math.min(safePage * limit, totalCount);

  return (
    <div className="mt-4 flex flex-col gap-3 border-t border-slate-200 pt-4 text-sm text-slate-600 sm:flex-row sm:items-center sm:justify-between">
      <p>
        Showing {startItem}-{endItem} of {totalCount}
      </p>
      <div className="flex items-center gap-3">
        <button
          aria-label="Previous page"
          className="rounded-lg border border-slate-200 px-3 py-2 font-semibold text-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
          disabled={safePage <= 1}
          onClick={() => onPageChange(safePage - 1)}
          type="button"
        >
          Previous
        </button>
        <span className="font-semibold text-slate-900">Page {safePage} of {lastPage}</span>
        <button
          aria-label="Next page"
          className="rounded-lg border border-slate-200 px-3 py-2 font-semibold text-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
          disabled={safePage >= lastPage}
          onClick={() => onPageChange(safePage + 1)}
          type="button"
        >
          Next
        </button>
      </div>
    </div>
  );
}
