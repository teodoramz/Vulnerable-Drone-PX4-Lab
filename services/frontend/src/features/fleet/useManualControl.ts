import { useCallback, useEffect, useRef, useState } from "react";

import type { Role, TelemetryDrone } from "../../api/types";

export interface ManualVelocity {
  vx: number;
  vy: number;
  vz: number;
  yaw: number;
}

export interface ManualControl {
  manualDrones: Set<number>;
  /** Mutated directly by the joystick/buttons; read by the 10 Hz stream. */
  velRef: React.MutableRefObject<ManualVelocity>;
  isManualFor: (ids: number[]) => boolean;
  disableManual: (ids: number[]) => void;
  toggleManual: (ids: number[]) => void;
}

interface Params {
  drones: Record<number, TelemetryDrone>;
  role: Role;
  myId: number;
  send: (msg: object) => void;
}

/** Manual (joystick) flight: which drones are manual, and the 10 Hz velocity stream that flies them. Refs mirror state so the interval never re-subscribes. */
export function useManualControl({ drones, role, myId, send }: Params): ManualControl {
  const [manualDrones, setManualDrones] = useState<Set<number>>(new Set());

  const velRef = useRef<ManualVelocity>({ vx: 0, vy: 0, vz: 0, yaw: 0 });
  const manualRef = useRef(manualDrones);
  const dronesRef = useRef(drones);
  useEffect(() => void (manualRef.current = manualDrones), [manualDrones]);
  useEffect(() => void (dronesRef.current = drones), [drones]);

  // 10 Hz manual velocity stream
  useEffect(() => {
    const interval = setInterval(() => {
      const set = manualRef.current;
      if (set.size === 0) return;
      const { vx, vy, vz, yaw } = velRef.current;
      for (const id of set) {
        const c = dronesRef.current[id]?.claim;
        const allowed = role === "admin" || (!!c?.held && c.user_id === myId);
        if (allowed) {
          send({ drone_id: id, command: "MANUAL", stream: true, vx, vy, vz, yaw });
        }
      }
    }, 100);
    return () => clearInterval(interval);
  }, [send, role, myId]);

  const disableManual = useCallback(
    (ids: number[]) => {
      if (ids.some((id) => manualDrones.has(id))) {
        setManualDrones((prev) => {
          const next = new Set(prev);
          ids.forEach((id) => next.delete(id));
          return next;
        });
        ids.forEach((id) => send({ drone_id: id, command: "HOVER" }));
      }
    },
    [manualDrones, send],
  );

  const toggleManual = useCallback(
    (ids: number[]) => {
      const on = ids.some((id) => manualDrones.has(id));
      if (on) {
        disableManual(ids);
      } else {
        setManualDrones((prev) => {
          const next = new Set(prev);
          ids.forEach((id) => next.add(id));
          return next;
        });
        ids.forEach((id) => send({ drone_id: id, command: "MANUAL" }));
      }
    },
    [manualDrones, disableManual, send],
  );

  const isManualFor = useCallback((ids: number[]) => ids.some((id) => manualDrones.has(id)), [manualDrones]);

  return { manualDrones, velRef, isManualFor, disableManual, toggleManual };
}
