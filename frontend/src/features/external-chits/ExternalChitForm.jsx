import { useEffect, useState } from "react";

import { FormActions, FormField, FormFrame } from "../../components/form-primitives";
import { buildExternalChitDraft, buildExternalChitPayload } from "./utils";

const cycleFrequencyOptions = [
  { value: "monthly", label: "Monthly" },
  { value: "weekly", label: "Weekly" },
  { value: "quarterly", label: "Quarterly" },
  { value: "yearly", label: "Yearly" },
];

const statusOptions = [
  { value: "active", label: "Active" },
  { value: "paused", label: "Paused" },
  { value: "completed", label: "Completed" },
  { value: "deleted", label: "Deleted" },
];

export default function ExternalChitForm({
  mode = "create",
  chit,
  onSubmit,
  onCancel,
  submitting = false,
  error = "",
  success = "",
}) {
  const [draft, setDraft] = useState(() => buildExternalChitDraft(chit));

  useEffect(() => {
    setDraft(buildExternalChitDraft(chit));
  }, [chit, mode]);

  function updateField(field, value) {
    setDraft((currentDraft) => ({
      ...currentDraft,
      [field]: value,
    }));
  }

  function handleSubmit(event) {
    event.preventDefault();
    if (submitting) {
      return;
    }

    if (typeof onSubmit === "function") {
      onSubmit(buildExternalChitPayload(draft, mode));
    }
  }

  const isEditMode = mode === "edit";

  return (
    <FormFrame
      description={
        isEditMode
          ? "Adjust the selected chit without leaving the page."
          : "Create a new outside chit record and keep it in the same workspace."
      }
      error={error}
      success={success}
      title={isEditMode ? "Edit external chit" : "Add external chit"}
    >
      <form className="grid gap-4 md:grid-cols-2" onSubmit={handleSubmit}>
        <FormField className="md:col-span-2" htmlFor="external-chit-title" label="Title">
          <input
            className="w-full rounded-md border border-slate-300 px-3 py-2"
            id="external-chit-title"
            name="title"
            onChange={(event) => updateField("title", event.target.value)}
            type="text"
            value={draft.title}
          />
        </FormField>

        <FormField className="md:col-span-2" htmlFor="external-chit-name" label="Ledger name">
          <input
            className="w-full rounded-md border border-slate-300 px-3 py-2"
            id="external-chit-name"
            name="name"
            onChange={(event) => updateField("name", event.target.value)}
            type="text"
            value={draft.name}
          />
        </FormField>

        <FormField htmlFor="external-chit-organizer" label="Organizer name">
          <input
            className="w-full rounded-md border border-slate-300 px-3 py-2"
            id="external-chit-organizer"
            name="organizerName"
            onChange={(event) => updateField("organizerName", event.target.value)}
            type="text"
            value={draft.organizerName}
          />
        </FormField>

        <FormField htmlFor="external-chit-status" label="Status">
          <select
            className="w-full rounded-md border border-slate-300 px-3 py-2"
            id="external-chit-status"
            name="status"
            onChange={(event) => updateField("status", event.target.value)}
            value={draft.status}
          >
            {statusOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </FormField>

        <FormField htmlFor="external-chit-value" label="Chit value">
          <input
            className="w-full rounded-md border border-slate-300 px-3 py-2"
            id="external-chit-value"
            name="chitValue"
            onChange={(event) => updateField("chitValue", event.target.value)}
            step="1"
            type="number"
            value={draft.chitValue}
          />
        </FormField>

        <FormField htmlFor="external-chit-installment" label="Installment amount">
          <input
            className="w-full rounded-md border border-slate-300 px-3 py-2"
            id="external-chit-installment"
            name="installmentAmount"
            onChange={(event) => updateField("installmentAmount", event.target.value)}
            step="1"
            type="number"
            value={draft.installmentAmount}
          />
        </FormField>

        <FormField htmlFor="external-chit-monthly-installment" label="Monthly installment">
          <input
            className="w-full rounded-md border border-slate-300 px-3 py-2"
            id="external-chit-monthly-installment"
            name="monthlyInstallment"
            onChange={(event) => updateField("monthlyInstallment", event.target.value)}
            step="1"
            type="number"
            value={draft.monthlyInstallment}
          />
        </FormField>

        <FormField htmlFor="external-chit-total-members" label="Total members">
          <input
            className="w-full rounded-md border border-slate-300 px-3 py-2"
            id="external-chit-total-members"
            name="totalMembers"
            onChange={(event) => updateField("totalMembers", event.target.value)}
            step="1"
            type="number"
            value={draft.totalMembers}
          />
        </FormField>

        <FormField htmlFor="external-chit-total-months" label="Total months">
          <input
            className="w-full rounded-md border border-slate-300 px-3 py-2"
            id="external-chit-total-months"
            name="totalMonths"
            onChange={(event) => updateField("totalMonths", event.target.value)}
            step="1"
            type="number"
            value={draft.totalMonths}
          />
        </FormField>

        <FormField htmlFor="external-chit-user-slots" label="My slots">
          <input
            className="w-full rounded-md border border-slate-300 px-3 py-2"
            id="external-chit-user-slots"
            name="userSlots"
            onChange={(event) => updateField("userSlots", event.target.value)}
            step="1"
            type="number"
            value={draft.userSlots}
          />
        </FormField>

        <FormField htmlFor="external-chit-frequency" label="Cycle frequency">
          <select
            className="w-full rounded-md border border-slate-300 px-3 py-2"
            id="external-chit-frequency"
            name="cycleFrequency"
            onChange={(event) => updateField("cycleFrequency", event.target.value)}
            value={draft.cycleFrequency}
          >
            {cycleFrequencyOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </FormField>

        <FormField htmlFor="external-chit-start-date" label="Start date">
          <input
            className="w-full rounded-md border border-slate-300 px-3 py-2"
            id="external-chit-start-date"
            name="startDate"
            onChange={(event) => updateField("startDate", event.target.value)}
            type="date"
            value={draft.startDate}
          />
        </FormField>

        <FormField htmlFor="external-chit-end-date" label="End date">
          <input
            className="w-full rounded-md border border-slate-300 px-3 py-2"
            id="external-chit-end-date"
            name="endDate"
            onChange={(event) => updateField("endDate", event.target.value)}
            type="date"
            value={draft.endDate}
          />
        </FormField>

        <FormField htmlFor="external-chit-first-month-organizer" label="First month organizer">
          <select
            className="w-full rounded-md border border-slate-300 px-3 py-2"
            id="external-chit-first-month-organizer"
            name="firstMonthOrganizer"
            onChange={(event) => updateField("firstMonthOrganizer", event.target.value === "true")}
            value={draft.firstMonthOrganizer ? "true" : "false"}
          >
            <option value="false">No</option>
            <option value="true">Yes</option>
          </select>
        </FormField>

        <FormField className="md:col-span-2" htmlFor="external-chit-notes" label="Notes">
          <textarea
            className="min-h-24 w-full rounded-md border border-slate-300 px-3 py-2"
            id="external-chit-notes"
            name="notes"
            onChange={(event) => updateField("notes", event.target.value)}
            value={draft.notes}
          />
        </FormField>

        <FormActions className="md:col-span-2">
          <button className="action-button" disabled={submitting} type="submit">
            {submitting ? (isEditMode ? "Saving..." : "Creating...") : isEditMode ? "Save changes" : "Create chit"}
          </button>
          {isEditMode && onCancel ? (
            <button className="rounded-md border border-slate-300 px-4 py-2" onClick={onCancel} type="button">
              Cancel editing
            </button>
          ) : null}
        </FormActions>
      </form>
    </FormFrame>
  );
}
