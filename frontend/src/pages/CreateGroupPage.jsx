import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { FormActions, FormField, FormFrame } from "../components/form-primitives";
import { useAppShellHeader } from "../components/app-shell";
import { getApiErrorMessage } from "../lib/api-error";
import { getCurrentUser } from "../lib/auth/store";
import { createGroup } from "../features/auctions/api";

function getOwnerId(currentUser) {
  return currentUser?.owner_id ?? currentUser?.ownerId ?? null;
}

export default function CreateGroupPage() {
  const navigate = useNavigate();
  const ownerId = getOwnerId(getCurrentUser());
  const [draft, setDraft] = useState({
    groupCode: "",
    title: "",
    chitValue: "",
    installmentAmount: "",
    memberCount: "",
    cycleCount: "",
    autoCycleCalculation: false,
    cycleFrequency: "monthly",
    commissionType: "NONE",
    auctionType: "LIVE",
    groupType: "STANDARD",
    visibility: "private",
    startDate: "",
    firstAuctionDate: "",
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useAppShellHeader({
    title: "Create group",
    contextLabel: "Owner-only group setup",
  });

  function updateDraft(field, value) {
    setDraft((current) => ({ ...current, [field]: value }));
    setError("");
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (submitting) {
      return;
    }
    if (!ownerId) {
      setError("Owner profile required.");
      return;
    }

    setSubmitting(true);
    try {
      const group = await createGroup({
        ownerId,
        groupCode: draft.groupCode.trim(),
        title: draft.title.trim(),
        chitValue: Number(draft.chitValue),
        installmentAmount: Number(draft.installmentAmount),
        memberCount: Number(draft.memberCount),
        cycleCount: Number(draft.cycleCount),
        autoCycleCalculation: draft.autoCycleCalculation,
        cycleFrequency: draft.cycleFrequency,
        commissionType: draft.commissionType,
        auctionType: draft.auctionType,
        groupType: draft.groupType,
        visibility: draft.visibility,
        startDate: draft.startDate,
        firstAuctionDate: draft.firstAuctionDate,
      });
      navigate(`/groups/${group.id}`);
    } catch (createError) {
      setError(getApiErrorMessage(createError, { fallbackMessage: "Unable to create this group right now." }));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="page-shell">
      <FormFrame
        description="Create the group shell first, then manage members, auctions, payments, and settings from the group detail route."
        error={error}
        title="Create chit group"
      >
        <form className="grid gap-4 md:grid-cols-2" onSubmit={handleSubmit}>
          <FormField htmlFor="groupCode" label="Group code">
            <input className="text-input" id="groupCode" onChange={(event) => updateDraft("groupCode", event.target.value)} value={draft.groupCode} />
          </FormField>
          <FormField htmlFor="title" label="Title">
            <input className="text-input" id="title" onChange={(event) => updateDraft("title", event.target.value)} value={draft.title} />
          </FormField>
          <FormField htmlFor="chitValue" label="Chit value">
            <input className="text-input" id="chitValue" min="1" onChange={(event) => updateDraft("chitValue", event.target.value)} type="number" value={draft.chitValue} />
          </FormField>
          <FormField htmlFor="installmentAmount" label="Installment amount">
            <input className="text-input" id="installmentAmount" min="1" onChange={(event) => updateDraft("installmentAmount", event.target.value)} type="number" value={draft.installmentAmount} />
          </FormField>
          <FormField htmlFor="memberCount" label="Member count">
            <input className="text-input" id="memberCount" min="1" onChange={(event) => updateDraft("memberCount", event.target.value)} type="number" value={draft.memberCount} />
          </FormField>
          <FormField htmlFor="cycleCount" label="Cycle count">
            <input
              className="text-input"
              disabled={draft.autoCycleCalculation}
              id="cycleCount"
              min="1"
              onChange={(event) => updateDraft("cycleCount", event.target.value)}
              type="number"
              value={draft.cycleCount}
            />
          </FormField>
          <FormField htmlFor="autoCycleCalculation" label="Auto-calculate cycle count">
            <input
              checked={draft.autoCycleCalculation}
              id="autoCycleCalculation"
              onChange={(event) => updateDraft("autoCycleCalculation", event.target.checked)}
              type="checkbox"
            />
          </FormField>
          <FormField htmlFor="cycleFrequency" label="Cycle frequency">
            <select className="text-input" id="cycleFrequency" onChange={(event) => updateDraft("cycleFrequency", event.target.value)} value={draft.cycleFrequency}>
              <option value="monthly">Monthly</option>
              <option value="weekly">Weekly</option>
            </select>
          </FormField>
          <FormField htmlFor="commissionType" label="Commission type">
            <select className="text-input" id="commissionType" onChange={(event) => updateDraft("commissionType", event.target.value)} value={draft.commissionType}>
              <option value="NONE">None</option>
              <option value="FIRST_MONTH">First month</option>
              <option value="PERCENTAGE">Percentage</option>
              <option value="FIXED_AMOUNT">Fixed amount</option>
            </select>
          </FormField>
          <FormField htmlFor="auctionType" label="Auction type">
            <select className="text-input" id="auctionType" onChange={(event) => updateDraft("auctionType", event.target.value)} value={draft.auctionType}>
              <option value="LIVE">Live</option>
              <option value="BLIND">Blind</option>
              <option value="FIXED">Fixed</option>
            </select>
          </FormField>
          <FormField htmlFor="groupType" label="Group type">
            <select className="text-input" id="groupType" onChange={(event) => updateDraft("groupType", event.target.value)} value={draft.groupType}>
              <option value="STANDARD">Standard</option>
              <option value="MULTI_SLOT">Multi-slot</option>
            </select>
          </FormField>
          <FormField htmlFor="visibility" label="Visibility">
            <select className="text-input" id="visibility" onChange={(event) => updateDraft("visibility", event.target.value)} value={draft.visibility}>
              <option value="private">Private</option>
              <option value="public">Public</option>
            </select>
          </FormField>
          <FormField htmlFor="startDate" label="Start date">
            <input className="text-input" id="startDate" onChange={(event) => updateDraft("startDate", event.target.value)} type="date" value={draft.startDate} />
          </FormField>
          <FormField htmlFor="firstAuctionDate" label="First auction date">
            <input className="text-input" id="firstAuctionDate" onChange={(event) => updateDraft("firstAuctionDate", event.target.value)} type="date" value={draft.firstAuctionDate} />
          </FormField>
          <FormActions className="md:col-span-2" note="Advanced auction and payment actions move to the group detail screen after creation.">
            <button className="action-button" disabled={submitting} type="submit">
              {submitting ? "Creating..." : "Create group"}
            </button>
          </FormActions>
        </form>
      </FormFrame>
    </main>
  );
}
