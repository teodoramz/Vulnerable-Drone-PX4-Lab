# Map source

The site is two files that must agree:

| File | What it is | Read by |
|---|---|---|
| `assets/airport-source.jpg` | authored map, 8000 x 5600 px | downscaled into the frontend |
| `services/c2/app/data/airport_objects.json` | 15,793 objects, boundary, projection | the C2, at import |

The JSON is the source of truth; the image is a backdrop. The objects file is
not duplicated here, so there is no second copy to drift.

## Projection

The dataset carries its own geography:

```json
"meters_per_pixel": 0.625,
"origin_lat": 44.0, "origin_lon": 25.0, "origin_pixel": [4000.0, 2800.0],
"formula": "lat = origin_lat - (py - 2800) * 0.625 / 111320 ; ..."
```

`app/services/site.py` reproduces that formula exactly, including evaluating
`cos()` once at the origin latitude. Evaluating it per point shifts
coordinates several metres away from the values in the file. A test asserts
the two agree to within half a metre across a sample of the dataset.

Everything else is derived from the data:

| What | Source |
|---|---|
| Ground extent, projection | `map.meters_per_pixel`, `map.origin_*` |
| Operational area | `operational_area.boundary_latlon` |
| Launch pads | `helipad` objects, by designator (HP-1, HP-2) |
| Obstacles and heights | each object's `footprint` / `length` / `width` / `height_m` |
| Grid references | `grid`, 500 m cells, A-J x 1-7 |
| Patrol routes | the dataset's runways, terminal and boundary |

`HOME_LAT` and `HOME_LON` are not configuration. A drone may only launch from
a pad, and the seed takes home from `site.LAUNCH_PADS`.

## Swapping the map

Replace both files with the same shape, then regenerate the frontend image:

```bash
cp new-map.jpg       assets/airport-source.jpg
cp new-objects.json  services/c2/app/data/airport_objects.json

python3 -c "
from PIL import Image
Image.MAX_IMAGE_PIXELS = None
im = Image.open('assets/airport-source.jpg').convert('RGB')
im.resize((4000, round(4000 * im.height / im.width)), Image.LANCZOS).save(
    'services/frontend/public/map/airport.jpg',
    quality=86, optimize=True, progressive=True)
"
```

Then run the C2 tests. They check the projection against the dataset, that
every patrol route stays inside the boundary and clears every structure at
patrol altitude, that home is on a pad, and that a drone can take off from
each pad without being lost.

The frontend image is 4000 x 2800 at 1.25 m per pixel, about 2.4 MB;
`ImageOverlay` decodes the whole file in the browser. Object outlines are
drawn as vectors from the JSON, so hit-testing is unaffected by the image
resolution.

## What the console receives

The browser never gets the full 3.9 MB dataset:

- `GET /api/site` - map, projection, boundary, pads, routes, type summary. No objects.
- `GET /api/site/objects?...` - a filtered page, for the Inventory tab and viewport outlines.
- `GET /api/site/objects/at?lat=&lon=` - what is at a point, using the collision detector's own footprint test.
