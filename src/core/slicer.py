"""
Full slicing engine.

Slices a 3D mesh into layers and generates per-layer tool paths
(perimeters, infill, solid top/bottom, support).
"""

import math
import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional, Callable, Any

try:
    import trimesh
    TRIMESH_OK = True
except ImportError:
    TRIMESH_OK = False

try:
    from shapely.geometry import (
        Polygon, MultiPolygon, LineString, MultiLineString,
        GeometryCollection
    )
    from shapely.ops import unary_union
    from shapely.validation import make_valid
    SHAPELY_OK = True
except ImportError:
    SHAPELY_OK = False

from src.core.infill import get_infill_function, solid_infill


# ---------------------------------------------------------------------------
# Settings dataclass
# ---------------------------------------------------------------------------

@dataclass
class SliceSettings:
    # ---- Layer / extrusion ----
    layer_height: float = 0.2
    first_layer_height: float = 0.3
    line_width: float = 0.4            # absolute mm (derived from nozzle * pct)
    line_width_pct: float = 100.0      # % of nozzle diameter (80–150)
    nozzle_diameter: float = 0.4
    filament_diameter: float = 1.75

    # ---- Walls ----
    wall_count: int = 3
    outer_before_inner: bool = False   # print order: outer first
    seam_position: str = 'back'        # 'back' | 'random' | 'sharpest'

    # ---- Infill ----
    infill_density: float = 20.0       # percent 0–100
    infill_pattern: str = 'grid'       # 'grid' | 'lines' | 'honeycomb'
    infill_angle: float = 45.0         # base angle in degrees
    infill_overlap: float = 10.0       # % overlap into perimeter
    sparse_before_walls: bool = False  # infill before walls (less stringing)

    # ---- Top / Bottom ----
    top_layers: int = 4
    bottom_layers: int = 4
    skin_overlap: float = 5.0          # % overlap of top/bottom into perimeter

    # ---- Skirt / Brim ----
    brim_enabled: bool = False
    brim_width: float = 8.0            # mm

    # ---- Retraction ----
    retraction_enabled: bool = True
    retraction_distance: float = 5.0   # mm
    retraction_speed: float = 45.0     # mm/s
    retraction_z_hop: float = 0.0      # mm lift during travel (0 = off)
    retraction_min_distance: float = 1.5  # mm – shorter travels skip retract
    retraction_extra_prime: float = 0.0   # mm extra material after retract

    # ---- Speed ----
    print_speed: float = 60.0          # general / inner wall mm/s
    outer_perimeter_speed: float = 40.0  # outer wall (quality critical)
    top_bottom_speed: float = 40.0     # top/bottom solid layers
    infill_speed: float = 80.0         # sparse infill
    bridge_speed: float = 25.0         # bridging
    first_layer_speed: float = 25.0    # all features on layer 0
    travel_speed: float = 200.0

    # ---- Temperature ----
    print_temp: int = 210
    print_temp_first_layer: int = 215  # higher for better adhesion
    bed_temp: int = 60

    # ---- Cooling / Fan ----
    fan_speed: int = 100               # normal fan speed %
    fan_first_layer: int = 0           # fan % for layer 0 (usually 0)
    fan_kick_in_layer: int = 2         # layer number to start fan
    min_layer_time: float = 5.0        # minimum seconds/layer (slow down if faster)

    # ---- Spiralize / Non-stop (Vase) mode ----
    spiralize_mode: bool = False   # Z+XY 同時移動でつなぎ目なし印刷

    # ---- Support ----
    support_enabled: bool = False
    support_threshold: float = 45.0    # overhang angle degrees
    support_density: float = 15.0      # percent
    support_pattern: str = 'lines'     # 'lines' | 'grid' | 'zigzag'
    support_interface_enabled: bool = True
    support_interface_layers: int = 2
    support_z_distance: float = 0.2    # mm gap above/below
    support_xy_distance: float = 0.7   # mm gap from model sides


# ---------------------------------------------------------------------------
# SlicedLayer
# ---------------------------------------------------------------------------

@dataclass
class SlicedLayer:
    z: float
    layer_num: int
    perimeters: List[np.ndarray] = field(default_factory=list)
    infill: List[np.ndarray] = field(default_factory=list)
    top_bottom: List[np.ndarray] = field(default_factory=list)
    support: List[np.ndarray] = field(default_factory=list)
    brim: List[np.ndarray] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Path conversion helpers
# ---------------------------------------------------------------------------

def _path2d_to_shapely(path2d) -> List[Polygon]:
    """Convert a trimesh Path2D cross-section to a list of shapely Polygons."""
    polygons = []
    if path2d is None:
        return polygons

    try:
        # Use trimesh's built-in conversion
        polys = path2d.polygons_full
        if polys is not None:
            for p in polys:
                if p is not None and not p.is_empty:
                    if not p.is_valid:
                        p = make_valid(p)
                    if isinstance(p, Polygon) and not p.is_empty:
                        polygons.append(p)
                    elif isinstance(p, MultiPolygon):
                        polygons.extend([g for g in p.geoms if not g.is_empty])
        return polygons
    except Exception:
        pass

    # Fallback: iterate over discrete entities
    try:
        for entity in path2d.entities:
            try:
                pts = path2d.vertices[entity.points]
                if len(pts) >= 3:
                    poly = Polygon(pts[:, :2])
                    if not poly.is_valid:
                        poly = make_valid(poly)
                    if isinstance(poly, Polygon) and not poly.is_empty:
                        polygons.append(poly)
            except Exception:
                continue
    except Exception:
        pass

    return polygons


def _polygon_to_path_array(polygon: Polygon) -> np.ndarray:
    """Convert a Shapely Polygon exterior ring to numpy array (N, 2)."""
    coords = np.array(polygon.exterior.coords, dtype=np.float32)
    return coords


def _polygons_from_section(section) -> List[Polygon]:
    """Extract shapely polygons from a trimesh cross-section result."""
    if section is None:
        return []

    polys = []
    if hasattr(section, '__iter__'):
        # It's a list of Path2D objects (one per section plane)
        for path2d in section:
            if path2d is None:
                continue
            polys.extend(_path2d_to_shapely(path2d))
    else:
        polys.extend(_path2d_to_shapely(section))

    return polys


# ---------------------------------------------------------------------------
# Perimeter generation
# ---------------------------------------------------------------------------

def _generate_perimeters(polygon: Polygon, wall_count: int, line_width: float) -> List[np.ndarray]:
    """
    Generate wall_count offset perimeters for a polygon.
    Returns list of (N, 2) numpy arrays.
    """
    perimeters = []
    current = polygon

    for i in range(wall_count):
        if current is None or current.is_empty:
            break
        try:
            # Exterior ring
            coords = np.array(current.exterior.coords, dtype=np.float32)
            perimeters.append(coords)

            # Inner holes become their own perimeters (for complex shapes)
            for interior in current.interiors:
                hole_coords = np.array(interior.coords, dtype=np.float32)
                perimeters.append(hole_coords)

            # Offset inward
            offset = current.buffer(-line_width, join_style=2)
            if offset is None or offset.is_empty:
                break
            if not offset.is_valid:
                offset = make_valid(offset)

            if isinstance(offset, MultiPolygon):
                # Take largest
                current = max(offset.geoms, key=lambda p: p.area)
            elif isinstance(offset, Polygon):
                current = offset
            else:
                break
        except Exception:
            break

    return perimeters


def _get_inner_area(polygon: Polygon, wall_count: int, line_width: float) -> Optional[Polygon]:
    """Get the inner area after wall_count offsets (for infill)."""
    current = polygon
    offset_dist = wall_count * line_width

    try:
        inner = current.buffer(-offset_dist, join_style=2)
        if inner is None or inner.is_empty:
            return None
        if not inner.is_valid:
            inner = make_valid(inner)
        if isinstance(inner, MultiPolygon):
            polys = [g for g in inner.geoms if not g.is_empty]
            return unary_union(polys) if polys else None
        return inner
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Brim generation
# ---------------------------------------------------------------------------

def _generate_brim(polygon: Polygon, brim_width: float, line_width: float) -> List[np.ndarray]:
    """Generate brim loops outward from the polygon."""
    brim = []
    brim_loops = max(1, int(round(brim_width / line_width)))
    current = polygon

    for i in range(brim_loops):
        try:
            offset = current.buffer(line_width * (i + 1), join_style=2)
            if offset is None or offset.is_empty:
                break
            if not offset.is_valid:
                offset = make_valid(offset)
            if isinstance(offset, Polygon):
                brim.append(np.array(offset.exterior.coords, dtype=np.float32))
            elif isinstance(offset, MultiPolygon):
                for p in offset.geoms:
                    brim.append(np.array(p.exterior.coords, dtype=np.float32))
        except Exception:
            break

    return brim


# ---------------------------------------------------------------------------
# Main Slicer class
# ---------------------------------------------------------------------------

class Slicer:
    """
    Slices a Mesh into layers and generates tool paths.
    """

    def __init__(self):
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def slice(
        self,
        mesh_obj,
        settings: SliceSettings,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> List[SlicedLayer]:
        """
        Slice mesh_obj (Mesh or trimesh.Trimesh) with given settings.

        progress_callback(current, total, message) is called periodically.

        Returns list of SlicedLayer objects.
        """
        self._cancelled = False

        # Get underlying trimesh
        if hasattr(mesh_obj, 'trimesh'):
            tri = mesh_obj.trimesh
        else:
            tri = mesh_obj

        # Compute Z range
        z_min = float(tri.bounds[0, 2])
        z_max = float(tri.bounds[1, 2])

        # Build layer Z positions
        z_heights = [z_min + settings.first_layer_height]
        z = z_min + settings.first_layer_height + settings.layer_height
        while z <= z_max + 1e-6:
            z_heights.append(z)
            z += settings.layer_height

        total_layers = len(z_heights)
        if progress_callback:
            progress_callback(0, total_layers, f"Slicing {total_layers} layers...")

        # --- Cross-section using trimesh section_multiplane ---
        # API: section_multiplane(plane_origin, plane_normal, heights)
        # heights are offsets from plane_origin along plane_normal
        z_base = float(tri.bounds[0, 2])
        heights = [z - z_base for z in z_heights]

        try:
            sections = tri.section_multiplane(
                plane_origin=[0.0, 0.0, z_base],
                plane_normal=[0.0, 0.0, 1.0],
                heights=heights
            )
        except Exception as e:
            print(f"[Slicer] section_multiplane failed: {e}")
            sections = [None] * total_layers

        # Detect support layers if enabled
        support_paths = {}
        if settings.support_enabled:
            try:
                from src.core.support import compute_support_layers
                support_paths = compute_support_layers(
                    mesh_obj,
                    z_heights,
                    settings.layer_height,
                    settings.line_width,
                    settings.support_threshold,
                    settings.support_density
                )
            except Exception as e:
                print(f"[Slicer] Support generation failed: {e}")

        # --- Process each layer ---
        layers = []
        infill_fn = get_infill_function(settings.infill_pattern)

        for layer_idx, (z, section) in enumerate(zip(z_heights, sections)):
            if self._cancelled:
                break

            if progress_callback and layer_idx % 5 == 0:
                progress_callback(layer_idx, total_layers, f"Processing layer {layer_idx + 1}/{total_layers}")

            sliced = SlicedLayer(z=z, layer_num=layer_idx)

            # Get polygons for this layer
            try:
                polys = _polygons_from_section(section)
            except Exception:
                polys = []

            if not polys:
                layers.append(sliced)
                continue

            # Merge polygons for this layer
            try:
                layer_poly = unary_union(polys)
                if not layer_poly.is_valid:
                    layer_poly = make_valid(layer_poly)
            except Exception:
                layers.append(sliced)
                continue

            # Determine if this is a solid layer (top or bottom)
            is_bottom = layer_idx < settings.bottom_layers
            is_top = layer_idx >= total_layers - settings.top_layers
            is_solid = is_bottom or is_top

            # Process each polygon component
            if isinstance(layer_poly, Polygon):
                poly_list = [layer_poly]
            elif isinstance(layer_poly, MultiPolygon):
                poly_list = list(layer_poly.geoms)
            else:
                poly_list = []

            for poly in poly_list:
                if poly.is_empty or poly.area < 1e-6:
                    continue

                try:
                    # Generate perimeters
                    perims = _generate_perimeters(poly, settings.wall_count, settings.line_width)
                    sliced.perimeters.extend(perims)

                    # Get inner area for infill
                    inner = _get_inner_area(poly, settings.wall_count, settings.line_width)

                    if inner is not None and not inner.is_empty:
                        if is_solid:
                            # Solid infill for top/bottom layers
                            angle = 45.0 + (layer_idx % 2) * 90.0
                            solid_segs = solid_infill(inner, settings.line_width, angle)
                            sliced.top_bottom.extend(solid_segs)
                        else:
                            # Sparse infill
                            if settings.infill_density > 0:
                                infill_segs = infill_fn(
                                    inner,
                                    settings.infill_density,
                                    settings.line_width,
                                    layer_idx
                                )
                                sliced.infill.extend(infill_segs)

                    # Brim on first layer
                    if layer_idx == 0 and settings.brim_enabled:
                        brim_paths = _generate_brim(poly, settings.brim_width, settings.line_width)
                        sliced.brim.extend(brim_paths)

                except Exception as e:
                    print(f"[Slicer] Layer {layer_idx} polygon processing error: {e}")
                    continue

            # Add support paths
            if layer_idx in support_paths:
                sliced.support = support_paths[layer_idx]

            layers.append(sliced)

        if progress_callback:
            progress_callback(total_layers, total_layers, f"Slicing complete: {len(layers)} layers")

        return layers

    @staticmethod
    def estimate_print_time(layers: List[SlicedLayer], settings: SliceSettings) -> float:
        """
        Estimate print time in seconds.
        """
        total_time = 0.0
        heat_time = 5 * 60  # 5 minutes for heating
        total_time += heat_time

        ps = settings.print_speed * 60  # mm/min -> mm/s... actually keep in mm/min
        fs = settings.first_layer_speed * 60
        is_ = settings.infill_speed * 60
        ts = settings.travel_speed * 60

        def path_length(paths):
            total = 0.0
            for p in paths:
                if p is None or len(p) < 2:
                    continue
                arr = np.array(p)
                if arr.ndim == 2 and arr.shape[1] >= 2:
                    diffs = np.diff(arr, axis=0)
                    total += float(np.sum(np.linalg.norm(diffs, axis=1)))
            return total

        for layer in layers:
            speed = fs if layer.layer_num == 0 else ps
            # Perimeters
            total_time += path_length(layer.perimeters) / speed * 60
            # Infill
            total_time += path_length(layer.infill) / is_ * 60
            total_time += path_length(layer.top_bottom) / is_ * 60
            # Support
            total_time += path_length(layer.support) / is_ * 60
            # Brim
            total_time += path_length(layer.brim) / fs * 60

        return total_time  # seconds

    @staticmethod
    def estimate_filament(layers: List[SlicedLayer], settings: SliceSettings) -> float:
        """
        Estimate filament usage in grams.
        Returns weight in grams (PLA density ~1.24 g/cm³).
        """
        filament_r = settings.filament_diameter / 2.0
        filament_area = math.pi * filament_r ** 2  # mm²
        nozzle_area = settings.line_width * settings.layer_height  # mm² of extrusion cross-section

        def path_length(paths):
            total = 0.0
            for p in paths:
                if p is None or len(p) < 2:
                    continue
                arr = np.array(p)
                if arr.ndim == 2 and arr.shape[1] >= 2:
                    diffs = np.diff(arr, axis=0)
                    total += float(np.sum(np.linalg.norm(diffs, axis=1)))
            return total

        total_length = 0.0
        for layer in layers:
            total_length += path_length(layer.perimeters)
            total_length += path_length(layer.infill)
            total_length += path_length(layer.top_bottom)
            total_length += path_length(layer.support)
            total_length += path_length(layer.brim)

        # Volume of extruded plastic
        volume_mm3 = total_length * nozzle_area  # mm³

        # Weight: density of PLA = 1.24 g/cm³ = 0.00124 g/mm³
        density_g_per_mm3 = 1.24 / 1000.0
        weight_g = volume_mm3 * density_g_per_mm3

        return weight_g
