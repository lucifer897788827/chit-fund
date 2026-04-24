import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { FormActions, FormField, FormFrame } from "../../components/form-primitives";
import { loginUser } from "./api";
import { getApiErrorMessage } from "../../lib/api-error";
import { getDashboardPath, saveSession } from "../../lib/auth/store";

export default function LoginPage() {
  const navigate = useNavigate();
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setSubmitting(true);
    setError("");

    try {
      const session = await loginUser({ phone, password });
      saveSession(session);
      navigate(getDashboardPath(session));
    } catch (loginError) {
      setError(
        getApiErrorMessage(loginError, {
          fallbackMessage: "Invalid phone number or password.",
        }),
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="app-shell">
      <FormFrame description="Access your chit dashboard and live auctions." title="Sign in">
        <form className="auction-form" onSubmit={handleSubmit}>
          <FormField htmlFor="phone" label="Phone number">
            <input
              className="text-input"
              id="phone"
              onChange={(event) => setPhone(event.target.value)}
              placeholder="Enter phone number"
              type="tel"
              value={phone}
            />
          </FormField>
          <FormField htmlFor="password" label="Password">
            <input
              className="text-input"
              id="password"
              onChange={(event) => setPassword(event.target.value)}
              placeholder="Enter password"
              type="password"
              value={password}
            />
          </FormField>
          {error ? (
            <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-900" role="alert">
              {error}
            </p>
          ) : null}
          <FormActions>
            <button className="action-button" disabled={submitting} type="submit">
              {submitting ? "Signing In..." : "Sign In"}
            </button>
          </FormActions>
          <div className="auth-links">
            <Link to="/signup">Create an account</Link>
            <Link to="/reset-password">Forgot password?</Link>
          </div>
        </form>
      </FormFrame>
    </main>
  );
}
