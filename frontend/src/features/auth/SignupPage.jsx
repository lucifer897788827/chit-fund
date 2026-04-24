import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { FormActions, FormField, FormFrame } from "../../components/form-primitives";
import { getApiErrorMessage } from "../../lib/api-error";
import { getDashboardPath, saveSession } from "../../lib/auth/store";
import { signupUser } from "./api";

export default function SignupPage() {
  const navigate = useNavigate();
  const [fullName, setFullName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    setSuccess("");

    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    setSubmitting(true);

    try {
      const session = await signupUser({
        fullName,
        phone,
        email: email.trim() || undefined,
        password,
      });
      saveSession(session);
      setSuccess("Your subscriber account is ready.");
      navigate(getDashboardPath(session));
    } catch (signupError) {
      setError(
        getApiErrorMessage(signupError, {
          fallbackMessage: "Unable to create your account right now.",
        }),
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="app-shell">
      <FormFrame
        description="Create a subscriber account and sign in immediately."
        success={success}
        title="Create your account"
      >
        <form className="auction-form" onSubmit={handleSubmit}>
          <FormField htmlFor="fullName" label="Full name">
            <input
              autoComplete="name"
              className="text-input"
              id="fullName"
              onChange={(event) => setFullName(event.target.value)}
              placeholder="Enter your name"
              type="text"
              value={fullName}
            />
          </FormField>
          <FormField htmlFor="signupPhone" label="Phone number">
            <input
              autoComplete="tel"
              className="text-input"
              id="signupPhone"
              onChange={(event) => setPhone(event.target.value)}
              placeholder="9999999999"
              type="tel"
              value={phone}
            />
          </FormField>
          <FormField htmlFor="signupEmail" label="Email address (optional)">
            <input
              autoComplete="email"
              className="text-input"
              id="signupEmail"
              onChange={(event) => setEmail(event.target.value)}
              placeholder="name@example.com"
              type="email"
              value={email}
            />
          </FormField>
          <FormField htmlFor="signupPassword" label="Password">
            <input
              autoComplete="new-password"
              className="text-input"
              id="signupPassword"
              onChange={(event) => setPassword(event.target.value)}
              placeholder="Create password"
              type="password"
              value={password}
            />
          </FormField>
          <FormField htmlFor="confirmPassword" label="Confirm password">
            <input
              autoComplete="new-password"
              className="text-input"
              id="confirmPassword"
              onChange={(event) => setConfirmPassword(event.target.value)}
              placeholder="Repeat password"
              type="password"
              value={confirmPassword}
            />
          </FormField>
          {error ? (
            <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-900" role="alert">
              {error}
            </p>
          ) : null}
          <FormActions note="Self-service signup creates a subscriber account.">
            <button className="action-button" disabled={submitting} type="submit">
              {submitting ? "Creating Account..." : "Create Account"}
            </button>
          </FormActions>
          <div className="auth-links">
            <span>Already have access?</span>
            <Link to="/">Sign in</Link>
          </div>
        </form>
      </FormFrame>
    </main>
  );
}
