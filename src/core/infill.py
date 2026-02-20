"""
Infill pattern generators.

Each function accepts:
    polygon     : shapely.geometry.Polygon or MultiPolygon (the inner area to fill)
    density     : float, 0-100 (percent)
    line_width  : float mm
    layer_num   : int (used to alternate direction each layer)

Returns:
    List of numpy arrays, each shape (2, 2) -> [[x1,y1],[x2,y2]] representing
    a line segment.  Empty list if polygon is empty / density is 0.
"""

import math
import numpy as np
from typing import List

try:
    from shapely.geometry import (
        Polygon, MultiPolygon, LineString, MultiLineString, GeometryCollection
    )
    from shapely.ops import unary_union
    import shapely.affinity as aff
    SHAPELY_OK = True
except ImportError:
    SHAPELY_OK = False


def _clip_lines_to_polygon(lines, polygon):
    """Intersect a list of LineStrings with the polygon, returning segments."""
    segments = []
    for line in lines:
        try:
            clipped = line.intersection(polygon)
        except Exception:
            continue
        if clipped.is_empty:
            continue
        if isinstance(clipped, LineString):
            coords = list(clipped.coords)
            for i in range(len(coords) - 1):
                segments.append(np.array([coords[i], coords[i + 1]], dtype=np.float32))
        elif isinstance(clipped, (MultiLineString, GeometryCollection)):
            for geom in clipped.geoms:
                if isinstance(geom, LineString):
                    coords = list(geom.coords)
                    for i in range(len(coords) - 1):
                        segments.append(np.array([coords[i], coords[i + 1]], dtype=np.float32))
    return segments


def _line_spacing(density: float, line_width: float) -> float:
    """Convert density % to line spacing in mm."""
    density = max(1.0, min(density, 100.0))
    return line_width / (density / 100.0)


def _bounding_lines(polygon, angle_deg: float, spacing: float) -> List:
    """Generate parallel lines at given angle covering the polygon bounding box."""
    if not SHAPELY_OK:
        return []
    bounds = polygon.bounds  # (minx, miny, maxx, maxy)
    minx, miny, maxx, maxy = bounds
    cx = (minx + maxx) / 2
    cy = (miny + maxy) / 2
    diag = math.hypot(maxx - minx, maxy - miny) * 0.6 + spacing

    lines = []
    angle_rad = math.radians(angle_deg)
    # Direction perpendicular to lines
    perp_x = math.cos(angle_rad + math.pi / 2)
    perp_y = math.sin(angle_rad + math.pi / 2)
    # Direction along lines
    dir_x = math.cos(angle_rad)
    dir_y = math.sin(angle_rad)

    n = int(math.ceil(diag * 2 / spacing)) + 1
    for i in range(-n, n + 1):
        ox = cx + perp_x * i * spacing
        oy = cy + perp_y * i * spacing
        x1 = ox - dir_x * diag
        y1 = oy - dir_y * diag
        x2 = ox + dir_x * diag
        y2 = oy + dir_y * diag
        lines.append(LineString([(x1, y1), (x2, y2)]))
    return lines


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def grid_infill(polygon, density: float, line_width: float, layer_num: int) -> List[np.ndarray]:
    """
    Grid (rectilinear) infill: two sets of parallel lines at 90° to each other.
    """
    if not SHAPELY_OK or polygon is None or polygon.is_empty:
        return []

    spacing = _line_spacing(density, line_width)
    # Alternate base angle each layer
    base_angle = 45.0 if (layer_num % 2 == 0) else -45.0

    lines_a = _bounding_lines(polygon, base_angle, spacing)
    lines_b = _bounding_lines(polygon, base_angle + 90.0, spacing)

    segments = []
    segments += _clip_lines_to_polygon(lines_a, polygon)
    segments += _clip_lines_to_polygon(lines_b, polygon)
    return segments


def lines_infill(polygon, density: float, line_width: float, layer_num: int) -> List[np.ndarray]:
    """
    Lines infill: single set of parallel lines, alternating direction each layer.
    """
    if not SHAPELY_OK or polygon is None or polygon.is_empty:
        return []

    spacing = _line_spacing(density, line_width)
    angle = 45.0 + (layer_num % 2) * 90.0

    lines = _bounding_lines(polygon, angle, spacing)
    return _clip_lines_to_polygon(lines, polygon)


def honeycomb_infill(polygon, density: float, line_width: float, layer_num: int) -> List[np.ndarray]:
    """
    Honeycomb (hexagonal) infill pattern.
    """
    if not SHAPELY_OK or polygon is None or polygon.is_empty:
        return []

    spacing = _line_spacing(density, line_width)
    hex_size = spacing  # approximate cell size

    bounds = polygon.bounds
    minx, miny, maxx, maxy = bounds
    pad = hex_size * 2

    segments = []

    # Build a hex grid
    # Hex geometry: flat-top hexagons
    w = hex_size * math.sqrt(3)
    h = hex_size * 2
    row_h = h * 0.75

    col = 0
    x = minx - pad
    while x < maxx + pad:
        row = 0
        y = miny - pad
        while y < maxy + pad:
            # Offset every other column
            offset_y = (hex_size * 0.5) if (col % 2 == 1) else 0.0
            cx_h = x
            cy_h = y + offset_y

            # Six vertices of hex
            verts = []
            for k in range(6):
                angle_deg = 60 * k + 30  # flat-top
                vx = cx_h + hex_size * math.cos(math.radians(angle_deg))
                vy = cy_h + hex_size * math.sin(math.radians(angle_deg))
                verts.append((vx, vy))
            verts.append(verts[0])  # close

            # Add edges as line segments
            for i in range(len(verts) - 1):
                try:
                    line = LineString([verts[i], verts[i + 1]])
                    clipped = line.intersection(polygon)
                    if clipped.is_empty:
                        continue
                    if isinstance(clipped, LineString):
                        coords = list(clipped.coords)
                        for j in range(len(coords) - 1):
                            segments.append(np.array([coords[j], coords[j + 1]], dtype=np.float32))
                    elif isinstance(clipped, (MultiLineString, GeometryCollection)):
                        for geom in clipped.geoms:
                            if isinstance(geom, LineString):
                                coords = list(geom.coords)
                                for j in range(len(coords) - 1):
                                    segments.append(np.array([coords[j], coords[j + 1]], dtype=np.float32))
                except Exception:
                    pass

            y += row_h
            row += 1
        x += w
        col += 1

    return segments


def solid_infill(polygon, line_width: float, angle_deg: float = 45.0) -> List[np.ndarray]:
    """
    Solid fill (used for top/bottom layers). Full 100% density rectilinear.
    """
    if not SHAPELY_OK or polygon is None or polygon.is_empty:
        return []
    lines = _bounding_lines(polygon, angle_deg, line_width)
    return _clip_lines_to_polygon(lines, polygon)


def get_infill_function(pattern: str):
    """Return the infill generator function for the given pattern name."""
    mapping = {
        'grid': grid_infill,
        'lines': lines_infill,
        'honeycomb': honeycomb_infill,
    }
    return mapping.get(pattern, grid_infill)
