import { useEffect, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";
import { FleetSocketProvider } from "../ws/FleetSocketProvider";
import { DroneMark, Wordmark } from "./Brand";
import { clockGmt3, DISPLAY_TZ_LABEL } from "../lib/time";

const navClass = ({ isActive }: { isActive: boolean }) =>
  `px-1 pb-0.5 border-b-2 transition-colors ${
    isActive ? "text-slate-100 border-blue-500" : "text-slate-400 border-transparent hover:text-slate-200"
  }`;

function MissionClock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);
  return (
    <span className="font-mono text-slate-400 tabular-nums" title={`Mission time (${DISPLAY_TZ_LABEL})`}>
      {clockGmt3(now)} {DISPLAY_TZ_LABEL}
    </span>
  );
}

export default function Layout() {
  const { user, logout } = useAuth();
  const isAdmin = user?.role === "admin";
  // Mirrors Permission.AUDIT_READ in the C2's rbac.py.
  const canReadAudit = isAdmin || user?.role === "operator";
  const roleStyle =
    user?.role === "admin"
      ? "border-amber-500/60 text-amber-300"
      : user?.role === "operator"
        ? "border-blue-500/60 text-blue-300"
        : "border-slate-600 text-slate-400";

  return (
    <div className="h-full flex flex-col">
      <div className="h-0.5 shrink-0 bg-gradient-to-r from-blue-600 via-blue-400 to-transparent" />
      <header className="h-12 shrink-0 bg-slate-900 border-b border-slate-800 flex items-center px-4 gap-7">
        <div className="flex items-center gap-2.5">
          <DroneMark />
          <Wordmark />
        </div>
        <nav className="flex gap-5 text-sm">
          <NavLink to="/" className={navClass} end>
            Operations
          </NavLink>
          <NavLink to="/network" className={navClass}>
            Network
          </NavLink>
          {/* Open to every role. */}
          <NavLink to="/inventory" className={navClass}>
            Inventory
          </NavLink>
          {isAdmin && (
            <NavLink to="/admin" className={navClass}>
              Users
            </NavLink>
          )}
          {canReadAudit && (
            <NavLink to="/audit" className={navClass}>
              Audit
            </NavLink>
          )}
        </nav>
        <div className="ml-auto flex items-center gap-4 text-xs">
          <MissionClock />
          <div className="flex items-center gap-2">
            <span className="text-slate-300">{user?.username}</span>
            <span className={`uppercase text-label font-semibold tracking-wide border rounded-full px-2 py-0.5 ${roleStyle}`}>
              {user?.role}
            </span>
          </div>
          <button
            onClick={logout}
            className="bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded px-2.5 py-1 text-slate-300"
          >
            Sign out
          </button>
        </div>
      </header>
      <main className="flex-1 min-h-0">
        <FleetSocketProvider>
          <Outlet />
        </FleetSocketProvider>
      </main>
    </div>
  );
}
