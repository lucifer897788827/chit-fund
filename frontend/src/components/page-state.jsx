import { Loader2, TriangleAlert } from "lucide-react";

import { normalizeApiError } from "../lib/api-error";
import { cn } from "../lib/utils";

function LoadingStateBody({ label, description }) {
  return (
    <>
      <Loader2 className="mt-1 h-5 w-5 animate-spin text-teal-700" aria-hidden="true" />
      <div className="space-y-1">
        <p className="font-semibold text-slate-900">{label}</p>
        {description ? <p className="text-sm text-slate-600">{description}</p> : null}
        <div aria-hidden="true" className="space-y-2 pt-2">
          <div className="h-3 w-28 animate-pulse rounded-full bg-slate-200" />
          <div className="h-3 w-full animate-pulse rounded-full bg-slate-100" />
          <div className="h-3 w-5/6 animate-pulse rounded-full bg-slate-100" />
        </div>
      </div>
    </>
  );
}

function EmptyStateBody({ title, description, onAction, actionLabel }) {
  return (
    <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 p-4">
      <p className="font-semibold text-slate-900">{title}</p>
      {description ? <p className="mt-1 text-sm text-slate-600">{description}</p> : null}
      {onAction && actionLabel ? (
        <button className="action-button mt-3" onClick={onAction} type="button">
          {actionLabel}
        </button>
      ) : null}
    </div>
  );
}

function ErrorStateBody({ error, fallbackMessage, onRetry, retryLabel, title }) {
  const normalizedError = normalizeApiError(error, { fallbackMessage });

  return (
    <div className="flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 p-4 text-red-950">
      <TriangleAlert className="h-4 w-4" aria-hidden="true" />
      <div className="space-y-3">
        <div>
          <p className="font-semibold">{title}</p>
          <p className="text-sm text-red-900">{normalizedError.message}</p>
        </div>
        {normalizedError.details ? <p>{normalizedError.details}</p> : null}
        {onRetry ? (
          <button className="action-button bg-red-700 hover:bg-red-800" onClick={onRetry} type="button">
            {retryLabel}
          </button>
        ) : null}
      </div>
    </div>
  );
}

export function SectionLoadingState({
  label = "Loading...",
  description = "Please wait while we fetch the latest data.",
  className,
}) {
  return (
    <section className={cn("panel flex items-start gap-3", className)} aria-live="polite" role="status">
      <LoadingStateBody description={description} label={label} />
    </section>
  );
}

export function SectionEmptyState({
  title = "Nothing here yet.",
  description = "There is nothing to show right now.",
  onAction,
  actionLabel,
  className,
}) {
  return (
    <section className={cn("panel", className)} aria-live="polite">
      <EmptyStateBody actionLabel={actionLabel} description={description} onAction={onAction} title={title} />
    </section>
  );
}

export function SectionErrorState({
  error,
  title = "We could not load this section.",
  fallbackMessage = "Please try again in a moment.",
  onRetry,
  retryLabel = "Retry",
  className,
}) {
  return (
    <section className={cn("panel", className)} aria-live="polite">
      <ErrorStateBody
        error={error}
        fallbackMessage={fallbackMessage}
        onRetry={onRetry}
        retryLabel={retryLabel}
        title={title}
      />
    </section>
  );
}

export function AsyncSectionState({
  title,
  description,
  loading,
  error,
  empty,
  loadingLabel = "Loading...",
  loadingDescription = "Please wait while we fetch the latest data.",
  emptyTitle = "Nothing here yet.",
  emptyDescription = "There is nothing to show right now.",
  emptyActionLabel,
  onEmptyAction,
  errorTitle = "We could not load this section.",
  fallbackMessage = "Please try again in a moment.",
  onRetry,
  retryLabel = "Retry",
  className,
  children,
}) {
  return (
    <section className={cn("panel space-y-4", className)} aria-live="polite">
      {title || description ? (
        <div className="space-y-1">
          {title ? <h2>{title}</h2> : null}
          {description ? <p className="text-sm text-slate-600">{description}</p> : null}
        </div>
      ) : null}

      {loading ? (
        <LoadingStateBody description={loadingDescription} label={loadingLabel} />
      ) : error ? (
        <ErrorStateBody
          error={error}
          fallbackMessage={fallbackMessage}
          onRetry={onRetry}
          retryLabel={retryLabel}
          title={errorTitle}
        />
      ) : empty ? (
        <EmptyStateBody
          actionLabel={emptyActionLabel}
          description={emptyDescription}
          onAction={onEmptyAction}
          title={emptyTitle}
        />
      ) : (
        children
      )}
    </section>
  );
}

export function PageLoadingState({
  label = "Loading...",
  description = "Please wait while we fetch the latest data.",
  className,
}) {
  return <SectionLoadingState className={className} description={description} label={label} />;
}

export function PageErrorState({
  error,
  title = "We could not load this page.",
  fallbackMessage = "Please try again in a moment.",
  onRetry,
  retryLabel = "Retry",
  className,
}) {
  return (
    <SectionErrorState
      className={className}
      error={error}
      fallbackMessage={fallbackMessage}
      onRetry={onRetry}
      retryLabel={retryLabel}
      title={title}
    />
  );
}
