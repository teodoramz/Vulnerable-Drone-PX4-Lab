import type { MutableRefObject } from "react";

import type { ManualVelocity } from "../../features/fleet/useManualControl";
import Joystick from "../Joystick";
import Button from "../ui/Button";

export default function ManualPanel({
  manualOn,
  onToggle,
  canToggle,
  velRef,
}: {
  manualOn: boolean;
  onToggle: () => void;
  canToggle: boolean;
  velRef: MutableRefObject<ManualVelocity>;
}) {
  return (
    <div className="w-56 shrink-0 flex flex-col items-center border-l border-slate-800 pl-4 justify-center">
      <Button
        variant={manualOn ? "danger" : "swarm"}
        size="sm"
        onClick={onToggle}
        disabled={!canToggle}
        className="mb-3"
      >
        {manualOn ? "DISABLE MANUAL" : "ENABLE MANUAL"}
      </Button>

      <Joystick
        disabled={!manualOn}
        onChange={(n, e) => {
          velRef.current.vx = n;
          velRef.current.vy = e;
        }}
      />

      <div className="flex flex-wrap justify-center gap-2 mt-2">
        <Button
          size="sm"
          onPointerDown={() => (velRef.current.vz = -5)}
          onPointerUp={() => (velRef.current.vz = 0)}
          onPointerLeave={() => (velRef.current.vz = 0)}
          disabled={!manualOn}
        >
          ▲ UP
        </Button>
        <Button
          size="sm"
          onPointerDown={() => (velRef.current.vz = 5)}
          onPointerUp={() => (velRef.current.vz = 0)}
          onPointerLeave={() => (velRef.current.vz = 0)}
          disabled={!manualOn}
        >
          ▼ DN
        </Button>
        <Button
          size="sm"
          onPointerDown={() => (velRef.current.yaw = -90)}
          onPointerUp={() => (velRef.current.yaw = 0)}
          disabled={!manualOn}
        >
          ↺
        </Button>
        <Button
          size="sm"
          onPointerDown={() => (velRef.current.yaw = 90)}
          onPointerUp={() => (velRef.current.yaw = 0)}
          disabled={!manualOn}
        >
          ↻
        </Button>
      </div>
    </div>
  );
}
