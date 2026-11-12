import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import { Crumbs, Due, ErrorNote } from "../components/bits";

export default function TACourse() {
  const { id } = useParams();
  const [c, setC] = useState(null);
  const [error, setError] = useState("");

  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [due, setDue] = useState("");
  const [aBusy, setABusy] = useState(false);
  const [aError, setAError] = useState("");

  const [emails, setEmails] = useState("");
  const [sBusy, setSBusy] = useState(false);
  const [sError, setSError] = useState("");
  const [added, setAdded] = useState(null); // result of the last "add students"

  useEffect(() => {
    let live = true; // a response that arrives after this page has moved on is dropped
    api.course(id)
      .then((d) => live && setC(d))
      .catch((e) => live && setError(e.message));
    return () => {
      live = false;
    };
  }, [id]);

  async function release(e) {
    e.preventDefault();
    setABusy(true);
    setAError("");
    try {
      await api.createAssignment(id, { title, description, due_at: due ? new Date(due).toISOString() : null });
      setTitle("");
      setDescription("");
      setDue("");
      setC(await api.course(id));
    } catch (err) {
      setAError(err.message);
    }
    setABusy(false);
  }

  async function addStudents(e) {
    e.preventDefault();
    const list = emails.split(/[\s,;]+/).filter(Boolean);
    if (list.length === 0) return setSError("Enter at least one email address");
    setSBusy(true);
    setSError("");
    try {
      const r = await api.addStudents(id, list);
      setC(r.course);
      setAdded(r);
      setEmails(r.rejected.map((x) => x.email).join("\n")); // keep the ones to fix
    } catch (err) {
      setSError(err.message);
    }
    setSBusy(false);
  }

  async function remove(m) {
    if (!window.confirm(`Remove ${m.email} from this course? Reports they already submitted are kept.`)) return;
    setSError("");
    try {
      setC(await api.removeStudent(id, m.id));
      setAdded(null);
    } catch (err) {
      setSError(err.message);
    }
  }

  if (error) return <ErrorNote error={error} />;
  if (!c) return <p className="muted">Loading…</p>;

  return (
    <>
      <Crumbs />
      <h1>
        {c.code && <span className="muted">{c.code} · </span>}
        {c.name}
      </h1>
      <div className="two">
        <section>
          <h2>Assignments</h2>
          <form className="card upload" onSubmit={release}>
            <h3>Release an assignment</h3>
            <p className="muted small">Students on this course see it straight away and can upload their report to it.</p>
            <div className="row">
              <label className="grow">
                Title
                <input id="a-title" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Lab 3: CNN architectures" maxLength={200} required />
              </label>
              <label>
                Due (optional)
                <input id="a-due" type="datetime-local" value={due} onChange={(e) => setDue(e.target.value)} />
              </label>
            </div>
            <label>
              Instructions (optional)
              <textarea id="a-desc" rows={3} value={description} onChange={(e) => setDescription(e.target.value)} maxLength={10000} placeholder="What the report should contain." />
            </label>
            <div className="row end">
              <button className="btn primary" disabled={aBusy}>
                {aBusy ? "Releasing…" : "Release assignment"}
              </button>
            </div>
            <ErrorNote error={aError} />
          </form>

          {c.assignments.length === 0 && <p className="empty">No assignments yet. Release the first one above.</p>}
          {c.assignments.length > 0 && (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Assignment</th>
                    <th>Due</th>
                    <th>Submitted</th>
                    <th>To review</th>
                  </tr>
                </thead>
                <tbody>
                  {c.assignments.map((a) => (
                    <tr key={a.id}>
                      <td>
                        <Link to={`/assignments/${a.id}`}>{a.title}</Link>
                      </td>
                      <td>
                        <Due at={a.due_at} />
                      </td>
                      <td className="num">
                        {a.submitted} of {a.students}
                      </td>
                      <td className="num">{a.to_review > 0 ? <span className="badge info">{a.to_review}</span> : "0"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section>
          <h2>Students ({c.members.length})</h2>
          <form className="card upload" onSubmit={addStudents}>
            <h3>Add students</h3>
            <label>
              Email addresses, one per line or separated by commas
              <textarea id="s-emails" rows={3} value={emails} onChange={(e) => setEmails(e.target.value)} placeholder={"asha@university.edu\nravi@university.edu"} />
            </label>
            <p className="muted small">A student who has not signed up yet sees the course once they create an account with that email.</p>
            <div className="row end">
              <button className="btn primary" disabled={sBusy}>
                {sBusy ? "Adding…" : "Add to course"}
              </button>
            </div>
            <ErrorNote error={sError} />
            {added && (
              <p className="note" role="status">
                {added.added.length} added
                {added.already.length > 0 && `, ${added.already.length} already on the course`}
                {added.rejected.length > 0 && `. Not added: ${added.rejected.map((x) => `${x.email} (${x.why})`).join(", ")}`}
              </p>
            )}
          </form>

          {c.members.length === 0 && <p className="empty">No students on this course yet.</p>}
          {c.members.length > 0 && (
            <ul className="people card">
              {c.members.map((m) => (
                <li key={m.id}>
                  <div>
                    {m.name || <span className="muted">Not signed up yet</span>}
                    <div className="muted small">{m.email}</div>
                  </div>
                  <button className="btn ghost danger" onClick={() => remove(m)} aria-label={`Remove ${m.email}`}>
                    Remove
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </>
  );
}
