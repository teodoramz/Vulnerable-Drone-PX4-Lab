import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";

import type { Role } from "../api/types";
import { useAuth } from "./AuthContext";

export default function RequireAuth({ children, roles }: { children: ReactNode; roles?: Role[] }) {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" replace />;
  if (roles && !roles.includes(user.role)) return <Navigate to="/" replace />;
  return <>{children}</>;
}
