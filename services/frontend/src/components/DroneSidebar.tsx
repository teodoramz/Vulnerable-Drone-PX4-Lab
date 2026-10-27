import { useState } from "react";

import type { DroneState, Role, TelemetryDrone } from "../api/types";
import type { LaunchPad } from "./map/site";
import { DRONE_COLORS } from "./map/MapView";
import Button from "./ui/Button";
import ClaimBadge from "./ClaimBadge";

interface Props {
  registry: DroneState[];
  drones: Record<number, TelemetryDrone>;
  selected: number | "SWARM";
  onSelect: (sel: number | "SWARM") => void;
  role: Role;
  myUserId: number;
  swarmSel: Set<number>;
  onToggleSwarm: (id: number) => void;
  onClaim: (id: number) => void;
  onRelease: (id: number) => void;
  onForceRelease: (id: number) => void;
  onPower: (id: number, on: boolean, pad?: string) => void;
  onReset: (id: number, pad?: string) => void;
  resetting: number | null;
  /** The pads a drone may launch from, from the site dataset. */
  pads?: LaunchPad[];
}

const ERROR_STATES = new Set(["ERROR", "FAILSAFE", "SIGNAL_LOST"]);

/** The state as shown to an operator: SIGNAL_LOST displays as "NO SIGNAL". */
function stateLabel(state: string): string {
  return state === "SIGNAL_LOST" ? "NO SIGNAL" : state;
}

export default function DroneSidebar({
  registry,
  drones,
  selected,
  onSelect,
  role,
  myUserId,
  swarmSel,
  onToggleSwarm,
  onClaim,
  onRelease,
  onForceRelease,
  onPower,
  onReset,
  resetting,
  pads = [],
}: Props) {
  // Pad used by the next launch or reset; a drone can only come up on a pad.
  const [pad, setPad] = useState<string>("");
  const padChoices = pads.filter((p) => p.designator);
  const canOperate = role !== "observer";
  const isAdmin = role === "admin";
  // Swarm support is retained (DRONE_COUNT) but hidden in the one-drone console.
  const showSwarm = registry.length > 1;

  return (
    <div className="w-64 shrink-0 bg-slate-900 border-r border-slate-800 flex flex-col">
      <div className="px-3 py-2.5 border-b border-slate-800 text-label uppercase text-slate-500">Fleet Roster</div>
      <div className="flex-1 overflow-y-auto">
        {registry.map((d) => {
          const live = drones[d.id];
          const claim = live?.claim;
          const mine = !!claim?.held && claim.user_id === myUserId;
          const lockedByOther = !!claim?.held && claim.user_id !== myUserId;
          // Prefer live telemetry for the loss flags; the REST registry is stale when contact is lost.
          const lost = live?.lost ?? d.lost ?? false;
          // Loss powers the drone down, so `enabled` is false; show the loss state rather than OFFLINE.
          const state = lost ? "SIGNAL_LOST" : live?.enabled ? live.state : "OFFLINE";
          const lastLat = live?.last_known_lat ?? d.last_known_lat;
          const lastLon = live?.last_known_lon ?? d.last_known_lon;
          const lastAlt = live?.last_known_alt ?? d.last_known_alt;
          const color = DRONE_COLORS[d.id % DRONE_COLORS.length];
          const active = selected === d.id;
          const isError = ERROR_STATES.has(state);

          return (
            <div
              key={d.id}
              onClick={() => onSelect(d.id)}
              className={`p-3 border-b border-slate-800 cursor-pointer transition-colors ${
                active ? "bg-slate-800 border-l-4 border-l-blue-500" : "border-l-4 border-l-transparent hover:bg-slate-850"
              }`}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 min-w-0">
                  <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: color }} />
                  <span className="font-bold text-slate-200 text-sm truncate">{d.callsign.toUpperCase()}</span>
                </div>
                <ClaimBadge claim={live?.claim} mine={mine} />
              </div>

              <div
                className={`text-xs mt-1 font-mono ${isError ? "text-red-500 font-bold animate-pulse" : "text-slate-500"}`}
              >
                {stateLabel(state)}
                {live?.enabled && !lost ? ` · ${live.alt.toFixed(1)}m` : ""}
              </div>

              {canOperate && (
                <div className="flex flex-wrap gap-1 mt-2" onClick={(e) => e.stopPropagation()}>
                  {lost ? (
                    <span className="text-micro text-slate-500 self-center">
                      Not responding - reset to deploy a replacement.
                    </span>
                  ) : !live?.enabled ? (
                    <>
                      {padChoices.length > 1 && (
                        <select
                          value={pad}
                          onChange={(e) => setPad(e.target.value)}
                          aria-label="Launch pad"
                          className="bg-slate-800 border border-slate-700 rounded text-micro text-slate-300 px-1 py-0.5"
                        >
                          <option value="">Pad…</option>
                          {padChoices.map((p) => (
                            <option key={p.id} value={p.designator!}>
                              {p.designator}
                            </option>
                          ))}
                        </select>
                      )}
                      <Button
                        size="sm"
                        variant="primary"
                        disabled={lockedByOther}
                        onClick={() => onPower(d.id, true, pad || undefined)}
                      >
                        Power On
                      </Button>
                    </>
                  ) : (
                    (mine || isAdmin) && (
                      <Button size="sm" variant="danger" onClick={() => onPower(d.id, false)}>
                        Power Off
                      </Button>
                    )
                  )}

                  {!claim?.held && (
                    <Button size="sm" onClick={() => onClaim(d.id)}>
                      Claim
                    </Button>
                  )}
                  {mine && (
                    <Button size="sm" onClick={() => onRelease(d.id)}>
                      Release
                    </Button>
                  )}
                  {lockedByOther && isAdmin && (
                    <Button size="sm" variant="caution" onClick={() => onForceRelease(d.id)}>
                      Force-release
                    </Button>
                  )}
                </div>
              )}

              {/* One message whatever happened: contact stopped, last fix shown. The cause is left to the audit log and inventory. */}
              {lost && (
                <div className="mt-2 rounded border border-red-800 bg-red-500/10 px-2 py-1 text-micro text-red-300">
                  <div className="font-semibold uppercase tracking-wider">Signal lost</div>
                  {lastLat != null && lastLon != null ? (
                    <div className="mt-0.5 tabular-nums">
                      Last fix {lastLat.toFixed(5)}, {lastLon.toFixed(5)}
                      {lastAlt != null && ` at ${lastAlt.toFixed(0)} m`}
                    </div>
                  ) : (
                    <div className="mt-0.5">Position unknown.</div>
                  )}
                  <div className="mt-0.5 text-red-400/80">
                    Position unknown. A maintenance reset puts a replacement on a pad.
                  </div>
                </div>
              )}

              {canOperate && (mine || isAdmin) && (
                <div className="mt-2 pt-2 border-t border-slate-800" onClick={(e) => e.stopPropagation()}>
                  <div className="text-micro uppercase tracking-widest text-slate-600 mb-1">
                    Maintenance
                  </div>
                  <Button
                    size="sm"
                    variant="caution"
                    disabled={resetting !== null}
                    onClick={() => {
                      // Destructive to in-flight state, so confirm.
                      const ok = window.confirm(
                        `Reset ${d.callsign}?\n\n` +
                          "This lands and power-cycles the drone, restores any tampered " +
                          "parameters, discards uploaded waypoints and drops unknown " +
                          "subscribers from its radio link, then brings it back to READY.\n\n" +
                          "The audit log and IDS alerts are NOT cleared.",
                      );
                      if (ok) onReset(d.id, pad || undefined);
                    }}
                    className="w-full"
                    title="Return the drone to a known-good state after an attack or failure"
                  >
                    {resetting === d.id ? "Resetting…" : "Reset Drone"}
                  </Button>
                </div>
              )}

              {showSwarm && selected === "SWARM" && live?.enabled && (
                <label
                  className="flex items-center gap-1 mt-2 text-label text-purple-300"
                  onClick={(e) => e.stopPropagation()}
                >
                  <input type="checkbox" checked={swarmSel.has(d.id)} onChange={() => onToggleSwarm(d.id)} />
                  include in swarm
                </label>
              )}
            </div>
          );
        })}
        {registry.length === 0 && (
          <div className="p-4 text-label text-slate-600">Waiting on the drone registry…</div>
        )}
      </div>

      {canOperate && showSwarm && (
        <div
          onClick={() => onSelect("SWARM")}
          className={`p-4 border-t border-slate-800 cursor-pointer ${
            selected === "SWARM" ? "bg-slate-800 border-l-4 border-l-purple-500" : "hover:bg-slate-850"
          }`}
        >
          <div className="font-bold text-purple-400 tracking-wider text-sm">SWARM OVERRIDE</div>
          <div className="text-label text-slate-500 mt-1">Broadcast to claimed drones</div>
        </div>
      )}
    </div>
  );
}
