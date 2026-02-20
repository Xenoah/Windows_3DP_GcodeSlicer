"""
3D OpenGL viewport for the slicer application.

Uses QOpenGLWidget with OpenGL 3.3 core profile.
Renders:
  - Build plate grid
  - 3D mesh with Phong shading
  - Sliced layer paths (as colored lines)
"""

import math
import numpy as np
from typing import List, Optional

from PyQt6.QtWidgets import QSizePolicy
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtCore import Qt, QPoint, pyqtSignal
from PyQt6.QtGui import QSurfaceFormat, QColor

try:
    from OpenGL.GL import (
        glGenVertexArrays, glBindVertexArray, glGenBuffers, glBindBuffer,
        glBufferData, glVertexAttribPointer, glEnableVertexAttribArray,
        glDrawArrays, glDrawElements, glEnable, glDisable, glDepthFunc,
        glClearColor, glClear, glViewport, glLineWidth,
        glUseProgram, glUniform3fv, glUniform1f, glUniformMatrix4fv,
        glGetUniformLocation, glDeleteBuffers, glDeleteVertexArrays,
        glCreateShader, glShaderSource, glCompileShader, glGetShaderiv,
        glGetShaderInfoLog, glCreateProgram, glAttachShader, glLinkProgram,
        glGetProgramiv, glGetProgramInfoLog, glDeleteShader, glDeleteProgram,
        glUniform3f, glPolygonMode, glFrontFace,
        GL_VERTEX_SHADER, GL_FRAGMENT_SHADER, GL_ARRAY_BUFFER,
        GL_ELEMENT_ARRAY_BUFFER, GL_STATIC_DRAW, GL_FLOAT, GL_UNSIGNED_INT,
        GL_TRIANGLES, GL_LINES, GL_LINE_STRIP, GL_DEPTH_TEST, GL_LESS,
        GL_COLOR_BUFFER_BIT, GL_DEPTH_BUFFER_BIT, GL_TRUE, GL_FALSE,
        GL_COMPILE_STATUS, GL_LINK_STATUS, GL_FRONT_AND_BACK, GL_LINE,
        GL_FILL, GL_CCW, GL_BLEND, GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA,
        glBlendFunc, GL_UNSIGNED_BYTE
    )
    OPENGL_OK = True
except ImportError as e:
    print(f"[Viewport] OpenGL import error: {e}")
    OPENGL_OK = False

try:
    from src.core.slicer import SlicedLayer
    SLICER_OK = True
except ImportError:
    SLICER_OK = False


# ---------------------------------------------------------------------------
# Shader source code
# ---------------------------------------------------------------------------

MESH_VERT_SHADER = """
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
    FragPos = vec3(model * vec4(aPos, 1.0));
    Normal = normalMat * aNormal;
}
"""

MESH_FRAG_SHADER = """
#version 330 core
in vec3 FragPos;
in vec3 Normal;
uniform vec3 lightDir;
uniform vec3 objectColor;
out vec4 FragColor;
void main() {
    float ambient = 0.3;
    vec3 norm = normalize(Normal);
    vec3 lightDirN = normalize(-lightDir);
    float diff = max(dot(norm, lightDirN), 0.0);
    vec3 lighting = (ambient + diff * 0.7) * objectColor;
    FragColor = vec4(lighting, 1.0);
}
"""

LINE_VERT_SHADER = """
#version 330 core
layout(location = 0) in vec3 aPos;
uniform mat4 MVP;
uniform vec3 lineColor;
out vec3 vColor;
void main() {
    gl_Position = MVP * vec4(aPos, 1.0);
    vColor = lineColor;
}
"""

LINE_FRAG_SHADER = """
#version 330 core
in vec3 vColor;
out vec4 FragColor;
void main() {
    FragColor = vec4(vColor, 1.0);
}
"""


# ---------------------------------------------------------------------------
# Math helpers
# ---------------------------------------------------------------------------

def _perspective(fov_deg, aspect, near, far):
    """Build a perspective projection matrix."""
    f = 1.0 / math.tan(math.radians(fov_deg) / 2.0)
    nf = 1.0 / (near - far)
    m = np.zeros((4, 4), dtype=np.float32)
    m[0, 0] = f / aspect
    m[1, 1] = f
    m[2, 2] = (far + near) * nf
    m[2, 3] = -1.0
    m[3, 2] = 2.0 * far * near * nf
    return m


def _look_at(eye, center, up):
    """Build a look-at view matrix."""
    eye = np.array(eye, dtype=np.float32)
    center = np.array(center, dtype=np.float32)
    up = np.array(up, dtype=np.float32)
    f = center - eye
    f /= np.linalg.norm(f)
    s = np.cross(f, up)
    s /= np.linalg.norm(s)
    u = np.cross(s, f)
    m = np.eye(4, dtype=np.float32)
    m[0, 0:3] = s
    m[1, 0:3] = u
    m[2, 0:3] = -f
    m[0, 3] = -np.dot(s, eye)
    m[1, 3] = -np.dot(u, eye)
    m[2, 3] = np.dot(f, eye)
    return m


def _rotation_matrix(azimuth_deg, elevation_deg):
    """Return a 4x4 rotation matrix from spherical camera angles."""
    az = math.radians(azimuth_deg)
    el = math.radians(elevation_deg)
    # Azimuth around Z, elevation around X
    ca, sa = math.cos(az), math.sin(az)
    ce, se = math.cos(el), math.sin(el)
    # Combined
    r = np.eye(4, dtype=np.float32)
    r[0, 0] = ca
    r[0, 1] = -sa * ce
    r[0, 2] = sa * se
    r[1, 0] = sa
    r[1, 1] = ca * ce
    r[1, 2] = -ca * se
    r[2, 0] = 0
    r[2, 1] = se
    r[2, 2] = ce
    return r


# ---------------------------------------------------------------------------
# Shader compilation
# ---------------------------------------------------------------------------

def _compile_shader(src: str, shader_type) -> int:
    shader = glCreateShader(shader_type)
    glShaderSource(shader, src)
    glCompileShader(shader)
    if not glGetShaderiv(shader, GL_COMPILE_STATUS):
        log = glGetShaderInfoLog(shader).decode()
        glDeleteShader(shader)
        raise RuntimeError(f"Shader compile error:\n{log}")
    return shader


def _link_program(vert_src: str, frag_src: str) -> int:
    vert = _compile_shader(vert_src, GL_VERTEX_SHADER)
    frag = _compile_shader(frag_src, GL_FRAGMENT_SHADER)
    prog = glCreateProgram()
    glAttachShader(prog, vert)
    glAttachShader(prog, frag)
    glLinkProgram(prog)
    glDeleteShader(vert)
    glDeleteShader(frag)
    if not glGetProgramiv(prog, GL_LINK_STATUS):
        log = glGetProgramInfoLog(prog).decode()
        glDeleteProgram(prog)
        raise RuntimeError(f"Program link error:\n{log}")
    return prog


# ---------------------------------------------------------------------------
# Viewport3D
# ---------------------------------------------------------------------------

class Viewport3D(QOpenGLWidget):
    """OpenGL 3D viewport for mesh and layer preview rendering."""

    layer_changed = pyqtSignal(int)  # emitted when preview layer changes

    def __init__(self, parent=None):
        # Request OpenGL 3.3 Core profile
        fmt = QSurfaceFormat()
        fmt.setVersion(3, 3)
        fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
        fmt.setDepthBufferSize(24)
        fmt.setSamples(4)  # MSAA
        QSurfaceFormat.setDefaultFormat(fmt)

        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(400, 300)

        # Camera state
        self._azimuth = 45.0      # degrees
        self._elevation = 30.0   # degrees
        self._distance = 300.0   # mm
        self._target = np.array([110.0, 110.0, 0.0], dtype=np.float32)  # look-at center

        # Mouse state
        self._last_mouse = QPoint()
        self._mouse_button = None

        # Build plate
        self._bed_x = 220.0
        self._bed_y = 220.0

        # Mesh rendering
        self._mesh_vao = None
        self._mesh_vbo = None
        self._mesh_nbo = None
        self._mesh_ebo = None
        self._mesh_index_count = 0
        self._mesh_loaded = False

        # Layer path rendering
        self._layer_vaos = []
        self._layer_vbos = []
        self._layer_vertex_counts = []
        self._layer_colors = []
        self._layer_z_values = []
        self._preview_layer = -1   # -1 = show all / no layers
        self._layers_loaded = False

        # Grid rendering
        self._grid_vao = None
        self._grid_vbo = None
        self._grid_vertex_count = 0

        # Shader programs
        self._mesh_prog = None
        self._line_prog = None

        # GL initialized?
        self._gl_ready = False

        # Colors
        self._mesh_color = np.array([0.2, 0.6, 1.0], dtype=np.float32)   # blue-ish
        self._grid_color = np.array([0.4, 0.4, 0.4], dtype=np.float32)
        self._bed_color = np.array([0.25, 0.25, 0.25], dtype=np.float32)

        # Layer colors (perimeter, infill, top/bottom, support, brim)
        self._layer_type_colors = {
            'perimeter': np.array([1.0, 0.5, 0.0], dtype=np.float32),
            'infill': np.array([0.0, 0.8, 0.0], dtype=np.float32),
            'top_bottom': np.array([0.2, 0.8, 1.0], dtype=np.float32),
            'support': np.array([0.8, 0.8, 0.0], dtype=np.float32),
            'brim': np.array([1.0, 0.0, 0.5], dtype=np.float32),
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_mesh(self, trimesh_mesh):
        """Upload mesh geometry to GPU VBOs."""
        self.makeCurrent()
        if not self._gl_ready:
            return

        # Clean up existing mesh buffers
        self._cleanup_mesh()

        try:
            verts = np.array(trimesh_mesh.vertices, dtype=np.float32)
            faces = np.array(trimesh_mesh.faces, dtype=np.uint32)
            normals = np.array(trimesh_mesh.vertex_normals, dtype=np.float32)

            self._mesh_vao = glGenVertexArrays(1)
            glBindVertexArray(self._mesh_vao)

            # Vertex positions
            self._mesh_vbo = glGenBuffers(1)
            glBindBuffer(GL_ARRAY_BUFFER, self._mesh_vbo)
            glBufferData(GL_ARRAY_BUFFER, verts.nbytes, verts, GL_STATIC_DRAW)
            glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 0, None)
            glEnableVertexAttribArray(0)

            # Vertex normals
            self._mesh_nbo = glGenBuffers(1)
            glBindBuffer(GL_ARRAY_BUFFER, self._mesh_nbo)
            glBufferData(GL_ARRAY_BUFFER, normals.nbytes, normals, GL_STATIC_DRAW)
            glVertexAttribPointer(1, 3, GL_FLOAT, GL_FALSE, 0, None)
            glEnableVertexAttribArray(1)

            # Index buffer
            self._mesh_ebo = glGenBuffers(1)
            glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, self._mesh_ebo)
            glBufferData(GL_ELEMENT_ARRAY_BUFFER, faces.nbytes, faces, GL_STATIC_DRAW)
            self._mesh_index_count = len(faces) * 3

            glBindVertexArray(0)
            self._mesh_loaded = True

            # Adjust camera to fit mesh
            bounds = trimesh_mesh.bounds
            center = (bounds[0] + bounds[1]) / 2
            self._target = np.array(center, dtype=np.float32)
            extents = bounds[1] - bounds[0]
            self._distance = float(np.max(extents) * 2.5)

        except Exception as e:
            print(f"[Viewport] load_mesh error: {e}")
            self._mesh_loaded = False

        self.doneCurrent()
        self.update()

    def load_layer_paths(self, layers: list):
        """Upload sliced layer paths to GPU as line VBOs."""
        self.makeCurrent()
        if not self._gl_ready:
            return

        self._cleanup_layers()

        if not layers:
            self.doneCurrent()
            return

        try:
            for layer in layers:
                z = float(layer.z)
                # Build combined line segments for each type
                self._upload_layer_paths_for_type(layer.perimeters, z, 'perimeter')
                self._upload_layer_paths_for_type(layer.infill, z, 'infill')
                self._upload_layer_paths_for_type(layer.top_bottom, z, 'top_bottom')
                self._upload_layer_paths_for_type(layer.support, z, 'support')
                self._upload_layer_paths_for_type(layer.brim, z, 'brim')

            self._layers_loaded = True
            self._preview_layer = len(layers) - 1

        except Exception as e:
            print(f"[Viewport] load_layer_paths error: {e}")

        self.doneCurrent()
        self.update()

    def _upload_layer_paths_for_type(self, paths, z: float, path_type: str):
        """Upload a list of paths (list of np arrays) as a VBO."""
        if not paths:
            return

        all_verts = []
        for path in paths:
            if path is None or len(path) < 2:
                continue
            arr = np.array(path, dtype=np.float32)
            if arr.ndim != 2 or arr.shape[1] < 2:
                continue
            # Create line strip vertices at height z
            for i in range(len(arr)):
                x, y = float(arr[i, 0]), float(arr[i, 1])
                all_verts.append([x, y, z])

        if not all_verts:
            return

        vdata = np.array(all_verts, dtype=np.float32)

        vao = glGenVertexArrays(1)
        glBindVertexArray(vao)
        vbo = glGenBuffers(1)
        glBindBuffer(GL_ARRAY_BUFFER, vbo)
        glBufferData(GL_ARRAY_BUFFER, vdata.nbytes, vdata, GL_STATIC_DRAW)
        glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 0, None)
        glEnableVertexAttribArray(0)
        glBindVertexArray(0)

        self._layer_vaos.append(vao)
        self._layer_vbos.append(vbo)
        self._layer_vertex_counts.append(len(vdata))
        self._layer_colors.append(self._layer_type_colors.get(path_type, np.array([1.0, 1.0, 1.0])))
        self._layer_z_values.append(z)

    def set_layer_preview(self, layer_index: int):
        """Show layers up to (and including) layer_index."""
        self._preview_layer = layer_index
        self.update()

    def reset_camera(self):
        """Reset camera to default position."""
        self._azimuth = 45.0
        self._elevation = 30.0
        self._distance = 300.0
        self._target = np.array([self._bed_x / 2, self._bed_y / 2, 0.0], dtype=np.float32)
        self.update()

    def set_bed_size(self, x: float, y: float):
        """Update the build plate size."""
        self._bed_x = float(x)
        self._bed_y = float(y)
        self._target = np.array([x / 2, y / 2, 0.0], dtype=np.float32)
        if self._gl_ready:
            self.makeCurrent()
            self._build_grid()
            self.doneCurrent()
        self.update()

    def clear_layers(self):
        """Remove all layer path data."""
        if self._gl_ready:
            self.makeCurrent()
            self._cleanup_layers()
            self.doneCurrent()
        self.update()

    def clear_mesh(self):
        """Remove mesh data."""
        if self._gl_ready:
            self.makeCurrent()
            self._cleanup_mesh()
            self.doneCurrent()
        self.update()

    # ------------------------------------------------------------------
    # OpenGL lifecycle
    # ------------------------------------------------------------------

    def initializeGL(self):
        if not OPENGL_OK:
            print("[Viewport] OpenGL not available")
            return
        try:
            glClearColor(0.12, 0.12, 0.12, 1.0)
            glEnable(GL_DEPTH_TEST)
            glDepthFunc(GL_LESS)
            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

            # Compile shaders
            self._mesh_prog = _link_program(MESH_VERT_SHADER, MESH_FRAG_SHADER)
            self._line_prog = _link_program(LINE_VERT_SHADER, LINE_FRAG_SHADER)

            # Build grid
            self._build_grid()

            self._gl_ready = True
        except Exception as e:
            print(f"[Viewport] initializeGL error: {e}")
            import traceback
            traceback.print_exc()

    def resizeGL(self, w: int, h: int):
        if h == 0:
            h = 1
        glViewport(0, 0, w, h)

    def paintGL(self):
        if not OPENGL_OK or not self._gl_ready:
            return

        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

        w, h = self.width(), self.height()
        if h == 0:
            return

        mvp, model_mat, normal_mat = self._compute_matrices(w, h)

        # Draw grid
        self._draw_grid(mvp)

        # Draw mesh (if no layers loaded, or mesh is visible)
        if self._mesh_loaded and not self._layers_loaded:
            self._draw_mesh(mvp, model_mat, normal_mat)
        elif self._mesh_loaded and self._layers_loaded:
            # Show mesh faintly in layer mode
            self._draw_mesh(mvp, model_mat, normal_mat, alpha_mode=True)

        # Draw layer paths
        if self._layers_loaded:
            self._draw_layers(mvp)

    # ------------------------------------------------------------------
    # Rendering helpers
    # ------------------------------------------------------------------

    def _compute_matrices(self, w: int, h: int):
        """Compute MVP, model and normal matrices from camera state."""
        # Camera position in spherical coordinates
        az = math.radians(self._azimuth)
        el = math.radians(self._elevation)

        eye_x = self._target[0] + self._distance * math.cos(el) * math.sin(az)
        eye_y = self._target[1] + self._distance * math.cos(el) * math.cos(az)
        eye_z = self._target[2] + self._distance * math.sin(el)

        eye = np.array([eye_x, eye_y, eye_z], dtype=np.float32)
        up = np.array([0.0, 0.0, 1.0], dtype=np.float32)

        view = _look_at(eye, self._target, up)
        proj = _perspective(45.0, w / h, 0.1, 10000.0)
        model = np.eye(4, dtype=np.float32)

        mvp = proj @ view @ model

        # Normal matrix = transpose(inverse(model)) upper-left 3x3
        normal_mat = np.linalg.inv(model[:3, :3]).T.astype(np.float32)

        return mvp, model, normal_mat

    def _draw_mesh(self, mvp, model_mat, normal_mat, alpha_mode=False):
        if not self._mesh_loaded or self._mesh_vao is None:
            return
        try:
            glUseProgram(self._mesh_prog)

            loc_mvp = glGetUniformLocation(self._mesh_prog, "MVP")
            loc_model = glGetUniformLocation(self._mesh_prog, "model")
            loc_nm = glGetUniformLocation(self._mesh_prog, "normalMat")
            loc_light = glGetUniformLocation(self._mesh_prog, "lightDir")
            loc_color = glGetUniformLocation(self._mesh_prog, "objectColor")

            glUniformMatrix4fv(loc_mvp, 1, GL_TRUE, mvp)
            glUniformMatrix4fv(loc_model, 1, GL_TRUE, model_mat)
            glUniformMatrix4fv(loc_nm, 1, GL_TRUE, normal_mat)

            light_dir = np.array([-1.0, -1.0, -2.0], dtype=np.float32)
            glUniform3fv(loc_light, 1, light_dir)

            color = self._mesh_color.copy()
            glUniform3fv(loc_color, 1, color)

            glBindVertexArray(self._mesh_vao)
            glDrawElements(GL_TRIANGLES, self._mesh_index_count, GL_UNSIGNED_INT, None)
            glBindVertexArray(0)
        except Exception as e:
            pass  # Silently skip render errors

    def _draw_grid(self, mvp):
        if self._grid_vao is None:
            return
        try:
            glUseProgram(self._line_prog)
            loc_mvp = glGetUniformLocation(self._line_prog, "MVP")
            loc_color = glGetUniformLocation(self._line_prog, "lineColor")

            glUniformMatrix4fv(loc_mvp, 1, GL_TRUE, mvp)
            glUniform3fv(loc_color, 1, self._grid_color)

            glBindVertexArray(self._grid_vao)
            glDrawArrays(GL_LINES, 0, self._grid_vertex_count)
            glBindVertexArray(0)
        except Exception as e:
            pass

    def _draw_layers(self, mvp):
        if not self._layer_vaos:
            return
        try:
            glUseProgram(self._line_prog)
            loc_mvp = glGetUniformLocation(self._line_prog, "MVP")
            loc_color = glGetUniformLocation(self._line_prog, "lineColor")
            glUniformMatrix4fv(loc_mvp, 1, GL_TRUE, mvp)

            max_z = -1e10
            if self._preview_layer >= 0 and self._layer_z_values:
                # Find the max z to show
                unique_zs = sorted(set(self._layer_z_values))
                if self._preview_layer < len(unique_zs):
                    max_z = unique_zs[self._preview_layer]
                else:
                    max_z = unique_zs[-1]

            for i, (vao, count, color, z) in enumerate(
                zip(self._layer_vaos, self._layer_vertex_counts,
                    self._layer_colors, self._layer_z_values)
            ):
                if self._preview_layer >= 0 and z > max_z + 1e-4:
                    continue
                glUniform3fv(loc_color, 1, color)
                glBindVertexArray(vao)
                glDrawArrays(GL_LINE_STRIP, 0, count)
                glBindVertexArray(0)
        except Exception as e:
            pass

    def _build_grid(self):
        """Build grid lines for the build plate."""
        if not self._gl_ready:
            return

        # Cleanup old grid
        if self._grid_vao is not None:
            try:
                glDeleteVertexArrays(1, [self._grid_vao])
                glDeleteBuffers(1, [self._grid_vbo])
            except Exception:
                pass

        try:
            grid_lines = []
            step = 10.0  # grid spacing in mm
            bx, by = self._bed_x, self._bed_y

            # Lines along X
            y = 0.0
            while y <= by + 1e-4:
                grid_lines += [[0.0, y, 0.0], [bx, y, 0.0]]
                y += step

            # Lines along Y
            x = 0.0
            while x <= bx + 1e-4:
                grid_lines += [[x, 0.0, 0.0], [x, by, 0.0]]
                x += step

            # Border (thicker, use same color for now)
            border = [
                [0, 0, 0], [bx, 0, 0],
                [bx, 0, 0], [bx, by, 0],
                [bx, by, 0], [0, by, 0],
                [0, by, 0], [0, 0, 0],
            ]
            grid_lines += border

            vdata = np.array(grid_lines, dtype=np.float32)

            self._grid_vao = glGenVertexArrays(1)
            glBindVertexArray(self._grid_vao)

            self._grid_vbo = glGenBuffers(1)
            glBindBuffer(GL_ARRAY_BUFFER, self._grid_vbo)
            glBufferData(GL_ARRAY_BUFFER, vdata.nbytes, vdata, GL_STATIC_DRAW)
            glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 0, None)
            glEnableVertexAttribArray(0)
            glBindVertexArray(0)

            self._grid_vertex_count = len(vdata)
        except Exception as e:
            print(f"[Viewport] _build_grid error: {e}")

    # ------------------------------------------------------------------
    # Mouse interaction
    # ------------------------------------------------------------------

    def mousePressEvent(self, event):
        self._last_mouse = event.pos()
        self._mouse_button = event.button()

    def mouseMoveEvent(self, event):
        if self._mouse_button is None:
            return
        dx = event.pos().x() - self._last_mouse.x()
        dy = event.pos().y() - self._last_mouse.y()
        self._last_mouse = event.pos()

        if self._mouse_button == Qt.MouseButton.LeftButton:
            # Orbit
            self._azimuth += dx * 0.5
            self._elevation = max(-89.0, min(89.0, self._elevation - dy * 0.5))
            self.update()

        elif self._mouse_button == Qt.MouseButton.MiddleButton:
            # Pan
            az = math.radians(self._azimuth)
            el = math.radians(self._elevation)

            # Right vector
            right_x = math.cos(az)
            right_y = -math.sin(az)

            # Up vector (in world space, projected)
            up_x = -math.sin(el) * math.sin(az)
            up_y = -math.sin(el) * math.cos(az)
            up_z = math.cos(el)

            scale = self._distance * 0.001
            self._target[0] -= (right_x * dx + up_x * dy) * scale
            self._target[1] -= (right_y * dx + up_y * dy) * scale
            self._target[2] -= up_z * dy * scale
            self.update()

    def mouseReleaseEvent(self, event):
        self._mouse_button = None

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        factor = 0.9 if delta > 0 else 1.1
        self._distance = max(10.0, min(5000.0, self._distance * factor))
        self.update()

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def _cleanup_mesh(self):
        if self._mesh_vao is not None:
            try:
                glDeleteVertexArrays(1, [self._mesh_vao])
            except Exception:
                pass
        if self._mesh_vbo is not None:
            try:
                glDeleteBuffers(1, [self._mesh_vbo])
            except Exception:
                pass
        if self._mesh_nbo is not None:
            try:
                glDeleteBuffers(1, [self._mesh_nbo])
            except Exception:
                pass
        if self._mesh_ebo is not None:
            try:
                glDeleteBuffers(1, [self._mesh_ebo])
            except Exception:
                pass
        self._mesh_vao = None
        self._mesh_vbo = None
        self._mesh_nbo = None
        self._mesh_ebo = None
        self._mesh_index_count = 0
        self._mesh_loaded = False

    def _cleanup_layers(self):
        for vao in self._layer_vaos:
            try:
                glDeleteVertexArrays(1, [vao])
            except Exception:
                pass
        for vbo in self._layer_vbos:
            try:
                glDeleteBuffers(1, [vbo])
            except Exception:
                pass
        self._layer_vaos = []
        self._layer_vbos = []
        self._layer_vertex_counts = []
        self._layer_colors = []
        self._layer_z_values = []
        self._layers_loaded = False
        self._preview_layer = -1

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
