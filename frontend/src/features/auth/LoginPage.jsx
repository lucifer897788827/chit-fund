import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { loginUser } from "./api";
import { saveSession } from "../../lib/auth/store";

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
      navigate(session.role === "chit_owner" ? "/owner" : "/subscriber");
    } catch (_error) {
      setError("Invalid phone number or password.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="app-shell">
      <section className="auth-card">
        <h1>Sign In</h1>
        <p>Access your chit dashboard and live auctions.</p>
        <form className="auction-form" onSubmit={handleSubmit}>
          <label className="field-label" htmlFor="phone">
            Phone Number
          </label>
          <input
            className="text-input"
            id="phone"
            onChange={(event) => setPhone(event.target.value)}
            placeholder="9999999999"
            type="tel"
            value={phone}
          />
          <label className="field-label" htmlFor="password">
            Password
          </label>
          <input
            className="text-input"
            id="password"
            onChange={(event) => setPassword(event.target.value)}
            placeholder="Enter password"
            type="password"
            value={password}
          />
          {error ? <p>{error}</p> : null}
          <button className="action-button" disabled={submitting} type="submit">
            {submitting ? "Signing In..." : "Sign In"}
          </button>
        </form>
        <p>Demo owner: 9999999999 / secret123</p>
        <p>Demo subscriber: 8888888888 / pass123</p>
      </section>
    </main>
  );
}
