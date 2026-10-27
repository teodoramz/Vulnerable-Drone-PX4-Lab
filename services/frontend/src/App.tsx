import { Navigate, Route, Routes } from "react-router-dom";

import { useAuth } from "./auth/AuthContext";
import RequireAuth from "./auth/RequireAuth";
import Layout from "./components/Layout";
import Admin from "./pages/Admin";
import Audit from "./pages/Audit";
import Inventory from "./pages/Inventory";
import Login from "./pages/Login";
import Network from "./pages/Network";
import Operations from "./pages/Operations";

export default function App() {
  const { loading, user } = useAuth();

  if (loading) {
    return <div className="h-full flex items-center justify-center text-slate-400">Loading…</div>;
  }

  return (
    <Routes>
      <Route path="/login" element={user ? <Navigate to="/" replace /> : <Login />} />
      <Route
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route path="/" element={<Operations />} />
        <Route path="/network" element={<Network />} />
        <Route path="/inventory" element={<Inventory />} />
        <Route
          path="/admin"
          element={
            <RequireAuth roles={["admin"]}>
              <Admin />
            </RequireAuth>
          }
        />
        <Route
          path="/audit"
          element={
            <RequireAuth roles={["admin", "operator"]}>
              <Audit />
            </RequireAuth>
          }
        />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
