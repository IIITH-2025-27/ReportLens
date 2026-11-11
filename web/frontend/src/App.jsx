import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth";
import Layout from "./components/Layout";
import SignIn from "./pages/SignIn";
import SignUp from "./pages/SignUp";
import Courses from "./pages/Courses";
import StudentAssignment from "./pages/StudentAssignment";
import StudentCourse from "./pages/StudentCourse";
import StudentReport from "./pages/StudentReport";
import TAAssignment from "./pages/TAAssignment";
import TACourse from "./pages/TACourse";
import TAReport from "./pages/TAReport";

export default function App() {
  const { user, loading } = useAuth();
  if (loading) return <p className="center muted">Loading…</p>;

  if (!user) {
    return (
      <Routes>
        <Route path="/signin" element={<SignIn />} />
        <Route path="/signup" element={<SignUp />} />
        <Route path="*" element={<Navigate to="/signin" replace />} />
      </Routes>
    );
  }

  // The portal is chosen by the role stored with the account.
  const ta = user.role === "ta";
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Courses />} />
        <Route path="/courses/:id" element={ta ? <TACourse /> : <StudentCourse />} />
        <Route path="/assignments/:id" element={ta ? <TAAssignment /> : <StudentAssignment />} />
        <Route path="/reports/:id" element={ta ? <TAReport /> : <StudentReport />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  );
}
