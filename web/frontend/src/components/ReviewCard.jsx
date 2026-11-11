import { num, when } from "./bits";

// A review as the student receives it: decision, score, findings, and the claims the TA confirmed.
export default function ReviewCard({ review }) {
  const rework = review.decision === "rework";
  return (
    <div className={`review ${rework ? "warn" : "ok"}`}>
      <div className="review-head">
        <strong>{rework ? "Rework requested" : "Accepted"}</strong>
        {review.score !== null && <span className="score">{num(review.score, 1)} / 100</span>}
        <span className="muted small">
          {review.ta_name} · {when(review.created_at)}
        </span>
      </div>
      {review.findings && <p className="findings">{review.findings}</p>}
      {review.confirmed_claims.length > 0 && (
        <>
          <h4>Numbers that do not match your charts</h4>
          <ul className="claims-plain">
            {review.confirmed_claims.map((c, i) => (
              <li key={i}>
                <q>{c.sentence}</q>
                <div className="muted small">
                  Page {c.page + 1}
                  {c.figure_id && ` · ${c.figure_id.replace(/^fig/, "Figure ")}`}
                  {c.claimed_value !== null && ` · you wrote ${num(c.claimed_value)}`}
                  {c.estimate !== null && ` · the chart reads about ${num(c.estimate)}`}
                </div>
                {c.ta_note && <div className="ta-note">TA: {c.ta_note}</div>}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
