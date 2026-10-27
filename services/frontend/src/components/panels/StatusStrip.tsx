import type { DroneState, TelemetryDrone } from "../../api/types";
import { DRONE_COLORS } from "../map/MapView";
import Badge from "../ui/Badge";

const ERROR_STATES = new Set(["ERROR", "FAILSAFE", "SIGNAL_LOST"]);

/** Link and per-drone state; used by the Operations toolbar and Network's link-health strip. */
export default function StatusStrip({
  connected,
  registry,
  drones,
}: {
  connected: boolean;
  registry: DroneState[];
  drones: Record<number, TelemetryDrone>;
}) {
  return (
    <div className="flex items-center gap-2 flex-wrap">
      <Badge tone={connected ? "success" : "danger"} pulse={!connected}>
        {connected ? "LINK ONLINE" : "DISCONNECTED"}
      </Badge>

      {registry.map((d) => {
        const live = drones[d.id];
        // A lost aircraft is powered down (`enabled` false), so the live loss flag wins over OFFLINE.
        const lost = live?.lost ?? d.lost ?? false;
        const state = lost ? "NO SIGNAL" : live?.enabled ? live.state : "OFFLINE";
        const isError = ERROR_STATES.has(state);
        const color = DRONE_COLORS[d.id % DRONE_COLORS.length];
        return (
          <span
            key={d.id}
            className={`inline-flex items-center gap-1.5 text-label px-2 py-0.5 rounded-full border ${
              isError ? "border-red-700 bg-red-600/20 text-red-300" : "border-slate-700 bg-slate-800 text-slate-300"
            }`}
            title={`${d.callsign} - ${state}`}
          >
            <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: color }} />
            <span className="font-semibold">{d.callsign.toUpperCase()}</span>
            <span className={isError ? "font-bold" : "text-slate-500"}>{state}</span>
          </span>
        );
      })}
      {registry.length === 0 && <span className="text-label text-slate-600">No drones registered.</span>}
    </div>
  );
}
