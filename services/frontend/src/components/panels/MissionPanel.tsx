import type { PatrolRoute } from "../map/site";
import Button from "../ui/Button";
import Field, { inputClass } from "../ui/Field";

/**
 * Mission controls: altitude, launch, go-to, patrol, land.
 *
 * The go-to destination is shared with the map: clicking fills the boxes, editing a box moves the marker.
 * One altitude box sets launch, transit and patrol height; SET ALT applies it to the aircraft now.
 */
export default function MissionPanel({
  commandable,
  alt,
  onAlt,
  onSetAltitude,
  canSetAltitude,
  onTakeoff,
  canLaunch,
  isNavigating,
  onCancelNav,
  onGoto,
  canGoto,
  targetLat,
  targetLon,
  onTargetLat,
  onTargetLon,
  routes,
  routeKey,
  onSelectRoute,
  isPatrolling,
  onStopPatrol,
  onStartPatrol,
  routePointCount,
  canPatrol,
  onLand,
  canLand,
}: {
  commandable: boolean;
  alt: number;
  onAlt: (v: number) => void;
  onSetAltitude: () => void;
  canSetAltitude: boolean;
  onTakeoff: () => void;
  canLaunch: boolean;
  isNavigating: boolean;
  onCancelNav: () => void;
  onGoto: () => void;
  canGoto: boolean;
  /** Go-to destination, empty when unset; shared with the map. */
  targetLat: string;
  targetLon: string;
  onTargetLat: (v: string) => void;
  onTargetLon: (v: string) => void;
  routes: Record<string, PatrolRoute>;
  routeKey: string;
  onSelectRoute: (key: string) => void;
  isPatrolling: boolean;
  onStopPatrol: () => void;
  onStartPatrol: () => void;
  routePointCount: number;
  canPatrol: boolean;
  onLand: () => void;
  canLand: boolean;
}) {
  const selected = routes[routeKey];

  return (
    <div className="flex-1 flex flex-col justify-center gap-3 min-w-0">
      <Field label="Altitude">
        <input
          type="number"
          min={0}
          max={400}
          value={alt}
          onChange={(e) => onAlt(Number(e.target.value))}
          className={`${inputClass} w-16`}
          aria-label="Working altitude in metres"
        />
        <Button
          variant="primary"
          onClick={onSetAltitude}
          disabled={!canSetAltitude}
          className="flex-1"
          title="Climb or descend to this altitude now, keeping the current mission"
        >
          SET ALT
        </Button>
      </Field>

      <Field label="Flight">
        <Button variant="success" onClick={onTakeoff} disabled={!canLaunch} className="flex-1">
          LAUNCH
        </Button>
        {isNavigating ? (
          <Button variant="caution" onClick={onCancelNav} className="flex-1">
            CANCEL NAV
          </Button>
        ) : (
          <Button variant="primary" onClick={onGoto} disabled={!canGoto} className="flex-1">
            GO TO POINT
          </Button>
        )}
      </Field>

      {/* Typed destination; same value the map click sets. */}
      <Field label="Target">
        <input
          type="text"
          inputMode="decimal"
          value={targetLat}
          onChange={(e) => onTargetLat(e.target.value)}
          placeholder="lat"
          className={`${inputClass} flex-1 min-w-0 tabular-nums`}
          aria-label="Target latitude"
        />
        <input
          type="text"
          inputMode="decimal"
          value={targetLon}
          onChange={(e) => onTargetLon(e.target.value)}
          placeholder="lon"
          className={`${inputClass} flex-1 min-w-0 tabular-nums`}
          aria-label="Target longitude"
        />
      </Field>

      {/* Predefined routes, or whatever the operator has drawn. */}
      <Field label="Patrol">
        <select
          value={routeKey}
          onChange={(e) => onSelectRoute(e.target.value)}
          className={`${inputClass} flex-1 min-w-0`}
          aria-label="Patrol route"
        >
          {Object.entries(routes).map(([key, r]) => (
            <option key={key} value={key}>
              {r.name}
            </option>
          ))}
          {!selected && <option value="">Custom (drawn on the map)</option>}
        </select>
      </Field>

      <div className="flex items-center gap-2">
        <span className="w-16 shrink-0 text-micro text-slate-500 truncate" title={selected?.description}>
          {routePointCount} pts
        </span>
        {isPatrolling ? (
          <Button variant="caution" onClick={onStopPatrol} className="flex-1">
            STOP PATROL
          </Button>
        ) : (
          <Button variant="patrol" onClick={onStartPatrol} disabled={!canPatrol} className="flex-1">
            START PATROL
          </Button>
        )}
      </div>

      <Button variant="danger" onClick={onLand} disabled={!canLand} className="w-full">
        FORCE LAND
      </Button>

      {!commandable && (
        <p className="text-micro text-slate-500">Power the drone on to command it.</p>
      )}
    </div>
  );
}
