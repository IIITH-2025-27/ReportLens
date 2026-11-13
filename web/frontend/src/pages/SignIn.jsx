import { useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth";
import { ErrorNote } from "../components/bits";

export default function SignIn() {
  const { signin } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await signin({ email, password }); // the account's role decides which portal opens
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  return (
    <div className="auth">
      <form className="card auth-card" onSubmit={submit}>
        <h1 className="brand big">ReportLens</h1>
        <p className="muted">Sign in with your email. You are taken to the student or TA portal that your account belongs to.</p>
        <label>
          Email
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" required autoFocus />
        </label>
        <label>
          Password
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required />
        </label>
        <ErrorNote error={error} />
        <button className="btn primary" disabled={busy}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
        <p className="muted small">
          No account yet? <Link to="/signup">Create one</Link>
        </p>
      </form>
    </div>
  );
}
