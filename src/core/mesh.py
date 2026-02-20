"""
Mesh container class wrapping trimesh.Trimesh with utility methods.
"""

import numpy as np
import trimesh


class Mesh:
    """
    Container for a loaded 3D mesh, wrapping trimesh.Trimesh.
    Provides convenient access to geometry data and transform utilities.
    """

    def __init__(self, tri_mesh: trimesh.Trimesh, name: str = "mesh"):
        if not isinstance(tri_mesh, trimesh.Trimesh):
            # Handle Scene objects by extracting the largest mesh
            if isinstance(tri_mesh, trimesh.Scene):
                meshes = list(tri_mesh.geometry.values())
                if not meshes:
                    raise ValueError("Scene contains no geometry")
                tri_mesh = max(meshes, key=lambda m: m.volume if hasattr(m, 'volume') else 0)
            else:
                raise TypeError(f"Expected trimesh.Trimesh, got {type(tri_mesh)}")

        self._mesh = tri_mesh
        self.name = name

    # ------------------------------------------------------------------
    # Raw geometry accessors
    # ------------------------------------------------------------------

    @property
    def vertices(self) -> np.ndarray:
        """Return (N, 3) float32 vertex array."""
        return np.array(self._mesh.vertices, dtype=np.float32)

    @property
    def faces(self) -> np.ndarray:
        """Return (M, 3) uint32 face index array."""
        return np.array(self._mesh.faces, dtype=np.uint32)

    @property
    def normals(self) -> np.ndarray:
        """Return (M, 3) float32 face normal array."""
        return np.array(self._mesh.face_normals, dtype=np.float32)

    @property
    def vertex_normals(self) -> np.ndarray:
        """Return (N, 3) float32 vertex normal array."""
        return np.array(self._mesh.vertex_normals, dtype=np.float32)

    # ------------------------------------------------------------------
    # Bounding information
    # ------------------------------------------------------------------

    @property
    def bounds(self) -> np.ndarray:
        """Return (2, 3) array: [[xmin,ymin,zmin],[xmax,ymax,zmax]]."""
        return np.array(self._mesh.bounds, dtype=np.float64)

    @property
    def extents(self) -> np.ndarray:
        """Return (3,) array with x/y/z size."""
        return np.array(self._mesh.extents, dtype=np.float64)

    @property
    def center_mass(self) -> np.ndarray:
        """Return (3,) center of mass."""
        try:
            return np.array(self._mesh.center_mass, dtype=np.float64)
        except Exception:
            return np.array(self._mesh.centroid, dtype=np.float64)

    @property
    def centroid(self) -> np.ndarray:
        """Return (3,) geometric centroid."""
        return np.array(self._mesh.centroid, dtype=np.float64)

    # ------------------------------------------------------------------
    # Mesh properties
    # ------------------------------------------------------------------

    @property
    def volume(self) -> float:
        """Volume in mm³ (valid only for watertight meshes)."""
        try:
            return float(self._mesh.volume)
        except Exception:
            return 0.0

    @property
    def surface_area(self) -> float:
        """Surface area in mm²."""
        try:
            return float(self._mesh.area)
        except Exception:
            return 0.0

    @property
    def is_watertight(self) -> bool:
        return bool(self._mesh.is_watertight)

    @property
    def trimesh(self) -> trimesh.Trimesh:
        """Access the underlying trimesh object."""
        return self._mesh

    # ------------------------------------------------------------------
    # Transforms
    # ------------------------------------------------------------------

    def place_on_bed(self):
        """Translate mesh so its lowest point sits at z=0."""
        z_min = self.bounds[0, 2]
        self._mesh.apply_translation([0.0, 0.0, -z_min])

    def translate(self, offset):
        """
        Translate mesh by offset (3-element sequence).
        """
        offset = np.array(offset, dtype=np.float64)
        self._mesh.apply_translation(offset)

    def scale(self, factor, center=None):
        """
        Scale mesh by scalar factor (uniform) or (3,) array (non-uniform).
        Scales around `center` (defaults to mesh centroid).
        """
        if center is None:
            center = self.centroid
        center = np.array(center, dtype=np.float64)
        if np.isscalar(factor):
            matrix = trimesh.transformations.scale_matrix(factor, origin=center)
        else:
            factor = np.array(factor, dtype=np.float64)
            matrix = np.eye(4)
            matrix[0, 0] = factor[0]
            matrix[1, 1] = factor[1]
            matrix[2, 2] = factor[2]
            # Apply around center
            t1 = np.eye(4)
            t1[:3, 3] = -center
            t2 = np.eye(4)
            t2[:3, 3] = center
            matrix = t2 @ matrix @ t1
        self._mesh.apply_transform(matrix)

    def rotate(self, axis, angle_deg, center=None):
        """
        Rotate mesh around `axis` (3-element) by `angle_deg` degrees.
        Rotates around `center` (defaults to mesh centroid).
        """
        axis = np.array(axis, dtype=np.float64)
        axis = axis / np.linalg.norm(axis)
        angle_rad = np.radians(angle_deg)
        if center is None:
            center = self.centroid
        center = np.array(center, dtype=np.float64)
        matrix = trimesh.transformations.rotation_matrix(angle_rad, axis, point=center)
        self._mesh.apply_transform(matrix)

    def center_on_bed(self, bed_size=(220, 220)):
        """Center mesh on the build plate (x/y) and place on bed (z=0)."""
        cx, cy = bed_size[0] / 2.0, bed_size[1] / 2.0
        centroid = self.centroid
        self._mesh.apply_translation([cx - centroid[0], cy - centroid[1], 0.0])
        self.place_on_bed()

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def copy(self) -> "Mesh":
        """Return a deep copy of this mesh."""
        return Mesh(self._mesh.copy(), name=self.name)

    def __repr__(self):
        return (
            f"Mesh(name={self.name!r}, vertices={len(self.vertices)}, "
            f"faces={len(self.faces)}, watertight={self.is_watertight})"
        )
