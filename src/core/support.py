"""
Support structure generator.

Detects overhanging areas and generates support columns below them.
Returns per-layer support paths as lists of numpy arrays.
"""

import numpy as np
from typing import List, Dict, Optional

try:
    from shapely.geometry import Polygon, MultiPolygon, box
    from shapely.ops import unary_union
    SHAPELY_OK = True
except ImportError:
    SHAPELY_OK = False

try:
    import trimesh
    TRIMESH_OK = True
except ImportError:
    TRIMESH_OK = False


def _face_overhang_angle(face_normal: np.ndarray) -> float:
    """
    Return the overhang angle in degrees for a face.
    0° = flat upward face, 90° = vertical, >90° = overhanging.
    """
    # Normal pointing down has z < 0
    # Overhang angle: angle between face normal and straight-down vector (0,0,-1)
    # A face is overhanging when its normal points partially downward.
    down = np.array([0.0, 0.0, -1.0])
    dot = np.clip(np.dot(face_normal, down), -1.0, 1.0)
    return np.degrees(np.arccos(dot))


def detect_overhangs(mesh, threshold_angle: float = 45.0) -> np.ndarray:
    """
    Return boolean mask of faces that are overhanging beyond threshold_angle.
    Faces with normals pointing more than threshold away from vertical are overhangs.
    """
    normals = mesh.face_normals  # (M, 3)
    # A face is an overhang if its normal has a negative z component
    # and the angle from straight-down is less than (90 - threshold)
    # i.e., normal_z < -cos(threshold_angle)
    threshold_cos = np.cos(np.radians(90.0 - threshold_angle))
    overhang_mask = normals[:, 2] < -threshold_cos
    return overhang_mask


def get_overhang_regions(mesh, threshold_angle: float = 45.0):
    """
    Return shapely polygons (in XY plane) of overhang regions.
    """
    if not SHAPELY_OK or not TRIMESH_OK:
        return []

    overhang_mask = detect_overhangs(mesh, threshold_angle)
    if not np.any(overhang_mask):
        return []

    overhang_faces = mesh.faces[overhang_mask]
    overhang_verts = mesh.vertices

    polygons = []
    for face in overhang_faces:
        pts = overhang_verts[face][:, :2]  # just x, y
        if len(pts) >= 3:
            try:
                poly = Polygon(pts)
                if poly.is_valid and not poly.is_empty:
                    polygons.append(poly)
            except Exception:
                pass

    if not polygons:
        return []

    try:
        merged = unary_union(polygons)
        if merged.is_empty:
            return []
        if isinstance(merged, Polygon):
            return [merged]
        elif isinstance(merged, MultiPolygon):
            return list(merged.geoms)
        return []
    except Exception:
        return polygons


def generate_support_paths(
    overhang_regions: list,
    z_start: float,
    z_end: float,
    layer_height: float,
    line_width: float,
    density: float = 20.0
) -> Dict[int, List[np.ndarray]]:
    """
    Generate support line paths for layers from z_start to z_end.

    Returns dict: layer_index -> list of numpy arrays [(x1,y1),(x2,y2)]
    """
    if not SHAPELY_OK or not overhang_regions:
        return {}

    # Merge overhang regions
    try:
        support_area = unary_union(overhang_regions)
        # Add small buffer to ensure coverage
        support_area = support_area.buffer(line_width)
    except Exception:
        return {}

    if support_area.is_empty:
        return {}

    spacing = line_width / (max(density, 1.0) / 100.0)
    result = {}

    z = z_start
    layer_idx = 0

    while z <= z_end + 1e-6:
        segments = _generate_support_lines(support_area, spacing, layer_idx)
        if segments:
            result[layer_idx] = segments
        z += layer_height
        layer_idx += 1

    return result


def _generate_support_lines(polygon, spacing: float, layer_num: int) -> List[np.ndarray]:
    """Generate a grid of support lines within the polygon."""
    if not SHAPELY_OK or polygon is None or polygon.is_empty:
        return []

    from src.core.infill import lines_infill
    return lines_infill(polygon, density=20.0, line_width=spacing * 0.5, layer_num=layer_num)


def compute_support_layers(
    mesh,
    layer_heights: List[float],
    layer_height: float,
    line_width: float,
    threshold_angle: float = 45.0,
    density: float = 20.0
) -> Dict[int, List[np.ndarray]]:
    """
    High-level function: compute support paths for all layers.

    Args:
        mesh: Mesh object (has .trimesh property) or trimesh.Trimesh
        layer_heights: list of z values for each layer
        layer_height: layer height in mm
        line_width: extrusion line width in mm
        threshold_angle: overhang angle in degrees
        density: support density percent

    Returns:
        Dict mapping layer_index -> list of path segments
    """
    if not SHAPELY_OK or not TRIMESH_OK:
        return {}

    # Get the underlying trimesh
    try:
        tri = mesh.trimesh if hasattr(mesh, 'trimesh') else mesh
    except Exception:
        return {}

    overhang_regions = get_overhang_regions(tri, threshold_angle)
    if not overhang_regions:
        return {}

    support_paths = {}

    try:
        merged_overhang = unary_union(overhang_regions)
        if merged_overhang.is_empty:
            return {}
        # Buffer slightly for safety margin
        support_footprint = merged_overhang.buffer(line_width * 2)
    except Exception:
        return {}

    spacing = line_width / max(density / 100.0, 0.01)

    for layer_idx, z in enumerate(layer_heights):
        segments = _generate_support_lines(support_footprint, spacing, layer_idx)
        if segments:
            support_paths[layer_idx] = segments

    return support_paths
