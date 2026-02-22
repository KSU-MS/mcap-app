import base64
import math
import urllib.request
from pathlib import Path

from django.conf import settings


TILE_SIZE = 256
DEFAULT_WIDTH = 232
DEFAULT_HEIGHT = 144
DEFAULT_PADDING = 14


def _clamp_lat(lat: float) -> float:
    return max(min(lat, 85.05112878), -85.05112878)


def _lonlat_to_world_pixels(lon: float, lat: float, zoom: int) -> tuple[float, float]:
    lat = _clamp_lat(lat)
    scale = TILE_SIZE * (2**zoom)
    x = (lon + 180.0) / 360.0 * scale
    sin_lat = math.sin(math.radians(lat))
    y = (0.5 - math.log((1 + sin_lat) / (1 - sin_lat)) / (4 * math.pi)) * scale
    return x, y


def _pick_zoom(
    coords: list[tuple[float, float]], width: int, height: int, padding: int
) -> int:
    if len(coords) < 2:
        return 12

    min_lon = min(c[0] for c in coords)
    max_lon = max(c[0] for c in coords)
    min_lat = min(c[1] for c in coords)
    max_lat = max(c[1] for c in coords)

    usable_width = max(width - 2 * padding, 10)
    usable_height = max(height - 2 * padding, 10)

    for zoom in range(18, 1, -1):
        min_x, min_y = _lonlat_to_world_pixels(min_lon, max_lat, zoom)
        max_x, max_y = _lonlat_to_world_pixels(max_lon, min_lat, zoom)
        if (max_x - min_x) <= usable_width and (max_y - min_y) <= usable_height:
            return zoom
    return 2


def _tile_url(z: int, x: int, y: int) -> str:
    template = getattr(
        settings,
        "MAP_PREVIEW_TILE_URL_TEMPLATE",
        "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    )
    return template.format(z=z, x=x, y=y)


def _fetch_tile_data_uri(z: int, x: int, y: int) -> str | None:
    url = _tile_url(z, x, y)
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "mcap-query-backend-map-preview/1.0",
            "Accept": "image/png,image/*;q=0.8,*/*;q=0.5",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as response:
            if response.status != 200:
                return None
            raw = response.read()
            return "data:image/png;base64," + base64.b64encode(raw).decode("ascii")
    except Exception:
        return None


def _to_svg_path(points: list[tuple[float, float]]) -> str:
    if not points:
        return ""
    first_x, first_y = points[0]
    cmds = [f"M {first_x:.2f} {first_y:.2f}"]
    cmds.extend(f"L {x:.2f} {y:.2f}" for x, y in points[1:])
    return " ".join(cmds)


def generate_map_preview_svg(
    log_id: int,
    coords: list[tuple[float, float]],
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    padding: int = DEFAULT_PADDING,
) -> tuple[str, str]:
    if not coords:
        raise ValueError("No coordinates available for map preview generation")

    zoom = _pick_zoom(coords, width, height, padding)
    world_points = [_lonlat_to_world_pixels(lon, lat, zoom) for lon, lat in coords]

    min_x = min(p[0] for p in world_points)
    max_x = max(p[0] for p in world_points)
    min_y = min(p[1] for p in world_points)
    max_y = max(p[1] for p in world_points)

    path_width = max(max_x - min_x, 1.0)
    path_height = max(max_y - min_y, 1.0)
    offset_x = (width - path_width) / 2.0 - min_x
    offset_y = (height - path_height) / 2.0 - min_y

    view_min_x = -offset_x
    view_max_x = width - offset_x
    view_min_y = -offset_y
    view_max_y = height - offset_y

    tile_min_x = math.floor(view_min_x / TILE_SIZE)
    tile_max_x = math.floor(view_max_x / TILE_SIZE)
    tile_min_y = math.floor(view_min_y / TILE_SIZE)
    tile_max_y = math.floor(view_max_y / TILE_SIZE)

    tile_count = 2**zoom
    tile_images: list[str] = []
    for ty in range(tile_min_y, tile_max_y + 1):
        if ty < 0 or ty >= tile_count:
            continue
        for tx in range(tile_min_x, tile_max_x + 1):
            wrapped_x = tx % tile_count
            data_uri = _fetch_tile_data_uri(zoom, wrapped_x, ty)
            if not data_uri:
                continue
            img_x = tx * TILE_SIZE + offset_x
            img_y = ty * TILE_SIZE + offset_y
            tile_images.append(
                f'<image x="{img_x:.2f}" y="{img_y:.2f}" width="{TILE_SIZE}" height="{TILE_SIZE}" href="{data_uri}" />'
            )

    screen_points = [(x + offset_x, y + offset_y) for x, y in world_points]
    path_d = _to_svg_path(screen_points)
    start = screen_points[0]
    end = screen_points[-1]

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
        f'<defs><clipPath id="clip"><rect x="0" y="0" width="{width}" height="{height}" rx="8" ry="8" /></clipPath></defs>'
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#f5f2ea" rx="8" ry="8" />'
        f'<g clip-path="url(#clip)">{"".join(tile_images)}</g>'
        f'<path d="{path_d}" fill="none" stroke="#C38822" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" />'
        f'<circle cx="{start[0]:.2f}" cy="{start[1]:.2f}" r="4" fill="#1e7b34" stroke="#ffffff" stroke-width="1.2" />'
        f'<circle cx="{end[0]:.2f}" cy="{end[1]:.2f}" r="4" fill="#a7261c" stroke="#ffffff" stroke-width="1.2" />'
        "</svg>"
    )

    preview_dir = Path(settings.MEDIA_ROOT) / "map_previews"
    preview_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{log_id}.svg"
    file_path = preview_dir / filename
    file_path.write_text(svg, encoding="utf-8")

    media_prefix = settings.MEDIA_URL.rstrip("/")
    uri = f"{media_prefix}/map_previews/{filename}"
    return str(file_path), uri
