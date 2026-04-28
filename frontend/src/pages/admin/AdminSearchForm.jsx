export default function AdminSearchForm({ value, onChange, onClear, onSubmit, placeholder = "Search by phone or name" }) {
  return (
    <form className="grid gap-3 md:grid-cols-[minmax(0,1fr)_auto_auto]" onSubmit={onSubmit}>
      <label className="space-y-2 text-sm font-semibold text-slate-700">
        Search
        <input className="text-input" onChange={onChange} placeholder={placeholder} type="search" value={value} />
      </label>
      <button
        aria-label="Apply search"
        className="self-end rounded-lg border border-slate-200 px-4 py-3 font-semibold text-slate-700"
        type="submit"
      >
        Apply
      </button>
      <button
        aria-label="Clear search"
        className="self-end rounded-lg border border-slate-200 px-4 py-3 font-semibold text-slate-700"
        onClick={onClear}
        type="button"
      >
        Clear
      </button>
    </form>
  );
}
