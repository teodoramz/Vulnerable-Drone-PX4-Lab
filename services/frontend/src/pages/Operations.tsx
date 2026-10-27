import { useCallback, useEffect, useMemo, useState } from "react";

import { useAuth } from "../auth/AuthContext";
import DroneSidebar from "../components/DroneSidebar";
import MapView from "../components/map/MapView";
import ManualPanel from "../components/panels/ManualPanel";
import MapToolbar from "../components/panels/MapToolbar";
import MissionPanel from "../components/panels/MissionPanel";
import ObjectInspector from "../components/panels/ObjectInspector";
import StatusStrip from "../components/panels/StatusStrip";
import TelemetryReadout from "../components/panels/TelemetryReadout";
import Terminal from "../components/Terminal";
import { useSite } from "../features/site/useSite";
import { useSiteObjects } from "../features/site/useSiteObjects";
import { useDroneRegistry } from "../features/fleet/useDroneRegistry";
import { useFleetCommands } from "../features/fleet/useFleetCommands";
import { useManualControl } from "../features/fleet/useManualControl";
import { useMissionPlanner } from "../features/fleet/useMissionPlanner";
import { useFleetSocketContext } from "../ws/FleetSocketProvider";

/** Operator console: composes the fleet hooks and panels. Command dispatch lives in features/fleet. */
export default function Operations() {
  const { user } = useAuth();
  const { drones, logs, connected, lastError, send } = useFleetSocketContext();

  const myId = user?.id ?? -1;
  const role = user?.role ?? "observer";

  const [toast, setToast] = useState<string | null>(null);
  useEffect(() => {
    if (!lastError) return;
    setToast(lastError.msg);
    const t = setTimeout(() => setToast(null), 4000);
    return () => clearTimeout(t);
  }, [lastError]);

  const { registry, claim, release, forceRelease, power, reset, resetting } = useDroneRegistry(setToast);
  const { site } = useSite();
  // Structures appear with zoom rather than behind a toggle.
  const [scale, setScale] = useState<{ zoom: number; mPerPx: number }>({ zoom: 13, mPerPx: 9 });
  const objects = useSiteObjects(scale.mPerPx);
  const showObstacles = objects.visible;
  // Camera starts locked on the drone; dragging or scrolling the map releases it.
  const [cameraLock, setCameraLock] = useState(true);
  const manual = useManualControl({ drones, role, myId, send });
  const fleet = useFleetCommands({ drones, role, myId, send, disableManual: manual.disableManual, onError: setToast });
  const mission = useMissionPlanner({ registry, controlTargets: fleet.controlTargets, selected: fleet.selected, site });

  const isSwarm = fleet.selected === "SWARM";

  const hasTarget = useMemo(
    () =>
      isSwarm
        ? fleet.controlTargets.some((id) => mission.targets[id])
        : !!(typeof fleet.selected === "number" && mission.targets[fleet.selected]),
    [isSwarm, fleet.controlTargets, fleet.selected, mission.targets],
  );

  const manualOn = manual.isManualFor(fleet.controlTargets);
  const readyOrFlying = isSwarm || fleet.isFlying;

  const handleLand = () => {
    fleet.doLand();
    mission.clearTargets(fleet.controlTargets);
  };

  // A click both plans (target, route point) and inspects, so there is no mode to pick.
  const handleMapClick = useCallback(
    (lat: number, lon: number) => {
      mission.onMapClick(lat, lon);
      void objects.inspect(lat, lon, fleet.alt);
    },
    [mission, objects, fleet.alt],
  );

  return (
    <div className="h-full flex">
      <DroneSidebar
        registry={registry}
        drones={drones}
        selected={fleet.selected}
        onSelect={fleet.setSelected}
        role={role}
        myUserId={myId}
        swarmSel={fleet.swarmSel}
        onToggleSwarm={fleet.toggleSwarm}
        onClaim={claim}
        onRelease={release}
        onForceRelease={forceRelease}
        onPower={power}
        onReset={reset}
        resetting={resetting}
        pads={site?.launch_pads ?? []}
      />

      <div className="flex-1 flex flex-col p-3 gap-3 min-w-0">
        <div className="flex items-center gap-3 flex-wrap">
          <StatusStrip connected={connected} registry={registry} drones={drones} />
          <div className="w-px self-stretch bg-slate-800" />
          <TelemetryReadout drone={drones[0]} />
          <div className="w-px self-stretch bg-slate-800" />
          <MapToolbar
            clickMode={mission.clickMode}
            onClickMode={mission.setClickMode}
            perimeterCount={mission.perimeter.length}
            onUndo={mission.undoPerimeterPoint}
            onClear={mission.clearMarks}
          />
          {/* Fixed width and no wrapping: a growing readout reflowed the strip and cancelled zoom. */}
          <span className="text-micro text-slate-500 tabular-nums shrink-0 w-40 whitespace-nowrap">
            {scale.mPerPx < 1
              ? `${(scale.mPerPx * 100).toFixed(0)} cm/px`
              : `${scale.mPerPx.toFixed(1)} m/px`}
            {showObstacles && (
              <span className="ml-2 text-amber-400/80">{objects.objects.length} objects</span>
            )}
          </span>
          <button
            onClick={() => setCameraLock((v) => !v)}
            className={`shrink-0 text-micro px-2 py-1 rounded border transition-colors ${
              cameraLock
                ? "border-blue-500 text-blue-300 bg-blue-500/10"
                : "border-slate-700 text-slate-400 hover:text-slate-200"
            }`}
            title={
              cameraLock
                ? "Following the drone - drag the map to look around"
                : "Free view - click to follow the drone again"
            }
          >
            {cameraLock ? "LOCK CAMERA" : "FREE VIEW"}
          </button>
          {toast && (
            <span className="ml-auto px-3 py-1 rounded bg-red-600/30 text-red-200 border border-red-700 text-xs">
              {toast}
            </span>
          )}
        </div>

        <div className="flex-1 rounded-xl border border-slate-800 overflow-hidden min-h-0">
          <MapView
            registry={registry}
            drones={drones}
            targets={mission.targets}
            perimeter={mission.perimeter}
            site={site}
            objects={objects.objects}
            selectedObjectId={objects.selected?.id ?? null}
            cameraLock={cameraLock}
            onReleaseCamera={() => setCameraLock(false)}
            onZoom={(zoom, mPerPx) => setScale({ zoom, mPerPx })}
            onViewChange={(b) =>
              objects.fetchForBounds(
                b.getSouth(), b.getWest(), b.getNorth(), b.getEast(),
              )
            }
            onMapClick={handleMapClick}
            onPerimeterClick={mission.removePerimeterPoint}
            onTargetClick={mission.removeTarget}
            onObjectClick={(o) => {
              objects.setSelected(o);
              void objects.inspect(o.lat, o.lon, fleet.alt);
            }}
          />
        </div>

        {/* Fixed height, not min-height, so the terminal log cannot squeeze the map. The control panel scrolls horizontally because wrapping its fixed-width columns hid GO TO POINT and FORCE LAND. */}
        {/* 288px is the control panel's content height; less clips FORCE LAND on a 768px screen. */}
        <div className="flex gap-3 shrink-0 h-[clamp(288px,32vh,340px)]">
          <div className="flex-1 min-w-0 overflow-x-auto bg-slate-900 rounded-xl border border-slate-800">
            <div className="h-full min-w-[34rem] max-w-[46rem] p-4 flex gap-4">
            <MissionPanel
              commandable={fleet.commandable}
              alt={fleet.alt}
              onAlt={fleet.setAlt}
              onSetAltitude={fleet.doSetAltitude}
              canSetAltitude={fleet.commandable && readyOrFlying}
              onTakeoff={fleet.doTakeoff}
              canLaunch={isSwarm ? fleet.swarmReady : fleet.commandable && fleet.isIdle}
              isNavigating={fleet.isNavigating}
              onCancelNav={fleet.doCancel}
              onGoto={() => fleet.doGoto(mission.targets)}
              canGoto={fleet.commandable && hasTarget && readyOrFlying}
              targetLat={mission.targetLat}
              targetLon={mission.targetLon}
              onTargetLat={mission.setTargetLat}
              onTargetLon={mission.setTargetLon}
              routes={site?.routes ?? {}}
              routeKey={mission.routeKey}
              onSelectRoute={mission.selectRoute}
              isPatrolling={fleet.isPatrolling}
              onStopPatrol={fleet.stopPatrol}
              onStartPatrol={() => fleet.startPatrol(mission.perimeter)}
              routePointCount={mission.perimeter.length}
              canPatrol={fleet.commandable && mission.perimeter.length >= 2 && readyOrFlying}
              onLand={handleLand}
              canLand={isSwarm ? fleet.swarmReady : fleet.commandable && fleet.isFlying}
            />
            <ManualPanel
              manualOn={manualOn}
              onToggle={() => manual.toggleManual(fleet.controlTargets)}
              canToggle={isSwarm ? fleet.swarmReady : fleet.commandable && fleet.isFlying}
              velRef={manual.velRef}
            />
            </div>
          </div>

          <div className="w-72 shrink-0 min-h-0 bg-slate-900 rounded-xl border border-slate-800 overflow-hidden">
            <ObjectInspector
              lookup={objects.lookup}
              selected={objects.selected}
              onSelect={objects.setSelected}
              onClose={objects.clear}
              onGoHere={(lat, lon) => {
                mission.setTargetLat(lat.toFixed(6));
                mission.setTargetLon(lon.toFixed(6));
              }}
            />
          </div>

          <div className="w-72 shrink-0 min-h-0">
            <Terminal logs={logs} />
          </div>
        </div>
      </div>
    </div>
  );
}
