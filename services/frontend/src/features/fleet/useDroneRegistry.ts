import { useCallback, useEffect, useState } from "react";

import api from "../../api/client";
import type { DroneState } from "../../api/types";

export interface DroneRegistry {
  registry: DroneState[];
  claim: (id: number) => Promise<void>;
  release: (id: number) => Promise<void>;
  forceRelease: (id: number) => Promise<void>;
  power: (id: number, on: boolean, pad?: string) => Promise<void>;
  /** Maintenance reset: restore the drone to a known-good state and power it back up. Resolves when the C2 finishes. */
  reset: (id: number, pad?: string) => Promise<void>;
  resetting: number | null;
}

/** The drone roster (REST) plus the claim/power actions. Flight commands live in useFleetCommands; this hook only calls /api/drones. */
export function useDroneRegistry(onError: (msg: string) => void): DroneRegistry {
  const [registry, setRegistry] = useState<DroneState[]>([]);

  useEffect(() => {
    api
      .get<DroneState[]>("/api/drones")
      .then((r) => setRegistry(r.data))
      .catch(() => {});
  }, []);

  const rest = useCallback(
    async (url: string, body?: object) => {
      try {
        await api.post(url, body);
      } catch (e: any) {
        onError(e?.response?.data?.detail ?? "Request failed");
      }
    },
    [onError],
  );

  const claim = useCallback((id: number) => rest(`/api/drones/${id}/claim`), [rest]);
  const release = useCallback((id: number) => rest(`/api/drones/${id}/release`), [rest]);
  const forceRelease = useCallback((id: number) => rest(`/api/drones/${id}/force-release`), [rest]);
  // `pad` is a launch-pad designator from the site dataset (HP-1 / HP-2).
  const power = useCallback(
    (id: number, on: boolean, pad?: string) =>
      rest(`/api/drones/${id}/power`, { on, ...(pad ? { pad } : {}) }),
    [rest],
  );

  const [resetting, setResetting] = useState<number | null>(null);
  const reset = useCallback(
    async (id: number, pad?: string) => {
      // Reset runs multi-step server-side and can take seconds; track which drone is mid-reset to disable the button.
      setResetting(id);
      try {
        await rest(`/api/drones/${id}/reset`, pad ? { pad } : {});
      } finally {
        setResetting(null);
      }
    },
    [rest],
  );

  return { registry, claim, release, forceRelease, power, reset, resetting };
}
