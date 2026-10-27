"""Site inventory: filtered search and point lookup over the object dataset.

The point lookup uses the same footprint test as the collision detector.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_current_user
from app.models.user import User
from app.services import site

router = APIRouter(prefix="/api/site", tags=["site"])

# Page-size ceiling, shared by the map viewport and the inventory table.
MAX_LIMIT = 2000


@router.get("")
async def get_site(_: User = Depends(get_current_user)) -> dict:
    """Map image, projection, boundary, launch pads, routes and type counts."""
    return site.describe()


@router.get("/objects")
async def list_objects(
    q: str | None = Query(None, description="Free text over id, type, use, species, model…"),
    type: list[str] | None = Query(None, description="Repeatable. Restrict to these types."),
    min_height: float | None = Query(None, ge=0),
    max_height: float | None = Query(None, ge=0),
    south: float | None = Query(None, description="Viewport bounds, all four or none."),
    west: float | None = None,
    north: float | None = None,
    east: float | None = None,
    near_lat: float | None = Query(None, ge=-90, le=90, description="Search near a position."),
    near_lon: float | None = Query(None, ge=-180, le=180),
    radius_m: float = Query(100.0, ge=0, le=5000, description="Used with near_lat/near_lon."),
    inside_area: bool | None = Query(None, description="Only in/outside the operational area."),
    include_scenery: bool = Query(True, description="False drops trees, fields and panel tables."),
    sort: str = Query("type", pattern="^(type|height|size|id|distance)$"),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=MAX_LIMIT),
    _: User = Depends(get_current_user),
) -> dict:
    """Filter the site inventory; returns one page plus the total matched.

    `near_lat`/`near_lon` with `radius_m` returns nearby objects, nearest first,
    with distances measured to the footprint.
    """
    bounds = None
    if any(v is not None for v in (south, west, north, east)):
        if None in (south, west, north, east):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Give all four of south, west, north and east, or none of them.",
            )
        bounds = (south, west, north, east)

    near = None
    if near_lat is not None or near_lon is not None:
        if near_lat is None or near_lon is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Give both near_lat and near_lon, or neither.",
            )
        near = (near_lat, near_lon)

    return site.query_objects(
        q=q, types=type, min_height=min_height, max_height=max_height,
        bounds=bounds, near=near, radius_m=radius_m, inside_area=inside_area,
        include_scenery=include_scenery, sort=sort, offset=offset, limit=limit,
    )


@router.get("/objects/at")
async def objects_at_point(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    alt: float | None = Query(None, description="If given, also says what would be hit here."),
    _: User = Depends(get_current_user),
) -> dict:
    """Everything whose footprint covers a position, tallest first.

    With `alt`, `would_hit` applies the collision detector's rule at that altitude.
    """
    hits = [site.public_object(o) for o in site.objects_at(lat, lon)]
    out: dict = {
        "lat": lat,
        "lon": lon,
        "grid_ref": site.grid_ref(lat, lon),
        "inside_operational_area": site.inside_boundary(lat, lon),
        "objects": hits,
    }
    if not out["inside_operational_area"]:
        out["metres_outside_area"] = round(site.distance_outside_m(lat, lon), 1)
    if alt is not None:
        ob = site.obstacle_at(lat, lon, alt)
        out["would_hit"] = site.public_object(ob) if ob else None
        out["alt"] = alt
    return out


@router.get("/objects/{object_id}")
async def get_object(object_id: str, _: User = Depends(get_current_user)) -> dict:
    o = site.object_by_id(object_id)
    if o is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No object {object_id}")
    return o
