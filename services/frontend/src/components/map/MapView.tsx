import L from "leaflet";
import { Fragment, useCallback, useEffect, useMemo, useRef } from "react";
import {
  Circle,
  CircleMarker,
  MapContainer,
  Marker,
  Polygon,
  Polyline,
  Tooltip,
  useMap,
  useMapEvents,
} from "react-leaflet";

import type { DroneState, TelemetryDrone } from "../../api/types";
import { type LatLon } from "./geo";
import SiteMap from "./SiteMap";
import { imageBounds, type SiteDef, type SiteObject } from "./site";

/** Half the airframe width of a small quadrotor, in metres. */
export const DRONE_RADIUS_M = 0.8;

export const DRONE_COLORS = ["#ef4444", "#3b82f6", "#10b981", "#f59e0b", "#a855f7", "#ec4899"];

/** How much ground the camera shows around the drone when it is locked on. */
export const FOLLOW_RADIUS_M = 400;

export type { LatLon };

/** Reports the current zoom and metres-per-pixel upward. */
function ZoomWatcher({
  onZoom,
  onViewChange,
}: {
  onZoom: (z: number, mPerPx: number) => void;
  onViewChange?: (b: L.LatLngBounds, mPerPx: number) => void;
}) {
  const map = useMap();
  useEffect(() => {
    const report = () => {
      const c = map.getCenter();
      const mPerPx =
        (40075016.686 * Math.cos((c.lat * Math.PI) / 180)) / Math.pow(2, map.getZoom() + 8);
      onZoom(map.getZoom(), mPerPx);
      onViewChange?.(map.getBounds(), mPerPx);
    };
    report();
    map.on("zoomend moveend resize", report);
    return () => {
      map.off("zoomend moveend resize", report);
    };
  }, [map, onZoom, onViewChange]);
  return null;
}

function ClickHandler({ onClick }: { onClick: (lat: number, lon: number) => void }) {
  useMapEvents({
    click(e) {
      onClick(e.latlng.lat, e.latlng.lng);
    },
  });
  return null;
}

/** Follows the drone while the camera is locked; dragging or scrolling releases the lock. */
function FollowDrone({
  target,
  locked,
  onRelease,
}: {
  target: LatLon | null;
  locked: boolean;
  onRelease: () => void;
}) {
  const map = useMap();
  // Set while this component moves the map, so its own pans are not read as the operator taking over.
  const selfMove = useRef(false);

  useEffect(() => {
    if (!locked) return;
    const release = () => {
      if (!selfMove.current) onRelease();
    };
    map.on("dragstart", release);
    map.on("wheel", release);
    return () => {
      map.off("dragstart", release);
      map.off("wheel", release);
    };
  }, [map, locked, onRelease]);

  useEffect(() => {
    if (!locked || !target) return;
    selfMove.current = true;
    map.panTo([target.lat, target.lon], { animate: true, duration: 0.4 });
    const t = window.setTimeout(() => {
      selfMove.current = false;
    }, 500);
    return () => window.clearTimeout(t);
  }, [map, locked, target?.lat, target?.lon]);

  return null;
}

/** Clamp zoom-out and panning to the site map. The zoom floor comes from `getBoundsZoom` so setting a limit never moves the view. */
function applyLimits(map: L.Map, bounds: [number, number][]): number {
  const box = L.latLngBounds(bounds);
  const floor = map.getBoundsZoom(box, false, L.point(24, 24));
  map.setMinZoom(floor);
  map.setMaxBounds(box.pad(0.05));
  return floor;
}

/** Frames the whole site (zoom floor and pan limits), then zooms to a radius around the drone if the camera is locked and its position is known. */
function OpeningView({
  bounds,
  focus,
  radiusM,
}: {
  bounds: [number, number][];
  focus: LatLon | null;
  radiusM: number;
}) {
  const map = useMap();
  const done = useRef(false);

  useEffect(() => {
    if (done.current) return;

    const apply = () => {
      // Leaflet caches the container size; re-measure before fitting, since the pane may not be laid out yet.
      map.invalidateSize({ animate: false });
      applyLimits(map, bounds);
      if (focus) {
        map.fitBounds(L.latLng(focus.lat, focus.lon).toBounds(radiusM * 2), {
          animate: false,
        });
        // Latch only once there is a real focus point, not the placeholder bounds.
        done.current = true;
      } else {
        map.fitBounds(bounds as L.LatLngBoundsExpression, {
          padding: [24, 24],
          animate: false,
        });
      }
    };

    apply();
    // Re-run after layout settles; keeps re-framing until a focus point exists.
    const t = window.setTimeout(apply, 250);
    return () => window.clearTimeout(t);
  }, [bounds, map, focus?.lat, focus?.lon, radiusM]);

  return null;
}

/** Re-measure the pane on resize and refresh the zoom floor and pan limits. Never re-frames, which would undo manual zooms. */
function RefitOnResize({ bounds }: { bounds: [number, number][] }) {
  const map = useMap();
  useEffect(() => {
    const el = map.getContainer();
    let frame = 0;

    const observer = new ResizeObserver(() => {
      window.cancelAnimationFrame(frame);
      frame = window.requestAnimationFrame(() => {
        map.invalidateSize({ animate: false });
        // The floor depends on pane size; Leaflet clamps the current zoom to it.
        applyLimits(map, bounds);
      });
    });
    observer.observe(el);
    return () => {
      window.cancelAnimationFrame(frame);
      observer.disconnect();
    };
  }, [map, bounds]);
  return null;
}

function droneIcon(color: string) {
  return L.divIcon({
    className: "",
    html: `<div style="width:16px;height:16px;border-radius:50%;border:3px solid #fff;background:${color};box-shadow:0 0 12px 4px ${color}99"></div>`,
    iconSize: [16, 16],
    iconAnchor: [8, 8],
  });
}

/** Where contact was lost: a record of a position, not an aircraft. */
const LOST_ICON = L.divIcon({
  className: "",
  html:
    `<div style="width:22px;height:22px;border-radius:50%;border:2px dashed #f87171;` +
    `display:flex;align-items:center;justify-content:center;color:#f87171;` +
    `font:700 13px/1 ui-sans-serif,system-ui">?</div>`,
  iconSize: [22, 22],
  iconAnchor: [11, 11],
});

const TARGET_ICON = L.divIcon({ className: "target-marker", iconSize: [12, 12] });

export default function MapView({
  registry,
  drones,
  targets,
  perimeter,
  site,
  objects,
  selectedObjectId,
  cameraLock,
  onReleaseCamera,
  onZoom,
  onViewChange,
  onMapClick,
  onPerimeterClick,
  onTargetClick,
  onObjectClick,
}: {
  registry: DroneState[];
  drones: Record<number, TelemetryDrone>;
  targets: Record<number, { lat: number; lon: number }>;
  perimeter?: LatLon[];
  /** Site definition from the C2: map image, pads and the enforced operational boundary. */
  site?: SiteDef | null;
  /** The objects to outline - whatever is in view, fetched by the page. */
  objects?: SiteObject[];
  selectedObjectId?: string | null;
  /** Follow the drone. Released by dragging or scrolling the map. */
  cameraLock?: boolean;
  onReleaseCamera?: () => void;
  onZoom?: (zoom: number, metresPerPixel: number) => void;
  onViewChange?: (bounds: L.LatLngBounds, metresPerPixel: number) => void;
  onMapClick: (lat: number, lon: number) => void;
  onPerimeterClick?: (index: number) => void;
  onTargetClick?: (droneId: number) => void;
  onObjectClick?: (o: SiteObject) => void;
}) {
  const home = registry[0];
  const center: [number, number] = site
    ? [site.home_lat, site.home_lon]
    : home
      ? [home.home_lat, home.home_lon]
      : [44.0, 25.0];

  // Memoised: feeds effect dependency lists.
  const siteBounds = useMemo<[number, number][]>(() => {
    if (!site) {
      const d = 0.02;
      return [
        [center[0] - d, center[1] - d],
        [center[0] + d, center[1] + d],
      ];
    }
    const [[s0, w0], [n0, e0]] = imageBounds(site);
    return [
      [s0, w0],
      [n0, e0],
    ];
  }, [site, center[0], center[1]]);

  // What the camera follows: the live aircraft, or where it was last seen.
  const live = home ? drones[home.id] : undefined;
  const hasFix = !!live && live.enabled && !(live.lat === 0 && live.lon === 0);
  const followTarget: LatLon | null = hasFix
    ? { lat: live!.lat, lon: live!.lon }
    : live?.last_known_lat != null && live?.last_known_lon != null
      ? { lat: live.last_known_lat, lon: live.last_known_lon }
      : site
        ? { lat: site.home_lat, lon: site.home_lon }
        : null;

  const release = useCallback(() => onReleaseCamera?.(), [onReleaseCamera]);

  return (
    <MapContainer
      center={center}
      // OpeningView does the real framing; this avoids a visible jump.
      zoom={14}
      // Fractional zoom: fitBounds otherwise snaps down to a whole level.
      zoomSnap={0}
      zoomDelta={0.5}
      // The map image is 4000 px for 5 km, so it goes soft before this; zoom is for seeing the aircraft at a believable size.
      maxZoom={22}
      // Real floor is set by applyLimits; this only must not block it.
      minZoom={1}
      scrollWheelZoom
      // Slower wheel zoom than Leaflet's default of one level per 60 px.
      wheelPxPerZoomLevel={240}
      zoomControl
      style={{ height: "100%", width: "100%" }}
    >
      {site && (
        <SiteMap
          site={site}
          objects={objects ?? []}
          selectedObjectId={selectedObjectId ?? null}
          onObjectClick={onObjectClick}
        />
      )}
      {onZoom && <ZoomWatcher onZoom={onZoom} onViewChange={onViewChange} />}
      <ClickHandler onClick={onMapClick} />
      <OpeningView bounds={siteBounds} focus={cameraLock ? followTarget : null} radiusM={FOLLOW_RADIUS_M} />
      <RefitOnResize bounds={siteBounds} />
      <FollowDrone target={followTarget} locked={!!cameraLock} onRelease={release} />

      {/* Mission the aircraft is flying, from the C2; drawn for every user. Solid and brighter than the operator's own drawing. */}
      {registry.map((d) => {
        const t = drones[d.id];
        if (!t || !t.enabled || t.lost) return null;
        const colour = DRONE_COLORS[d.id % DRONE_COLORS.length];
        const flown = t.patrol?.points ?? [];
        const leg = t.patrol ? t.patrol.index % Math.max(flown.length, 1) : -1;
        return (
          <Fragment key={`mission-${d.id}`}>
            {flown.length > 1 && (
              <>
                <Polygon
                  positions={flown}
                  pathOptions={{
                    color: colour,
                    weight: 2.5,
                    opacity: 0.95,
                    fillColor: colour,
                    fillOpacity: 0.05,
                  }}
                >
                  <Tooltip sticky>
                    {d.callsign} - patrolling {flown.length} waypoints
                    <br />
                    <span className="opacity-70">
                      flying to waypoint {leg + 1} of {flown.length}
                    </span>
                  </Tooltip>
                </Polygon>
                {flown.map((p, i) => (
                  <CircleMarker
                    key={i}
                    center={p}
                    radius={i === leg ? 7 : 4}
                    pathOptions={{
                      color: i === leg ? "#ffffff" : colour,
                      weight: i === leg ? 2 : 1,
                      fillColor: colour,
                      fillOpacity: 1,
                    }}
                  >
                    <Tooltip>
                      Waypoint {i + 1}
                      {i === leg ? " - next" : ""}
                    </Tooltip>
                  </CircleMarker>
                ))}
              </>
            )}
            {/* Current target and the line to it. */}
            {t.target && (
              <>
                <Polyline
                  positions={[
                    [t.lat, t.lon],
                    [t.target.lat, t.target.lon],
                  ]}
                  pathOptions={{ color: colour, weight: 2, opacity: 0.9 }}
                />
                <CircleMarker
                  center={[t.target.lat, t.target.lon]}
                  radius={6}
                  pathOptions={{ color: "#ffffff", weight: 2, fillColor: colour, fillOpacity: 0.9 }}
                >
                  <Tooltip>
                    {d.callsign} is flying here
                    <br />
                    <span className="opacity-70 tabular-nums">
                      {t.target.lat.toFixed(5)}, {t.target.lon.toFixed(5)} at{" "}
                      {t.target.alt.toFixed(0)} m
                    </span>
                  </Tooltip>
                </CircleMarker>
              </>
            )}
          </Fragment>
        );
      })}

      {/* Perimeter being built / active patrol loop. */}
      {perimeter && perimeter.length > 0 && (
        <>
          {/* Operator's own drawing: a plan, not a flight; dashed and dimmer. */}
          <Polygon
            positions={perimeter.map((p) => [p.lat, p.lon]) as [number, number][]}
            pathOptions={{
              color: "#22d3ee",
              weight: 1.5,
              opacity: 0.6,
              dashArray: "4, 6",
              fillColor: "#22d3ee",
              fillOpacity: 0.05,
            }}
          >
            <Tooltip sticky>Planned route ({perimeter.length} points) - not yet flying</Tooltip>
          </Polygon>
          {perimeter.map((p, i) => (
            <CircleMarker
              key={i}
              center={[p.lat, p.lon]}
              radius={6}
              pathOptions={{ color: "#22d3ee", fillColor: "#0891b2", fillOpacity: 1 }}
              eventHandlers={onPerimeterClick ? { click: () => onPerimeterClick(i) } : undefined}
            />
          ))}
        </>
      )}

      {registry.map((d) => {
        const t = drones[d.id];
        if (!t) return null;
        const color = DRONE_COLORS[d.id % DRONE_COLORS.length];
        const target = targets[d.id];
        const flying = t.enabled && !(t.lat === 0 && t.lon === 0);

        // Contact lost: mark where it was last seen.
        if (!flying) {
          if (t.last_known_lat == null || t.last_known_lon == null) return null;
          return (
            <Marker
              key={`lost-${d.id}`}
              position={[t.last_known_lat, t.last_known_lon]}
              icon={LOST_ICON}
              title={`${d.callsign}: last known position`}
            />
          );
        }

        return (
          <Fragment key={d.id}>
            {/* Two marks: the circle is the true-size aircraft (sub-pixel at site view); the marker keeps it findable. */}
            <Circle
              center={[t.lat, t.lon]}
              radius={DRONE_RADIUS_M}
              pathOptions={{ color, weight: 1, fillColor: color, fillOpacity: 0.9 }}
            />
            <Marker position={[t.lat, t.lon]} icon={droneIcon(color)} />
            {target && (
              <>
                <Marker
                  position={[target.lat, target.lon]}
                  icon={TARGET_ICON}
                  eventHandlers={onTargetClick ? { click: () => onTargetClick(d.id) } : undefined}
                />
                <Polyline
                  positions={[
                    [t.lat, t.lon],
                    [target.lat, target.lon],
                  ]}
                  pathOptions={{ color, weight: 2, dashArray: "6, 6", opacity: 0.8 }}
                />
              </>
            )}
          </Fragment>
        );
      })}
    </MapContainer>
  );
}
