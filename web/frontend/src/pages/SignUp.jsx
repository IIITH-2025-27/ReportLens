import { useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth";
import { ErrorNote } from "../components/bits";

export default function SignUp() {
  const { signup } = useAuth();
  const [form, setForm] = useState({ name: "", email: "", password: "", role: "student" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await signup(form);
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  return (
    <div className="auth">
      <form className="card auth-card" onSubmit={submit}>
        <h1 className="brand big">Create your account</h1>
        <fieldset className="roles">
          <legend>I am a</legend>
          {[
            ["student", "Student", "Upload reports and get feedback"],
            ["ta", "Teaching assistant", "Verify and review reports"],
          ].map(([value, title, text]) => (
            <label key={value} className={`role ${form.role === value ? "on" : ""}`}>
              <input type="radio" name="role" value={value} checked={form.role === value} onChange={set("role")} />
              <strong>{title}</strong>
              <span className="muted small">{text}</span>
            </label>
          ))}
        </fieldset>
        <label>
          Full name
          <input value={form.name} onChange={set("name")} autoComplete="name" required />
        </label>
        <label>
          Email
          <input type="email" value={form.email} onChange={set("email")} autoComplete="email" required />
        </label>
        <label>
          Password
          <input type="password" value={form.password} onChange={set("password")} autoComplete="new-password" minLength={8} required />
          <span className="muted small">At least 8 characters</span>
        </label>
        <ErrorNote error={error} />
        <button className="btn primary" disabled={busy}>
          {busy ? "Creating…" : "Create account"}
        </button>
        <p className="muted small">
          Already have an account? <Link to="/signin">Sign in</Link>
        </p>
      </form>
    </div>
  );
}
