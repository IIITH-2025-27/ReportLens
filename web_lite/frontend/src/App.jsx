import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import History from "./pages/History";
import Report from "./pages/Report";
import Upload from "./pages/Upload";

// Open to everyone: no sign-in, no accounts.
export default function App() {
  return (
    <>
      <header className="topbar">
        <div className="topbar-in">
          <NavLink to="/" className="brand">
            ReportLens
          </NavLink>
          <span className="portal">Lite</span>
          <span className="spacer" />
          <nav className="nav">
            <NavLink to="/" end>
              Upload
            </NavLink>
            <NavLink to="/history">History</NavLink>
          </nav>
        </div>
      </header>
      <main className="page">
        <Routes>
          <Route path="/" element={<Upload />} />
          <Route path="/history" element={<History />} />
          <Route path="/reports/:id" element={<Report />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </>
  );
}
