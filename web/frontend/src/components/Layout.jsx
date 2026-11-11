import { Link } from "react-router-dom";
import { useAuth } from "../auth";

export default function Layout({ children }) {
  const { user, signout } = useAuth();
  return (
    <>
      <header className="topbar">
        <div className="topbar-in">
          <Link to="/" className="brand">
            ReportLens
          </Link>
          <span className="portal">{user.role === "ta" ? "TA portal" : "Student portal"}</span>
          <span className="spacer" />
          <span className="who">
            {user.name} <span className="muted">· {user.email}</span>
          </span>
          <button className="btn ghost" onClick={signout}>
            Sign out
          </button>
        </div>
      </header>
      <main className="page">{children}</main>
    </>
  );
}
