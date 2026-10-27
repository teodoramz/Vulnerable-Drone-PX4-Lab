import { createContext, useContext, type ReactNode } from "react";

import { useAuth } from "../auth/AuthContext";
import { useFleetSocket, type FleetSocket } from "./useFleetSocket";

const FleetSocketContext = createContext<FleetSocket | null>(null);

/** Owns the single WebSocket for the authenticated app, so switching tabs does not reconnect. */
export function FleetSocketProvider({ children }: { children: ReactNode }) {
  const { token } = useAuth();
  const socket = useFleetSocket(token);
  return <FleetSocketContext.Provider value={socket}>{children}</FleetSocketContext.Provider>;
}

export function useFleetSocketContext(): FleetSocket {
  const ctx = useContext(FleetSocketContext);
  if (!ctx) throw new Error("useFleetSocketContext must be used within a FleetSocketProvider");
  return ctx;
}
