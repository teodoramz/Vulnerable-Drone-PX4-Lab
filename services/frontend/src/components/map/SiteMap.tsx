import { ImageOverlay, Marker, Polygon, Polyline, Tooltip } from "react-leaflet";

import { label } from "./geo";
import {
  boundaryLatLon,
  imageBounds,
  isPath,
  objectColor,
  objectLabel,
  outline,
  type SiteDef,
  type SiteObject,
} from "./site";

/**
 * The site: map image, operational boundary, launch pads, and the objects fetched for the current view.
 * Outlines are the footprints the C2 tests against, drawn from what the C2 served.
 */
export default function SiteMap({
  site,
  objects,
  selectedObjectId,
  onObjectClick,
}: {
  site: SiteDef;
  objects: SiteObject[];
  selectedObjectId: string | null;
  onObjectClick?: (o: SiteObject) => void;
}) {
  return (
    <>
      <ImageOverlay url={site.image} bounds={imageBounds(site)} opacity={1} />

      {/* Operational area: crossing it loses the aircraft, so it is a hard edge. */}
      <Polygon
        positions={boundaryLatLon(site)}
        pathOptions={{
          color: "#f59e0b",
          weight: 2,
          dashArray: "8, 6",
          fillColor: "#f59e0b",
          fillOpacity: 0.04,
        }}
      >
        <Tooltip sticky>
          Operational area - {site.boundary_area_km2} km². Leaving it loses the aircraft.
        </Tooltip>
      </Polygon>

      {/* Objects in view: paths are lines, everything else is a closed footprint. */}
      {objects.map((o) => {
        const colour = objectColor(o);
        const chosen = o.id === selectedObjectId;
        const pts = outline(o);
        if (!pts.length) return null;

        const options = {
          color: chosen ? "#ffffff" : colour,
          weight: chosen ? 3 : 1.2,
          fillColor: colour,
          fillOpacity: chosen ? 0.45 : 0.2,
        };
        const handlers = onObjectClick ? { click: () => onObjectClick(o) } : undefined;
        const tip = (
          <Tooltip sticky>
            <span className="font-semibold">{objectLabel(o)}</span>
            <br />
            {o.length_m.toFixed(0)} × {o.width_m.toFixed(0)} m · {o.height_m.toFixed(1)} m high
            <br />
            <span className="opacity-70 tabular-nums">
              {o.lat.toFixed(5)}, {o.lon.toFixed(5)}
              {o.grid_ref ? ` · ${o.grid_ref}` : ""}
            </span>
            <br />
            <span className="opacity-70">click for full details</span>
          </Tooltip>
        );

        return isPath(o) ? (
          <Polyline
            key={o.id}
            positions={pts}
            pathOptions={{
              ...options,
              weight: Math.max(2, chosen ? 5 : 3),
              fillOpacity: 0,
            }}
            eventHandlers={handlers}
          >
            {tip}
          </Polyline>
        ) : (
          <Polygon key={o.id} positions={pts} pathOptions={options} eventHandlers={handlers}>
            {tip}
          </Polygon>
        );
      })}

      {/* Launch pads: the only places a drone may come up. */}
      {site.launch_pads.map((p) => (
        <Marker
          key={p.id}
          position={[p.lat, p.lon]}
          icon={label(p.designator ?? "PAD", "#3fbfae", 11)}
          interactive={false}
        />
      ))}
    </>
  );
}
