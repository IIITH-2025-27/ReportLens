import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import { Crumbs, Due, ErrorNote, StatusBadge } from "../components/bits";

export default function StudentCourse() {
  const { id } = useParams();
  const [c, setC] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let live = true; // a response that arrives after this page has moved on is dropped
    api.course(id)
      .then((d) => live && setC(d))
      .catch((e) => live && setError(e.message));
    return () => {
      live = false;
    };
  }, [id]);

  if (error) return <ErrorNote error={error} />;
  if (!c) return <p className="muted">Loading…</p>;

  return (
    <>
      <Crumbs />
      <h1>
        {c.code && <span className="muted">{c.code} · </span>}
        {c.name}
      </h1>
      <p className="muted">TA: {c.ta_name}</p>
      <h2>Assignments</h2>
      {c.assignments.length === 0 && <p className="empty">Your TA has not released an assignment in this course yet.</p>}
      {c.assignments.length > 0 && (
        <div className="table-wrap" style={{ marginTop: 10 }}>
          <table>
            <thead>
              <tr>
                <th>Assignment</th>
                <th>Due</th>
                <th>Your report</th>
                <th>Score</th>
              </tr>
            </thead>
            <tbody>
              {c.assignments.map((a) => {
                const s = a.submission;
                return (
                  <tr key={a.id}>
                    <td>
                      <Link to={s ? `/reports/${s.id}` : `/assignments/${a.id}`}>{a.title}</Link>
                    </td>
                    <td>
                      <Due at={a.due_at} />
                    </td>
                    <td>
                      {s ? (
                        <StatusBadge status={s.status} student />
                      ) : (
                        <Link className="btn" to={`/assignments/${a.id}`}>
                          Upload report
                        </Link>
                      )}
                    </td>
                    <td className="num">{s?.latest_score ?? "–"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
