import { useEffect, useState } from "react";

import { FormActions, FormField, FormFrame } from "../../components/form-primitives";

function buildInitialDraft(mode, ownerId, subscriber) {
  return {
    ownerId: ownerId ?? "",
    fullName: subscriber?.fullName ?? "",
    phone: subscriber?.phone ?? "",
    email: subscriber?.email ?? "",
    password: mode === "create" ? "" : undefined,
  };
}

export default function SubscriberForm({
  mode = "create",
  ownerId,
  subscriber,
  resetSignal = 0,
  submitting = false,
  error = "",
  success = "",
  onSubmit,
  onCancel,
}) {
  const [draft, setDraft] = useState(() => buildInitialDraft(mode, ownerId, subscriber));

  useEffect(() => {
    setDraft(buildInitialDraft(mode, ownerId, subscriber));
  }, [mode, ownerId, subscriber, resetSignal]);

  function updateField(field, value) {
    setDraft((currentDraft) => ({
      ...currentDraft,
      [field]: value,
    }));
  }

  function handleSubmit(event) {
    event.preventDefault();

    const payload = {
      ownerId: draft.ownerId === "" ? undefined : Number(draft.ownerId),
      fullName: draft.fullName.trim(),
      phone: draft.phone.trim(),
      email: draft.email.trim() || null,
    };

    if (mode === "create") {
      payload.password = draft.password;
    }

    if (typeof onSubmit === "function") {
      onSubmit(payload);
    }
  }

  const isCreateMode = mode === "create";

  return (
    <FormFrame
      description={
        isCreateMode
          ? "Create a new owner-scoped subscriber account and keep it ready for future membership assignment."
          : "Update the subscriber profile while keeping the record in the management list."
      }
      error={error}
      success={success}
      title={isCreateMode ? "Add subscriber" : "Edit subscriber"}
    >
      <form className="grid gap-4 md:grid-cols-2" onSubmit={handleSubmit}>
        <input hidden name="ownerId" readOnly value={draft.ownerId} />

        <FormField className="md:col-span-2" htmlFor="subscriber-fullName" label="Full name">
          <input
            className="w-full rounded-md border border-slate-300 px-3 py-2"
            id="subscriber-fullName"
            name="fullName"
            onChange={(event) => updateField("fullName", event.target.value)}
            type="text"
            value={draft.fullName}
          />
        </FormField>

        <FormField htmlFor="subscriber-phone" label="Phone">
          <input
            className="w-full rounded-md border border-slate-300 px-3 py-2"
            id="subscriber-phone"
            name="phone"
            onChange={(event) => updateField("phone", event.target.value)}
            type="text"
            value={draft.phone}
          />
        </FormField>

        <FormField htmlFor="subscriber-email" label="Email">
          <input
            className="w-full rounded-md border border-slate-300 px-3 py-2"
            id="subscriber-email"
            name="email"
            onChange={(event) => updateField("email", event.target.value)}
            type="email"
            value={draft.email}
          />
        </FormField>

        {isCreateMode ? (
          <FormField className="md:col-span-2" htmlFor="subscriber-password" label="Temporary password">
            <input
              className="w-full rounded-md border border-slate-300 px-3 py-2"
              id="subscriber-password"
              name="password"
              onChange={(event) => updateField("password", event.target.value)}
              type="password"
              value={draft.password}
            />
          </FormField>
        ) : null}

        <FormActions className="md:col-span-2" note={isCreateMode ? "The temporary password can be shared securely with the subscriber." : undefined}>
          <button className="action-button" disabled={submitting} type="submit">
            {submitting ? (isCreateMode ? "Creating..." : "Saving...") : isCreateMode ? "Create subscriber" : "Save changes"}
          </button>
          {onCancel ? (
            <button className="rounded-md border border-slate-300 px-4 py-2" onClick={onCancel} type="button">
              Cancel
            </button>
          ) : null}
        </FormActions>
      </form>
    </FormFrame>
  );
}
