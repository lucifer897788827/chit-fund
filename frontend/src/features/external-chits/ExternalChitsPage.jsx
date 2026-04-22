import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import ExternalChitForm from "./ExternalChitForm";
import ExternalChitHistoryPanel from "./ExternalChitHistoryPanel";
import ExternalChitList from "./ExternalChitList";
import {
  createExternalChitEntry,
  createExternalChit,
  deleteExternalChit,
  fetchExternalChitDetails,
  fetchExternalChitSummary,
  fetchExternalChits,
  updateExternalChitEntry,
  updateExternalChit,
} from "./api";
import { useSignedInShellHeader } from "../../components/signed-in-shell";
import { getApiErrorMessage } from "../../lib/api-error";
import { getCurrentUser } from "../../lib/auth/store";
import { normalizeExternalChit, normalizeExternalChitList, normalizeExternalChitSummary } from "./utils";
import { logoutUser } from "../auth/api";

export default function ExternalChitsPage() {
  const navigate = useNavigate();
  const currentUser = getCurrentUser();
  const [chits, setChits] = useState([]);
  const [chitsLoading, setChitsLoading] = useState(true);
  const [chitsError, setChitsError] = useState("");
  const [selectedChitId, setSelectedChitId] = useState(null);
  const [selectedChit, setSelectedChit] = useState(null);
  const [selectedChitLoading, setSelectedChitLoading] = useState(false);
  const [selectedChitError, setSelectedChitError] = useState("");
  const [selectedChitSummary, setSelectedChitSummary] = useState(null);
  const [selectedChitSummaryLoading, setSelectedChitSummaryLoading] = useState(false);
  const [selectedChitSummaryError, setSelectedChitSummaryError] = useState("");
  const [editingChitId, setEditingChitId] = useState(null);
  const [submitState, setSubmitState] = useState({ mode: null, id: null });
  const [feedback, setFeedback] = useState({ type: "", message: "" });
  const [entrySubmitState, setEntrySubmitState] = useState({ mode: null, id: null });
  const [entryFeedback, setEntryFeedback] = useState({ type: "", message: "" });
  const [deleteTargetId, setDeleteTargetId] = useState(null);
  const [reloadKey, setReloadKey] = useState(0);

  const editingChit = useMemo(() => {
    if (editingChitId === null || editingChitId === undefined) {
      return null;
    }

    return (
      chits.find((chit) => chit.id === editingChitId) ??
      (selectedChitId === editingChitId ? selectedChit : null)
    );
  }, [chits, editingChitId, selectedChit, selectedChitId]);

  async function loadChits() {
    setChitsLoading(true);
    setChitsError("");

    try {
      const data = await fetchExternalChits();
      const normalizedChits = normalizeExternalChitList(data);
      setChits(normalizedChits);

      setSelectedChitId((currentSelectedId) => {
        if (normalizedChits.length === 0) {
          return null;
        }

        const stillPresent = normalizedChits.some((chit) => chit.id === currentSelectedId);
        if (stillPresent) {
          return currentSelectedId;
        }

        return normalizedChits[0].id;
      });
    } catch (error) {
      setChitsError(getApiErrorMessage(error, { fallbackMessage: "Unable to load external chit records right now." }));
    } finally {
      setChitsLoading(false);
    }
  }

  async function loadSelectedChitDetails(chitId) {
    if (!chitId) {
      setSelectedChit(null);
      setSelectedChitError("");
      setSelectedChitLoading(false);
      return;
    }

    setSelectedChitLoading(true);
    setSelectedChitError("");

    try {
      const data = await fetchExternalChitDetails(chitId);
      setSelectedChit(normalizeExternalChit(data));
    } catch (error) {
      setSelectedChitError(
        getApiErrorMessage(error, { fallbackMessage: "Unable to load entry history right now." }),
      );
      setSelectedChit(null);
    } finally {
      setSelectedChitLoading(false);
    }
  }

  async function loadSelectedChitSummary(chitId) {
    if (!chitId) {
      setSelectedChitSummary(null);
      setSelectedChitSummaryError("");
      setSelectedChitSummaryLoading(false);
      return;
    }

    setSelectedChitSummaryLoading(true);
    setSelectedChitSummaryError("");

    try {
      const data = await fetchExternalChitSummary(chitId);
      setSelectedChitSummary(normalizeExternalChitSummary(data));
    } catch (error) {
      setSelectedChitSummaryError(
        getApiErrorMessage(error, { fallbackMessage: "Unable to load summary totals right now." }),
      );
      setSelectedChitSummary(null);
    } finally {
      setSelectedChitSummaryLoading(false);
    }
  }

  useEffect(() => {
    loadChits();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reloadKey]);

  useEffect(() => {
    loadSelectedChitDetails(selectedChitId);
    loadSelectedChitSummary(selectedChitId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedChitId, reloadKey]);

  async function handleLogout() {
    try {
      await logoutUser();
    } finally {
      navigate("/");
    }
  }

  function handleSelectChit(chit) {
    setEditingChitId(null);
    setDeleteTargetId(null);
    setEntryFeedback({ type: "", message: "" });
    setSelectedChitId(chit.id);
  }

  function handleStartEdit(chit) {
    setEditingChitId(chit.id);
    setDeleteTargetId(null);
    setSelectedChitId(chit.id);
    setFeedback({ type: "", message: "" });
    setEntryFeedback({ type: "", message: "" });
  }

  function handleCancelEdit() {
    setEditingChitId(null);
  }

  function handleBeginDelete(chit) {
    setDeleteTargetId(chit.id);
    setFeedback({ type: "", message: "" });
    setEntryFeedback({ type: "", message: "" });
  }

  function handleCancelDelete() {
    setDeleteTargetId(null);
  }

  async function refreshAfterMutation(nextSelectedId) {
    await loadChits();
    if (typeof nextSelectedId === "number" || typeof nextSelectedId === "string") {
      setSelectedChitId(nextSelectedId);
    }
  }

  async function refreshSelectedLedger(chitId) {
    await Promise.all([
      loadSelectedChitDetails(chitId),
      loadSelectedChitSummary(chitId),
    ]);
  }

  async function handleCreate(payload) {
    setSubmitState({ mode: "create", id: null });
    setFeedback({ type: "", message: "" });

    try {
      const createdChit = normalizeExternalChit(await createExternalChit(payload));
      if (createdChit) {
        await refreshAfterMutation(createdChit.id);
      } else {
        await loadChits();
      }
      setEditingChitId(null);
      setFeedback({ type: "success", message: "External chit created." });
    } catch (error) {
      setFeedback({
        type: "error",
        message: getApiErrorMessage(error, { fallbackMessage: "Unable to create this external chit right now." }),
      });
    } finally {
      setSubmitState({ mode: null, id: null });
    }
  }

  async function handleUpdate(payload) {
    if (!editingChitId) {
      return;
    }

    setSubmitState({ mode: "edit", id: editingChitId });
    setFeedback({ type: "", message: "" });

    try {
      const updatedChit = normalizeExternalChit(await updateExternalChit(editingChitId, payload));
      if (updatedChit) {
        await refreshAfterMutation(updatedChit.id);
      } else {
        await loadChits();
      }
      setEditingChitId(null);
      setFeedback({ type: "success", message: "External chit updated." });
    } catch (error) {
      setFeedback({
        type: "error",
        message: getApiErrorMessage(error, { fallbackMessage: "Unable to update this external chit right now." }),
      });
    } finally {
      setSubmitState({ mode: null, id: null });
    }
  }

  async function handleConfirmDelete(chit) {
    setSubmitState({ mode: "delete", id: chit.id });
    setFeedback({ type: "", message: "" });

    try {
      const deletedChit = normalizeExternalChit(await deleteExternalChit(chit.id));
      if (deletedChit) {
        await loadChits();
        setSelectedChitId(deletedChit.id);
      } else {
        await loadChits();
      }
      setDeleteTargetId(null);
      setEditingChitId(null);
      setFeedback({ type: "success", message: "External chit deleted." });
    } catch (error) {
      setFeedback({
        type: "error",
        message: getApiErrorMessage(error, { fallbackMessage: "Unable to delete this external chit right now." }),
      });
    } finally {
      setSubmitState({ mode: null, id: null });
    }
  }

  function handleRetryList() {
    setReloadKey((currentValue) => currentValue + 1);
  }

  function handleRetryHistory() {
    refreshSelectedLedger(selectedChitId);
  }

  function handleRetrySummary() {
    refreshSelectedLedger(selectedChitId);
  }

  async function handleCreateEntry(payload) {
    if (!selectedChitId) {
      return false;
    }

    setEntrySubmitState({ mode: "create-entry", id: selectedChitId });
    setEntryFeedback({ type: "", message: "" });

    try {
      await createExternalChitEntry(selectedChitId, payload);
      await refreshSelectedLedger(selectedChitId);
      setEntryFeedback({ type: "success", message: "Month entry added." });
      return true;
    } catch (error) {
      setEntryFeedback({
        type: "error",
        message: getApiErrorMessage(error, { fallbackMessage: "Unable to save this month entry right now." }),
      });
      return false;
    } finally {
      setEntrySubmitState({ mode: null, id: null });
    }
  }

  async function handleUpdateEntry(entryId, payload) {
    if (!selectedChitId || !entryId) {
      return false;
    }

    setEntrySubmitState({ mode: "edit-entry", id: entryId });
    setEntryFeedback({ type: "", message: "" });

    try {
      await updateExternalChitEntry(selectedChitId, entryId, payload);
      await refreshSelectedLedger(selectedChitId);
      setEntryFeedback({ type: "success", message: "Month entry updated." });
      return true;
    } catch (error) {
      setEntryFeedback({
        type: "error",
        message: getApiErrorMessage(error, { fallbackMessage: "Unable to update this month entry right now." }),
      });
      return false;
    } finally {
      setEntrySubmitState({ mode: null, id: null });
    }
  }

  const shellContextLabel = selectedChit?.title
    ? `${selectedChit.title} · private record`
    : chits.length > 0
      ? `${chits.length} external chits tracked`
      : "Private off-platform chit records";

  useSignedInShellHeader({
    title: "External chits",
    contextLabel: shellContextLabel,
  });

  return (
    <main className="page-shell">
      <header className="space-y-3" id="profile">
        <h1>My External Chits</h1>
        <p>Maintain private records for outside chits in one place.</p>
        <p>
          <Link to={currentUser?.role === "chit_owner" ? "/owner" : "/subscriber"}>Back to dashboard</Link>
        </p>
        <button className="action-button" onClick={handleLogout} type="button">
          Log Out
        </button>
      </header>

      {feedback.message ? (
        <p
          className={`mt-4 rounded-lg border px-3 py-2 text-sm ${
            feedback.type === "error"
              ? "border-red-200 bg-red-50 text-red-900"
              : "border-emerald-200 bg-emerald-50 text-emerald-900"
          }`}
          role={feedback.type === "error" ? "alert" : "status"}
        >
          {feedback.message}
        </p>
      ) : null}

      <div className="panel-grid mt-6" id="home">
        <ExternalChitForm
          chit={editingChit}
          error=""
          mode={editingChit ? "edit" : "create"}
          onCancel={editingChit ? handleCancelEdit : undefined}
          onSubmit={editingChit ? handleUpdate : handleCreate}
          submitting={
            submitState.mode === (editingChit ? "edit" : "create") &&
            submitState.id === (editingChit ? editingChit.id : null)
          }
          success=""
        />

        <ExternalChitList
          chits={chits}
          deleteTargetId={deleteTargetId}
          error={chitsError}
          loading={chitsLoading}
          onCancelDelete={handleCancelDelete}
          onConfirmDelete={handleConfirmDelete}
          onDelete={handleBeginDelete}
          onEdit={handleStartEdit}
          onRetry={handleRetryList}
          onSelect={handleSelectChit}
          selectedChitId={selectedChitId}
        />

        <ExternalChitHistoryPanel
          chit={selectedChit}
          error={selectedChitError}
          feedback={entryFeedback}
          loading={selectedChitLoading}
          onCreateEntry={handleCreateEntry}
          onRetry={handleRetryHistory}
          onRetrySummary={handleRetrySummary}
          onUpdateEntry={handleUpdateEntry}
          submitting={entrySubmitState}
          summary={selectedChitSummary}
          summaryError={selectedChitSummaryError}
          summaryLoading={selectedChitSummaryLoading}
        />
      </div>
    </main>
  );
}
