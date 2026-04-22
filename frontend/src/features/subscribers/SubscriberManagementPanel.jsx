import { useEffect, useState } from "react";

import { PageErrorState, PageLoadingState } from "../../components/page-state";
import { getApiErrorMessage } from "../../lib/api-error";
import {
  createSubscriber,
  deactivateSubscriber,
  fetchSubscribers,
  updateSubscriber,
} from "./api";
import SubscriberForm from "./SubscriberForm";
import SubscriberList from "./SubscriberList";

function normalizeSubscriber(subscriber) {
  if (!subscriber || typeof subscriber !== "object") {
    return null;
  }

  return {
    id: subscriber.id,
    ownerId: subscriber.ownerId ?? subscriber.owner_id ?? null,
    fullName: subscriber.fullName ?? subscriber.full_name ?? "",
    phone: subscriber.phone ?? "",
    email: subscriber.email ?? null,
    status: subscriber.status ?? "active",
  };
}

function normalizeSubscriberList(items) {
  return (Array.isArray(items) ? items : []).map(normalizeSubscriber).filter(Boolean);
}

export default function SubscriberManagementPanel({ ownerId }) {
  const [subscribers, setSubscribers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [editingSubscriber, setEditingSubscriber] = useState(null);
  const [actionState, setActionState] = useState({
    mode: null,
    id: null,
  });
  const [feedback, setFeedback] = useState({
    type: "",
    message: "",
  });
  const [createResetSignal, setCreateResetSignal] = useState(0);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let active = true;

    setLoading(true);
    setLoadError("");

    fetchSubscribers()
      .then((data) => {
        if (active) {
          setSubscribers(normalizeSubscriberList(data));
        }
      })
      .catch((error) => {
        if (active) {
          setLoadError(
            getApiErrorMessage(error, { fallbackMessage: "Unable to load subscribers right now." }),
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
  }, [reloadToken]);

  function setSuccess(message) {
    setFeedback({ type: "success", message });
  }

  function setError(error, fallbackMessage) {
    setFeedback({
      type: "error",
      message: getApiErrorMessage(error, { fallbackMessage }),
    });
  }

  async function handleCreate(payload) {
    setActionState({ mode: "create", id: null });
    setFeedback({ type: "", message: "" });

    try {
      const createdSubscriber = normalizeSubscriber(await createSubscriber(payload));
      if (createdSubscriber) {
        setSubscribers((currentSubscribers) => [createdSubscriber, ...currentSubscribers]);
      }
      setCreateResetSignal((currentSignal) => currentSignal + 1);
      setSuccess("Subscriber created.");
    } catch (error) {
      setError(error, "Unable to create this subscriber right now.");
    } finally {
      setActionState({ mode: null, id: null });
    }
  }

  async function handleUpdate(payload) {
    if (!editingSubscriber) {
      return;
    }

    setActionState({ mode: "edit", id: editingSubscriber.id });
    setFeedback({ type: "", message: "" });

    try {
      const updatedSubscriber = normalizeSubscriber(
        await updateSubscriber(editingSubscriber.id, payload),
      );
      if (updatedSubscriber) {
        setSubscribers((currentSubscribers) =>
          currentSubscribers.map((subscriber) =>
            subscriber.id === updatedSubscriber.id ? updatedSubscriber : subscriber,
          ),
        );
      }
      setEditingSubscriber(null);
      setSuccess("Subscriber updated.");
    } catch (error) {
      setError(error, "Unable to update this subscriber right now.");
    } finally {
      setActionState({ mode: null, id: null });
    }
  }

  async function handleDeactivate(subscriber) {
    const confirmMessage = `Deactivate ${subscriber.fullName}? This will keep the record visible as deleted/inactive.`;
    if (typeof window !== "undefined" && typeof window.confirm === "function") {
      const confirmed = window.confirm(confirmMessage);
      if (!confirmed) {
        return;
      }
    }

    setActionState({ mode: "delete", id: subscriber.id });
    setFeedback({ type: "", message: "" });

    try {
      const deletedSubscriber = normalizeSubscriber(await deactivateSubscriber(subscriber.id));
      if (deletedSubscriber) {
        setSubscribers((currentSubscribers) =>
          currentSubscribers.map((currentSubscriber) =>
            currentSubscriber.id === deletedSubscriber.id ? deletedSubscriber : currentSubscriber,
          ),
        );
      }
      if (editingSubscriber?.id === subscriber.id) {
        setEditingSubscriber(null);
      }
      setSuccess("Subscriber deactivated.");
    } catch (error) {
      setError(error, "Unable to deactivate this subscriber right now.");
    } finally {
      setActionState({ mode: null, id: null });
    }
  }

  function startEdit(subscriber) {
    setEditingSubscriber(subscriber);
    setFeedback({ type: "", message: "" });
  }

  const isSubmittingCreate = actionState.mode === "create";
  const isSubmittingEdit = actionState.mode === "edit" && actionState.id === editingSubscriber?.id;

  return (
    <section className="space-y-6">
      <div className="space-y-2">
        <h1>Subscriber Management</h1>
        <p>Manage owner-scoped subscribers, keep deactivated rows visible, and update records in place.</p>
      </div>

      {loading ? (
        <PageLoadingState
          description="Fetching the latest owner-scoped subscriber list."
          label="Loading subscribers..."
        />
      ) : null}

      {!loading && loadError ? (
        <PageErrorState
          error={loadError}
          fallbackMessage="Unable to load subscribers right now."
          onRetry={() => setReloadToken((currentToken) => currentToken + 1)}
          title="We could not load the subscriber list."
        />
      ) : null}

      {!loading && !loadError ? (
        <>
          <SubscriberForm
            key={editingSubscriber ? `edit-${editingSubscriber.id}` : `create-${createResetSignal}`}
            mode={editingSubscriber ? "edit" : "create"}
            onCancel={editingSubscriber ? () => setEditingSubscriber(null) : undefined}
            onSubmit={editingSubscriber ? handleUpdate : handleCreate}
            ownerId={ownerId}
            resetSignal={createResetSignal}
            subscriber={editingSubscriber}
            submitting={editingSubscriber ? isSubmittingEdit : isSubmittingCreate}
            error={feedback.type === "error" ? feedback.message : ""}
            success={feedback.type === "success" ? feedback.message : ""}
          />

          <SubscriberList
            onDeactivate={handleDeactivate}
            onEdit={startEdit}
            subscribers={subscribers}
          />
        </>
      ) : null}
    </section>
  );
}
