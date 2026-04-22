import { cn } from "../lib/utils";

function FeedbackMessage({ variant, children }) {
  if (!children) {
    return null;
  }

  const styles =
    variant === "error"
      ? "border-red-200 bg-red-50 text-red-900"
      : "border-emerald-200 bg-emerald-50 text-emerald-900";
  const role = variant === "error" ? "alert" : "status";

  return (
    <p className={cn("rounded-lg border px-3 py-2 text-sm", styles)} role={role}>
      {children}
    </p>
  );
}

export function FormFrame({
  title,
  description,
  error = "",
  success = "",
  className,
  children,
}) {
  return (
    <section className={cn("panel space-y-4", className)}>
      <div className="space-y-1">
        {title ? <h2 className="text-xl font-semibold text-slate-900">{title}</h2> : null}
        {description ? <p className="text-sm text-slate-600">{description}</p> : null}
      </div>

      <FeedbackMessage variant="error">{error}</FeedbackMessage>
      <FeedbackMessage variant="success">{success}</FeedbackMessage>

      {children}
    </section>
  );
}

export function FormField({
  label,
  htmlFor,
  helpText,
  error,
  className,
  labelClassName,
  children,
}) {
  return (
    <div className={cn("space-y-1", className)}>
      <label className={cn("field-label block text-sm", labelClassName)} htmlFor={htmlFor}>
        {label}
      </label>
      {children}
      {helpText ? <p className="text-sm text-slate-600">{helpText}</p> : null}
      {error ? <p className="text-sm text-red-700">{error}</p> : null}
    </div>
  );
}

export function FormActions({ note, className, children }) {
  return (
    <div className={cn("flex flex-wrap items-center gap-3", className)}>
      {children}
      {note ? <p className="text-sm text-slate-600">{note}</p> : null}
    </div>
  );
}
