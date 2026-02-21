"""
3D OpenGL viewport for the slicer application.

Uses QOpenGLWidget with OpenGL 3.3 core profile.
Renders:
  - Build plate grid
  - 3D mesh with Blinn-Phong shading (solid + transparent modes)
  - Sliced layer paths (as colored GL_LINES)

View modes:
  MODEL  - show only the 3D mesh
  LAYERS - show only sliced layer paths
  BOTH   - show transparent mesh + layer paths
"""

import math
import numpy as np
from enum import Enum
from typing import List, Optional

from PyQt6.QtWidgets import QSizePolicy
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtCore import Qt, QPoint, pyqtSignal
from PyQt6.QtGui import QSurfaceFormat

try:
    from OpenGL.GL import (
        glGenVertexArrays, glBindVertexArray, glGenBuffers, glBindBuffer,
        glBufferData, glVertexAttribPointer, glEnableVertexAttribArray,
        glDrawArrays, glDrawElements, glEnable, glDisable, glDepthFunc,
        glClearColor, glClear, glViewport, glLineWidth,
        glUseProgram, glUniform3fv, glUniform1f, glUniformMatrix4fv,
        glUniformMatrix3fv,
        glGetUniformLocation, glDeleteBuffers, glDeleteVertexArrays,
        glCreateShader, glShaderSource, glCompileShader, glGetShaderiv,
        glGetShaderInfoLog, glCreateProgram, glAttachShader, glLinkProgram,
        glGetProgramiv, glGetProgramInfoLog, glDeleteShader, glDeleteProgram,
        glUniform3f, glUniform1i,
        GL_VERTEX_SHADER, GL_FRAGMENT_SHADER, GL_ARRAY_BUFFER,
        GL_ELEMENT_ARRAY_BUFFER, GL_STATIC_DRAW, GL_FLOAT, GL_UNSIGNED_INT,
        GL_TRIANGLES, GL_LINES, GL_DEPTH_TEST, GL_LESS,
        GL_COLOR_BUFFER_BIT, GL_DEPTH_BUFFER_BIT, GL_TRUE, GL_FALSE,
        GL_COMPILE_STATUS, GL_LINK_STATUS,
        GL_BLEND, GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA,
        glBlendFunc, glDepthMask,
        GL_BACK, glCullFace, GL_CULL_FACE,
    )
    OPENGL_OK = True
except ImportError as e:
    print(f"[Viewport] OpenGL import error: {e}")
    OPENGL_OK = False


# ---------------------------------------------------------------------------
# View mode
# ---------------------------------------------------------------------------

class ViewMode(Enum):
    MODEL  = "model"    # 3D mesh only
    LAYERS = "layers"   # sliced layer paths only
    BOTH   = "both"     # transparent mesh + layer paths


# ---------------------------------------------------------------------------
# Shader source
# ---------------------------------------------------------------------------

# Mesh: Blinn-Phong shading + optional transparency
MESH_VERT = """
#version 330 core
layout(location = 0) in vec3 aPos;
layout(location = 1) in vec3 aNormal;
uniform mat4 MVP;
uniform mat4 model;
uniform mat3 normalMat;
out vec3 FragPos;
out vec3 Normal;
void main() {
    gl_Position = MVP * vec4(aPos, 1.0);
    FragPos     = vec3(model * vec4(aPos, 1.0));
    Normal      = normalize(normalMat * aNormal);
}
"""

MESH_FRAG = """
#version 330 core
in  vec3 FragPos;
in  vec3 Normal;
uniform vec3  lightDir;   // direction TO light (world space)
uniform vec3  viewPos;    // camera position
uniform vec3  objectColor;
uniform float alpha;
out vec4 FragColor;

void main() {
    vec3 norm    = normalize(Normal);
    vec3 lightN  = normalize(lightDir);
    vec3 viewN   = normalize(viewPos - FragPos);
    vec3 halfDir = normalize(lightN + viewN);

    float ambient  = 0.25;
    float diffuse  = max(dot(norm, lightN), 0.0) * 0.65;
    float specular = pow(max(dot(norm, halfDir), 0.0), 32.0) * 0.25;

    vec3 color = (ambient + diffuse + specular) * objectColor;
    FragColor  = vec4(color, alpha);
}
"""

# Lines: solid color
LINE_VERT = """
#version 330 core
layout(location = 0) in vec3 aPos;
uniform mat4 MVP;
void main() {
    gl_Position = MVP * vec4(aPos, 1.0);
}
"""

LINE_FRAG = """
#version 330 core
uniform vec3 lineColor;
out vec4 FragColor;
void main() {
    FragColor = vec4(lineColor, 1.0);
}
"""


# ---------------------------------------------------------------------------
# Math helpers
# ---------------------------------------------------------------------------

def _perspective(fov_deg: float, aspect: float, near: float, far: float) -> np.ndarray:
    f = 1.0 / math.tan(math.radians(fov_deg) / 2.0)
    nf = 1.0 / (near - far)
    m = np.zeros((4, 4), dtype=np.float32)
    m[0, 0] = f / aspect
    m[1, 1] = f
    m[2, 2] = (far + near) * nf
    m[2, 3] = -1.0
    m[3, 2] = 2.0 * far * near * nf
    return m


def _look_at(eye: np.ndarray, center: np.ndarray, up: np.ndarray) -> np.ndarray:
    f = center - eye;  f /= np.linalg.norm(f)
    s = np.cross(f, up); s /= np.linalg.norm(s)
    u = np.cross(s, f)
    m = np.eye(4, dtype=np.float32)
    m[0, :3] = s;  m[0, 3] = -np.dot(s, eye)
    m[1, :3] = u;  m[1, 3] = -np.dot(u, eye)
    m[2, :3] = -f; m[2, 3] =  np.dot(f, eye)
    return m


# ---------------------------------------------------------------------------
# Shader helpers
# ---------------------------------------------------------------------------

def _compile_shader(src: str, shader_type) -> int:
    sh = glCreateShader(shader_type)
    glShaderSource(sh, src)
    glCompileShader(sh)
    if not glGetShaderiv(sh, GL_COMPILE_STATUS):
        log = glGetShaderInfoLog(sh).decode()
        glDeleteShader(sh)
        raise RuntimeError(f"Shader compile error:\n{log}")
    return sh


def _link_program(vert_src: str, frag_src: str) -> int:
    v = _compile_shader(vert_src, GL_VERTEX_SHADER)
    f = _compile_shader(frag_src, GL_FRAGMENT_SHADER)
    prog = glCreateProgram()
    glAttachShader(prog, v)
    glAttachShader(prog, f)
    glLinkProgram(prog)
    glDeleteShader(v)
    glDeleteShader(f)
    if not glGetProgramiv(prog, GL_LINK_STATUS):
        log = glGetProgramInfoLog(prog).decode()
        glDeleteProgram(prog)
        raise RuntimeError(f"Program link error:\n{log}")
    return prog


# ---------------------------------------------------------------------------
# Viewport3D
# ---------------------------------------------------------------------------

class Viewport3D(QOpenGLWidget):
    """OpenGL 3D viewport: mesh preview + layer path preview."""

    layer_changed = pyqtSignal(int)

    # Layer type display colors  (perimeter, infill, top/bottom, support, brim)
    _TYPE_COLORS = {
        'perimeter':  np.array([1.00, 0.55, 0.10], dtype=np.float32),  # orange
        'infill':     np.array([0.20, 0.80, 0.20], dtype=np.float32),  # green
        'top_bottom': np.array([0.20, 0.80, 1.00], dtype=np.float32),  # cyan
        'support':    np.array([0.90, 0.90, 0.10], dtype=np.float32),  # yellow
        'brim':       np.array([1.00, 0.20, 0.60], dtype=np.float32),  # pink
    }

    def __init__(self, parent=None):
        # NOTE: QSurfaceFormat.setDefaultFormat() is called in main.py
        # BEFORE QApplication, which is required for it to take effect.
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(400, 300)
        self.setMouseTracking(True)

        # --- Camera ---
        self._azimuth   = 45.0    # degrees
        self._elevation = 30.0    # degrees
        self._distance  = 300.0   # mm
        self._target    = np.array([110.0, 110.0, 10.0], dtype=np.float32)

        # --- Mouse ---
        self._last_mouse   = QPoint()
        self._mouse_button = None

        # --- Build plate ---
        self._bed_x = 220.0
        self._bed_y = 220.0

        # --- Mesh GPU data ---
        self._mesh_vao         = None
        self._mesh_vbo         = None
        self._mesh_nbo         = None
        self._mesh_ebo         = None
        self._mesh_index_count = 0
        self._mesh_loaded      = False
        self._mesh_color       = np.array([0.30, 0.65, 1.00], dtype=np.float32)
        self._pending_trimesh  = None   # stored for deferred GPU upload

        # --- Layer GPU data ---
        # Each entry: (vao, vbo, vert_count, color_rgb, z_value, type_name)
        self._layer_draws: list = []
        self._layer_z_sorted: list = []   # sorted unique z values
        self._layers_loaded   = False
        self._preview_layer   = -1        # index into _layer_z_sorted

        # --- Grid GPU data ---
        self._grid_vao = None
        self._grid_vbo = None
        self._grid_vc  = 0
        self._show_grid = True

        # --- Shader programs ---
        self._mesh_prog = None
        self._line_prog = None

        # --- State ---
        self._gl_ready  = False
        self._view_mode = ViewMode.MODEL

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def set_view_mode(self, mode: ViewMode):
        """Switch between MODEL / LAYERS / BOTH display modes."""
        self._view_mode = mode
        self.update()

    def get_view_mode(self) -> ViewMode:
        return self._view_mode

    def load_mesh(self, trimesh_mesh):
        """
        Upload mesh geometry to the GPU.
        Safe to call at any time – deferred until GL is initialized.
        """
        # Fit camera regardless of GL state
        try:
            bounds = trimesh_mesh.bounds
            center = ((bounds[0] + bounds[1]) / 2).astype(np.float32)
            self._target   = center
            self._distance = float(np.max(bounds[1] - bounds[0]) * 2.2)
        except Exception:
            pass

        self._pending_trimesh = trimesh_mesh
        if self._gl_ready:
            self.makeCurrent()
            self._flush_pending_mesh()
            self.doneCurrent()
        self.update()

    def _flush_pending_mesh(self):
        """Upload _pending_trimesh to GPU. Must be called with GL context current."""
        if self._pending_trimesh is None:
            return
        tri = self._pending_trimesh
        self._pending_trimesh = None
        self._cleanup_mesh()
        try:
            verts   = np.asarray(tri.vertices,      dtype=np.float32)
            normals = np.asarray(tri.vertex_normals, dtype=np.float32)
            faces   = np.asarray(tri.faces,          dtype=np.uint32)

            self._mesh_vao = glGenVertexArrays(1)
            glBindVertexArray(self._mesh_vao)

            self._mesh_vbo = glGenBuffers(1)
            glBindBuffer(GL_ARRAY_BUFFER, self._mesh_vbo)
            glBufferData(GL_ARRAY_BUFFER, verts.nbytes, verts, GL_STATIC_DRAW)
            glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 0, None)
            glEnableVertexAttribArray(0)

            self._mesh_nbo = glGenBuffers(1)
            glBindBuffer(GL_ARRAY_BUFFER, self._mesh_nbo)
            glBufferData(GL_ARRAY_BUFFER, normals.nbytes, normals, GL_STATIC_DRAW)
            glVertexAttribPointer(1, 3, GL_FLOAT, GL_FALSE, 0, None)
            glEnableVertexAttribArray(1)

            self._mesh_ebo = glGenBuffers(1)
            glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, self._mesh_ebo)
            glBufferData(GL_ELEMENT_ARRAY_BUFFER, faces.nbytes, faces, GL_STATIC_DRAW)
            self._mesh_index_count = faces.size

            glBindVertexArray(0)
            self._mesh_loaded = True
            print(f"[Viewport] mesh uploaded: {len(verts)} verts, {len(faces)} faces")

        except Exception as e:
            print(f"[Viewport] _flush_pending_mesh error: {e}")
            import traceback; traceback.print_exc()

    def load_layer_paths(self, layers: list):
        """
        Upload sliced layer paths to GPU.
        Each layer has .perimeters / .infill / .top_bottom / .support / .brim
        (lists of numpy Nx2 coordinate arrays).
        """
        self.makeCurrent()
        if not self._gl_ready:
            self.doneCurrent()
            return
        self._cleanup_layers()
        if not layers:
            self.doneCurrent()
            return
        try:
            z_set = set()
            for layer in layers:
                z = float(layer.z)
                z_set.add(z)
                for type_name, paths in [
                    ('perimeter',  layer.perimeters),
                    ('infill',     layer.infill),
                    ('top_bottom', layer.top_bottom),
                    ('support',    getattr(layer, 'support', [])),
                    ('brim',       getattr(layer, 'brim',    [])),
                ]:
                    self._upload_paths(paths, z, type_name)

            self._layer_z_sorted = sorted(z_set)
            self._layers_loaded  = True
            self._preview_layer  = len(self._layer_z_sorted) - 1

        except Exception as e:
            print(f"[Viewport] load_layer_paths error: {e}")
            import traceback; traceback.print_exc()
        self.doneCurrent()
        self.update()

    def _upload_paths(self, paths, z: float, type_name: str):
        """Convert a list of Nx2 paths to line-segment GPU data and upload."""
        if not paths:
            return
        segments = []
        for path in paths:
            arr = np.asarray(path, dtype=np.float32)
            if arr.ndim != 2 or arr.shape[1] < 2 or len(arr) < 2:
                continue
            # Generate line segments (pairs: p0-p1, p1-p2, ...)
            for i in range(len(arr) - 1):
                x0, y0 = float(arr[i,   0]), float(arr[i,   1])
                x1, y1 = float(arr[i+1, 0]), float(arr[i+1, 1])
                segments.append([x0, y0, z])
                segments.append([x1, y1, z])
        if not segments:
            return

        vdata = np.array(segments, dtype=np.float32)
        vao = glGenVertexArrays(1)
        glBindVertexArray(vao)
        vbo = glGenBuffers(1)
        glBindBuffer(GL_ARRAY_BUFFER, vbo)
        glBufferData(GL_ARRAY_BUFFER, vdata.nbytes, vdata, GL_STATIC_DRAW)
        glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 0, None)
        glEnableVertexAttribArray(0)
        glBindVertexArray(0)

        color = self._TYPE_COLORS.get(type_name, np.array([1.0, 1.0, 1.0], dtype=np.float32))
        self._layer_draws.append((vao, vbo, len(vdata), color.copy(), z, type_name))

    def set_layer_preview(self, layer_index: int):
        """Show layers up to and including layer_index (0-based)."""
        self._preview_layer = layer_index
        self.update()

    def reset_camera(self):
        self._azimuth   = 45.0
        self._elevation = 30.0
        self._distance  = max(self._bed_x, self._bed_y) * 2.0
        self._target    = np.array([self._bed_x/2, self._bed_y/2, 10.0], dtype=np.float32)
        self.update()

    def set_bed_size(self, x: float, y: float):
        self._bed_x = float(x)
        self._bed_y = float(y)
        self._target = np.array([x/2, y/2, 10.0], dtype=np.float32)
        if self._gl_ready:
            self.makeCurrent()
            self._build_grid()
            self.doneCurrent()
        self.update()

    def set_show_grid(self, visible: bool):
        self._show_grid = visible
        self.update()

    def clear_layers(self):
        if self._gl_ready:
            self.makeCurrent()
            self._cleanup_layers()
            self.doneCurrent()
        self.update()

    def clear_mesh(self):
        if self._gl_ready:
            self.makeCurrent()
            self._cleanup_mesh()
            self.doneCurrent()
        self.update()

    # -----------------------------------------------------------------------
    # OpenGL lifecycle
    # -----------------------------------------------------------------------

    def initializeGL(self):
        if not OPENGL_OK:
            return
        try:
            glClearColor(0.10, 0.10, 0.12, 1.0)
            glEnable(GL_DEPTH_TEST)
            glDepthFunc(GL_LESS)
            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            glEnable(GL_CULL_FACE)
            glCullFace(GL_BACK)

            self._mesh_prog = _link_program(MESH_VERT, MESH_FRAG)
            self._line_prog = _link_program(LINE_VERT, LINE_FRAG)
            self._build_grid()
            self._gl_ready = True
        except Exception as e:
            print(f"[Viewport] initializeGL error: {e}")
            import traceback; traceback.print_exc()

    def resizeGL(self, w: int, h: int):
        glViewport(0, 0, w, max(h, 1))

    def paintGL(self):
        if not OPENGL_OK or not self._gl_ready:
            return
        # Upload any pending mesh (deferred from before GL was ready)
        if self._pending_trimesh is not None:
            self._flush_pending_mesh()
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        w, h = self.width(), self.height()
        if h == 0:
            return

        mvp, model_mat, normal_mat, eye_pos = self._compute_matrices(w, h)

        # Grid (always)
        if self._show_grid:
            self._draw_grid(mvp)

        mode = self._view_mode

        if mode == ViewMode.MODEL:
            if self._mesh_loaded:
                self._draw_mesh(mvp, model_mat, normal_mat, eye_pos, alpha=1.0)

        elif mode in (ViewMode.LAYERS, ViewMode.BOTH):
            # Always show mesh as ghost background so model is never lost from view
            if self._mesh_loaded:
                alpha = 0.30 if self._layers_loaded else 0.85
                self._draw_mesh(mvp, model_mat, normal_mat, eye_pos, alpha=alpha)
            # Layer paths on top
            if self._layers_loaded:
                self._draw_layers(mvp)

    # -----------------------------------------------------------------------
    # Rendering helpers
    # -----------------------------------------------------------------------

    def _compute_matrices(self, w: int, h: int):
        az = math.radians(self._azimuth)
        el = math.radians(self._elevation)

        eye = np.array([
            self._target[0] + self._distance * math.cos(el) * math.sin(az),
            self._target[1] + self._distance * math.cos(el) * math.cos(az),
            self._target[2] + self._distance * math.sin(el),
        ], dtype=np.float32)

        view   = _look_at(eye, self._target, np.array([0, 0, 1], dtype=np.float32))
        proj   = _perspective(45.0, w / h, 0.1, 10000.0)
        model  = np.eye(4, dtype=np.float32)
        mvp    = proj @ view @ model

        # Normal matrix: inverse-transpose of upper-left 3x3 of model
        normal_mat = np.linalg.inv(model[:3, :3]).T.astype(np.float32)

        return mvp, model, normal_mat, eye

    def _draw_mesh(self, mvp, model_mat, normal_mat, eye_pos, alpha: float = 1.0):
        if not self._mesh_loaded or self._mesh_vao is None:
            return
        try:
            glUseProgram(self._mesh_prog)

            glUniformMatrix4fv(glGetUniformLocation(self._mesh_prog, "MVP"),
                               1, GL_TRUE, mvp)
            glUniformMatrix4fv(glGetUniformLocation(self._mesh_prog, "model"),
                               1, GL_TRUE, model_mat)
            # *** FIX: normalMat is mat3 → use glUniformMatrix3fv ***
            glUniformMatrix3fv(glGetUniformLocation(self._mesh_prog, "normalMat"),
                               1, GL_TRUE, normal_mat)

            # Light direction (world space, toward the light)
            light = np.array([1.0, 0.8, 2.0], dtype=np.float32)
            light /= np.linalg.norm(light)
            glUniform3fv(glGetUniformLocation(self._mesh_prog, "lightDir"),  1, light)
            glUniform3fv(glGetUniformLocation(self._mesh_prog, "viewPos"),   1, eye_pos)
            glUniform3fv(glGetUniformLocation(self._mesh_prog, "objectColor"), 1, self._mesh_color)
            glUniform1f(glGetUniformLocation(self._mesh_prog, "alpha"), alpha)

            if alpha < 1.0:
                glDisable(GL_CULL_FACE)  # show both sides when transparent
                glDepthMask(GL_FALSE)
            else:
                glEnable(GL_CULL_FACE)
                glDepthMask(GL_TRUE)

            glBindVertexArray(self._mesh_vao)
            glDrawElements(GL_TRIANGLES, self._mesh_index_count, GL_UNSIGNED_INT, None)
            glBindVertexArray(0)

            # Restore state
            glDepthMask(GL_TRUE)
            glEnable(GL_CULL_FACE)

        except Exception as e:
            print(f"[Viewport] _draw_mesh error: {e}")

    def _draw_grid(self, mvp):
        if self._grid_vao is None:
            return
        try:
            glUseProgram(self._line_prog)
            glUniformMatrix4fv(glGetUniformLocation(self._line_prog, "MVP"), 1, GL_TRUE, mvp)

            # Main grid (dark)
            glUniform3fv(glGetUniformLocation(self._line_prog, "lineColor"), 1,
                         np.array([0.30, 0.30, 0.30], dtype=np.float32))
            glBindVertexArray(self._grid_vao)
            glDrawArrays(GL_LINES, 0, self._grid_vc)
            glBindVertexArray(0)
        except Exception as e:
            print(f"[Viewport] _draw_grid error: {e}")

    def _draw_layers(self, mvp):
        if not self._layer_draws:
            return
        try:
            glUseProgram(self._line_prog)
            glUniformMatrix4fv(glGetUniformLocation(self._line_prog, "MVP"), 1, GL_TRUE, mvp)
            loc_color = glGetUniformLocation(self._line_prog, "lineColor")

            # Determine max z to display
            max_z = float('inf')
            if self._preview_layer >= 0 and self._layer_z_sorted:
                idx = min(self._preview_layer, len(self._layer_z_sorted) - 1)
                max_z = self._layer_z_sorted[idx]

            # Current layer highlight z
            cur_z = self._layer_z_sorted[idx] if self._layer_z_sorted else None

            glLineWidth(1.5)
            for vao, vbo, vc, color, z, type_name in self._layer_draws:
                if z > max_z + 1e-4:
                    continue
                # Highlight the current (top-most visible) layer
                if cur_z is not None and abs(z - cur_z) < 1e-4:
                    c = np.minimum(color * 1.5, 1.0)
                else:
                    c = color * 0.7  # slightly dimmer for lower layers
                glUniform3fv(loc_color, 1, c.astype(np.float32))
                glBindVertexArray(vao)
                glDrawArrays(GL_LINES, 0, vc)
                glBindVertexArray(0)
            glLineWidth(1.0)
        except Exception as e:
            print(f"[Viewport] _draw_layers error: {e}")

    def _build_grid(self):
        """Build plate grid geometry."""
        if not self._gl_ready:
            return
        if self._grid_vao is not None:
            try:
                glDeleteVertexArrays(1, [self._grid_vao])
                glDeleteBuffers(1, [self._grid_vbo])
            except Exception:
                pass

        try:
            verts = []
            bx, by = self._bed_x, self._bed_y
            step = 10.0

            # Interior grid lines
            y = step
            while y < by - 1e-4:
                verts += [[0.0, y, 0.0], [bx, y, 0.0]]
                y += step
            x = step
            while x < bx - 1e-4:
                verts += [[x, 0.0, 0.0], [x, by, 0.0]]
                x += step

            # Axis lines (slightly brighter, added separately via same VBO)
            verts += [
                [0, 0, 0], [bx, 0, 0],   # front edge
                [0, 0, 0], [0, by, 0],   # left edge
                [bx, 0, 0], [bx, by, 0], # right edge
                [0, by, 0], [bx, by, 0], # back edge
            ]

            vdata = np.array(verts, dtype=np.float32)
            self._grid_vao = glGenVertexArrays(1)
            glBindVertexArray(self._grid_vao)
            self._grid_vbo = glGenBuffers(1)
            glBindBuffer(GL_ARRAY_BUFFER, self._grid_vbo)
            glBufferData(GL_ARRAY_BUFFER, vdata.nbytes, vdata, GL_STATIC_DRAW)
            glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 0, None)
            glEnableVertexAttribArray(0)
            glBindVertexArray(0)
            self._grid_vc = len(vdata)
        except Exception as e:
            print(f"[Viewport] _build_grid error: {e}")

    # -----------------------------------------------------------------------
    # Mouse / keyboard
    # -----------------------------------------------------------------------

    def mousePressEvent(self, event):
        self._last_mouse   = event.pos()
        self._mouse_button = event.button()

    def mouseMoveEvent(self, event):
        if self._mouse_button is None:
            return
        dx = event.pos().x() - self._last_mouse.x()
        dy = event.pos().y() - self._last_mouse.y()
        self._last_mouse = event.pos()

        if self._mouse_button == Qt.MouseButton.LeftButton:
            self._azimuth   += dx * 0.5
            self._elevation  = max(-89.0, min(89.0, self._elevation - dy * 0.5))
            self.update()

        elif self._mouse_button == Qt.MouseButton.MiddleButton:
            az = math.radians(self._azimuth)
            el = math.radians(self._elevation)
            right = np.array([ math.cos(az), -math.sin(az), 0.0], dtype=np.float32)
            up    = np.array([-math.sin(el)*math.sin(az),
                               -math.sin(el)*math.cos(az),
                                math.cos(el)], dtype=np.float32)
            scale = self._distance * 0.0012
            self._target -= (right * dx - up * dy) * scale
            self.update()

    def mouseReleaseEvent(self, event):
        self._mouse_button = None

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        factor = 0.88 if delta > 0 else 1.14
        self._distance = max(5.0, min(8000.0, self._distance * factor))
        self.update()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_R:
            self.reset_camera()
        super().keyPressEvent(event)

    # -----------------------------------------------------------------------
    # Cleanup
    # -----------------------------------------------------------------------

    def _cleanup_mesh(self):
        for buf in [self._mesh_vao, self._mesh_vbo, self._mesh_nbo, self._mesh_ebo]:
            if buf is not None:
                try:
                    if buf == self._mesh_vao:
                        glDeleteVertexArrays(1, [buf])
                    else:
                        glDeleteBuffers(1, [buf])
                except Exception:
                    pass
        self._mesh_vao = self._mesh_vbo = self._mesh_nbo = self._mesh_ebo = None
        self._mesh_index_count = 0
        self._mesh_loaded = False

    def _cleanup_layers(self):
        for vao, vbo, *_ in self._layer_draws:
            try: glDeleteVertexArrays(1, [vao])
            except Exception: pass
            try: glDeleteBuffers(1, [vbo])
            except Exception: pass
        self._layer_draws      = []
        self._layer_z_sorted   = []
        self._layers_loaded    = False
        self._preview_layer    = -1

    def closeEvent(self, event):
        self.makeCurrent()
        self._cleanup_mesh()
        self._cleanup_layers()
        if self._grid_vao is not None:
            try:
                glDeleteVertexArrays(1, [self._grid_vao])
                glDeleteBuffers(1, [self._grid_vbo])
            except Exception:
                pass
        self.doneCurrent()
        super().closeEvent(event)
