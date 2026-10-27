import { useCallback, useMemo, useState } from "react";

import type { LatLon } from "../../components/map/MapView";
import type { Role, TelemetryDrone } from "../../api/types";

const FLIGHT_STATES = new Set(["TAKEOFF", "HOVER", "GOTO", "PATROL", "MANUAL", "LAND", "FAILSAFE", "ERROR"]);

export type Selection = number | "SWARM";

interface Params {
  drones: Record<number, TelemetryDrone>;
  role: Role;
  myId: number;
  send: (msg: object) => void;
  disableManual: (ids: number[]) => void;
  onError: (msg: string) => void;
}

export interface FleetCommands {
  selected: Selection;
  setSelected: (sel: Selection) => void;
  swarmSel: Set<number>;
  toggleSwarm: (id: number) => void;
  controlTargets: number[];
  canCmd: (id: number) => boolean;

  state: string;
  isIdle: boolean;
  isFlying: boolean;
  isNavigating: boolean;
  isPatrolling: boolean;
  commandable: boolean;
  swarmReady: boolean;

  /** One working altitude, used for launch, transit and patrol. */
  alt: number;
  setAlt: (alt: number) => void;

  doTakeoff: () => void;
  /** Climb or descend to `alt` where the drone is, without losing the mission. */
  doSetAltitude: () => void;
  doGoto: (targets: Record<number, LatLon>) => void;
  doLand: () => void;
  doCancel: () => void;
  startPatrol: (perimeter: LatLon[]) => void;
  stopPatrol: () => void;
}

/** Flight-command dispatch: selection, derived flight-state flags, and every command sent over the WebSocket. */
export function useFleetCommands({ drones, role, myId, send, disableManual, onError }: Params): FleetCommands {
  const [selected, setSelected] = useState<Selection>(0);
  const [swarmSel, setSwarmSel] = useState<Set<number>>(new Set());
  // One altitude for launch, transit and patrol.
  const [alt, setAlt] = useState(25);

  const canCmd = useCallback(
    (id: number): boolean => {
      if (role === "observer") return false;
      if (role === "admin") return true;
      const c = drones[id]?.claim;
      return !!c?.held && c.user_id === myId;
    },
    [drones, role, myId],
  );

  const controlTargets = useMemo<number[]>(() => {
    if (selected === "SWARM") {
      return [...swarmSel].filter((id) => drones[id]?.enabled && canCmd(id));
    }
    return drones[selected]?.enabled && canCmd(selected) ? [selected] : [];
  }, [selected, swarmSel, drones, canCmd]);

  const liveSel = typeof selected === "number" ? drones[selected] : undefined;
  const state = liveSel?.enabled ? liveSel.state : "OFFLINE";
  const isIdle = state === "IDLE";
  const isFlying = !!liveSel?.enabled && FLIGHT_STATES.has(state);
  const isNavigating = state === "GOTO";
  const isPatrolling =
    selected === "SWARM" ? controlTargets.some((id) => drones[id]?.state === "PATROL") : state === "PATROL";

  const swarmReady = selected === "SWARM" && controlTargets.length > 0;
  const commandable = selected === "SWARM" ? swarmReady : controlTargets.length > 0;

  const toggleSwarm = useCallback(
    (id: number) =>
      setSwarmSel((prev) => {
        const next = new Set(prev);
        next.has(id) ? next.delete(id) : next.add(id);
        return next;
      }),
    [],
  );

  const doTakeoff = useCallback(() => {
    controlTargets.forEach((id) => send({ drone_id: id, command: "TAKEOFF", target_alt: alt }));
  }, [controlTargets, send, alt]);

  const doSetAltitude = useCallback(() => {
    controlTargets.forEach((id) => send({ drone_id: id, command: "ALTITUDE", target_alt: alt }));
  }, [controlTargets, send, alt]);

  const doGoto = useCallback(
    (targets: Record<number, LatLon>) => {
      disableManual(controlTargets);
      controlTargets.forEach((id) => {
        const t = targets[id];
        if (t) send({ drone_id: id, command: "GOTO", target_lat: t.lat, target_lon: t.lon, target_alt: alt });
      });
    },
    [controlTargets, disableManual, send, alt],
  );

  const doLand = useCallback(() => {
    disableManual(controlTargets);
    controlTargets.forEach((id) => send({ drone_id: id, command: "LAND" }));
  }, [controlTargets, disableManual, send]);

  const doCancel = useCallback(() => {
    controlTargets.forEach((id) => send({ drone_id: id, command: "CANCEL" }));
  }, [controlTargets, send]);

  const startPatrol = useCallback(
    (perimeter: LatLon[]) => {
      if (perimeter.length < 2) {
        onError("Add at least 2 perimeter points (Perimeter mode, click the map).");
        return;
      }
      disableManual(controlTargets);
      const points = perimeter.map((p) => ({ lat: p.lat, lon: p.lon }));
      controlTargets.forEach((id) =>
        send({ drone_id: id, command: "PATROL", points, target_alt: alt, swarm_mode: selected === "SWARM" }),
      );
    },
    [controlTargets, disableManual, send, alt, selected, onError],
  );

  const stopPatrol = useCallback(() => {
    controlTargets.forEach((id) => send({ drone_id: id, command: "CANCEL" }));
  }, [controlTargets, send]);

  return {
    selected,
    setSelected,
    swarmSel,
    toggleSwarm,
    controlTargets,
    canCmd,
    state,
    isIdle,
    isFlying,
    isNavigating,
    isPatrolling,
    commandable,
    swarmReady,
    alt,
    setAlt,
    doTakeoff,
    doSetAltitude,
    doGoto,
    doLand,
    doCancel,
    startPatrol,
    stopPatrol,
  };
}
