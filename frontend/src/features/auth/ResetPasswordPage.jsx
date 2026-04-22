import { useState } from "react";
import { Link } from "react-router-dom";

import { FormActions, FormField, FormFrame } from "../../components/form-primitives";
import { getApiErrorMessage } from "../../lib/api-error";
import { confirmPasswordReset, requestPasswordReset } from "./api";

export default function ResetPasswordPage() {
  const [phone, setPhone] = useState("");
  const [resetToken, setResetToken] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [requestingToken, setRequestingToken] = useState(false);
  const [resettingPassword, setResettingPassword] = useState(false);

  async function handleRequestToken(event) {
    event.preventDefault();
    setError("");
    setSuccess("");
    setRequestingToken(true);

    try {
      const data = await requestPasswordReset({ phone });
      if (data?.reset_token) {
        setResetToken(data.reset_token);
        setSuccess("Reset token generated. Use it below to set a new password.");
        return;
      }

      setSuccess(data?.message || "If an account exists, a reset token has been generated.");
    } catch (requestError) {
      setError(
        getApiErrorMessage(requestError, {
          fallbackMessage: "Unable to request a password reset right now.",
        }),
      );
    } finally {
      setRequestingToken(false);
    }
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    setSuccess("");

    if (newPassword !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    if (!resetToken.trim()) {
      setError("Enter the reset token before saving your new password.");
      return;
    }

    setResettingPassword(true);

    try {
      const data = await confirmPasswordReset({
        token: resetToken.trim(),
        new_password: newPassword,
      });
      setSuccess(data?.message || "Password has been reset.");
      setResetToken("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (resetError) {
      setError(
        getApiErrorMessage(resetError, {
          fallbackMessage: "Unable to reset your password right now.",
        }),
      );
    } finally {
      setResettingPassword(false);
    }
  }

  return (
    <main className="app-shell">
      <FormFrame
        description="Request a reset token, then confirm it with your new password."
        success={success}
        title="Reset your password"
      >
        <form className="auction-form" onSubmit={handleSubmit}>
          <FormField htmlFor="resetPhone" label="Phone number">
            <input
              autoComplete="tel"
              className="text-input"
              id="resetPhone"
              onChange={(event) => setPhone(event.target.value)}
              placeholder="9999999999"
              type="tel"
              value={phone}
            />
          </FormField>
          <button className="action-button" disabled={requestingToken} onClick={handleRequestToken} type="button">
            {requestingToken ? "Requesting Token..." : "Request reset token"}
          </button>
          <FormField htmlFor="resetToken" label="Reset token">
            <input
              className="text-input"
              id="resetToken"
              onChange={(event) => setResetToken(event.target.value)}
              placeholder="Paste reset token"
              type="text"
              value={resetToken}
            />
          </FormField>
          <FormField htmlFor="resetPassword" label="New password">
            <input
              autoComplete="new-password"
              className="text-input"
              id="resetPassword"
              onChange={(event) => setNewPassword(event.target.value)}
              placeholder="Enter new password"
              type="password"
              value={newPassword}
            />
          </FormField>
          <FormField htmlFor="resetConfirmPassword" label="Confirm new password">
            <input
              autoComplete="new-password"
              className="text-input"
              id="resetConfirmPassword"
              onChange={(event) => setConfirmPassword(event.target.value)}
              placeholder="Repeat new password"
              type="password"
              value={confirmPassword}
            />
          </FormField>
          {error ? (
            <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-900" role="alert">
              {error}
            </p>
          ) : null}
          <FormActions note="Paste the reset token you received to finish updating your password.">
            <button className="action-button" disabled={resettingPassword} type="submit">
              {resettingPassword ? "Resetting Password..." : "Save New Password"}
            </button>
          </FormActions>
          <div className="auth-links">
            <Link to="/">Back to sign in</Link>
            <Link to="/signup">Need an account?</Link>
          </div>
        </form>
      </FormFrame>
    </main>
  );
}
