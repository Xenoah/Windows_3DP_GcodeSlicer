"""
Universal file loader for 3D model formats.

Supported formats:
  - STL (always available via trimesh)
  - FBX (via trimesh with optional assimp backend)
  - STEP/STP (via pythonocc-core or cadquery, optional)
  - OBJ, PLY, 3MF etc. (via trimesh)
"""

import os
import logging
from typing import Optional

import trimesh
import numpy as np

log = logging.getLogger(__name__)


def load_file(filepath: str) -> trimesh.Trimesh:
    """
    Load a 3D mesh file and return a trimesh.Trimesh object.

    Supports: STL, OBJ, PLY, 3MF, FBX, STEP/STP and any format
    supported by trimesh.

    Raises:
        FileNotFoundError: if file does not exist
        ImportError: if required optional library is missing (STEP files)
        ValueError: if file cannot be loaded as a mesh
    """
    if not os.path.isfile(filepath):
        raise FileNotFoundError(f"File not found: {filepath}")

    ext = os.path.splitext(filepath)[1].lower()

    if ext in ('.step', '.stp'):
        return _load_step(filepath)
    elif ext == '.fbx':
        return _load_fbx(filepath)
    else:
        return _load_generic(filepath)


def _load_generic(filepath: str) -> trimesh.Trimesh:
    """Load using trimesh's generic loader."""
    try:
        result = trimesh.load(filepath, force='mesh', process=True)
        return _ensure_trimesh(result, filepath)
    except Exception as e:
        log.error(f"Failed to load {filepath}: {e}")
        raise ValueError(f"Cannot load mesh from {filepath}: {e}")


def _load_fbx(filepath: str) -> trimesh.Trimesh:
    """Load FBX file (requires trimesh with assimp or pyassimp)."""
    try:
        result = trimesh.load(filepath, force='mesh', process=True)
        return _ensure_trimesh(result, filepath)
    except Exception as e:
        # Try without assimp backend
        try:
            result = trimesh.load(filepath, force='mesh')
            return _ensure_trimesh(result, filepath)
        except Exception as e2:
            raise ValueError(
                f"Cannot load FBX file. Make sure pyassimp or assimp is installed.\n"
                f"Install with: pip install pyassimp\n"
                f"Error: {e2}"
            )


def _load_step(filepath: str) -> trimesh.Trimesh:
    """
    Load a STEP file using pythonocc-core or cadquery.

    Falls back gracefully with a helpful error message.
    """
    # Try pythonocc-core
    try:
        return _load_step_occ(filepath)
    except ImportError:
        pass
    except Exception as e:
        log.warning(f"pythonocc STEP load failed: {e}")

    # Try cadquery
    try:
        return _load_step_cadquery(filepath)
    except ImportError:
        pass
    except Exception as e:
        log.warning(f"cadquery STEP load failed: {e}")

    # Try trimesh directly (some builds support STEP via OpenCASCADE)
    try:
        result = trimesh.load(filepath, force='mesh')
        return _ensure_trimesh(result, filepath)
    except Exception:
        pass

    raise ImportError(
        "STEP file loading requires pythonocc-core or cadquery.\n"
        "Install with:\n"
        "  pip install cadquery\n"
        "Or:\n"
        "  conda install -c conda-forge pythonocc-core"
    )


def _load_step_occ(filepath: str) -> trimesh.Trimesh:
    """Load STEP using pythonocc-core."""
    from OCC.Core.BRep import BRep_Builder
    from OCC.Core.BRepMesh import BRepMesh_IncrementalMesh
    from OCC.Core.STEPControl import STEPControl_Reader
    from OCC.Core.TopAbs import TopAbs_FACE
    from OCC.Core.TopExp import TopExp_Explorer
    from OCC.Core.BRep import BRep_Tool
    from OCC.Core.TopLoc import TopLoc_Location
    import OCC.Core.BRep as BRep

    reader = STEPControl_Reader()
    status = reader.ReadFile(filepath)
    if status != 1:  # 1 = Done
        raise ValueError(f"pythonocc failed to read STEP file: {filepath}")

    reader.TransferRoots()
    shape = reader.OneShape()

    # Tessellate
    mesh = BRepMesh_IncrementalMesh(shape, 0.1, False, 0.5, True)
    mesh.Perform()

    # Extract vertices and triangles
    vertices = []
    triangles = []
    offset = 0

    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    while explorer.More():
        face = explorer.Current()
        location = TopLoc_Location()
        triangulation = BRep_Tool.Triangulation_s(face, location)

        if triangulation is not None:
            n_nodes = triangulation.NbNodes()
            n_tris = triangulation.NbTriangles()

            for i in range(1, n_nodes + 1):
                node = triangulation.Node(i)
                pt = location.IsIdentity() and node or node.Transformed(location.Transformation())
                vertices.append([pt.X(), pt.Y(), pt.Z()])

            for i in range(1, n_tris + 1):
                tri = triangulation.Triangle(i)
                n1, n2, n3 = tri.Get()
                triangles.append([n1 - 1 + offset, n2 - 1 + offset, n3 - 1 + offset])

            offset += n_nodes

        explorer.Next()

    if not vertices:
        raise ValueError("No geometry extracted from STEP file")

    v_arr = np.array(vertices, dtype=np.float64)
    f_arr = np.array(triangles, dtype=np.int64)
    return trimesh.Trimesh(vertices=v_arr, faces=f_arr, process=True)


def _load_step_cadquery(filepath: str) -> trimesh.Trimesh:
    """Load STEP using cadquery."""
    import cadquery as cq
    shape = cq.importers.importStep(filepath)
    # Export to STL in memory and reload
    import tempfile
    with tempfile.NamedTemporaryFile(suffix='.stl', delete=False) as tmp:
        tmp_path = tmp.name
    try:
        cq.exporters.export(shape, tmp_path)
        return _load_generic(tmp_path)
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


def _ensure_trimesh(result, filepath: str) -> trimesh.Trimesh:
    """
    Ensure the result is a trimesh.Trimesh.
    If it's a Scene, extract the largest mesh.
    """
    if isinstance(result, trimesh.Trimesh):
        if len(result.faces) == 0:
            raise ValueError(f"Loaded mesh has no faces: {filepath}")
        return result

    if isinstance(result, trimesh.Scene):
        meshes = []
        for geom in result.geometry.values():
            if isinstance(geom, trimesh.Trimesh) and len(geom.faces) > 0:
                meshes.append(geom)
        if not meshes:
            raise ValueError(f"Scene from {filepath} contains no valid meshes")
        # Return largest mesh by face count
        return max(meshes, key=lambda m: len(m.faces))

    # Try to concatenate if it's a list
    if hasattr(result, '__iter__'):
        meshes = [m for m in result if isinstance(m, trimesh.Trimesh)]
        if meshes:
            return trimesh.util.concatenate(meshes)

    raise ValueError(f"Cannot convert loaded object to Trimesh: {type(result)}")


def get_file_info(mesh: trimesh.Trimesh) -> dict:
    """Return a dict with basic mesh statistics."""
    return {
        'vertices': len(mesh.vertices),
        'faces': len(mesh.faces),
        'volume_mm3': float(mesh.volume) if mesh.is_watertight else None,
        'surface_area_mm2': float(mesh.area),
        'bounds': mesh.bounds.tolist(),
        'extents': mesh.extents.tolist(),
        'is_watertight': bool(mesh.is_watertight),
    }
