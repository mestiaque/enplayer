"""Tiny OpenGL binding (ctypes) for the visualizer — just what a full-screen
fragment-shader renderer needs. Symbols are resolved through the same
EGL/GLX/WGL loader the mpv widget uses, so no extra dependency is required."""
import ctypes as C

from neplayer.player.mpv_widget import _get_proc_address

GL_FRAGMENT_SHADER = 0x8B30
GL_VERTEX_SHADER = 0x8B31
GL_COMPILE_STATUS = 0x8B81
GL_LINK_STATUS = 0x8B82
GL_INFO_LOG_LENGTH = 0x8B84
GL_TEXTURE_2D = 0x0DE1
GL_TEXTURE0 = 0x84C0
GL_TEXTURE_MIN_FILTER = 0x2801
GL_TEXTURE_MAG_FILTER = 0x2800
GL_TEXTURE_WRAP_S = 0x2802
GL_TEXTURE_WRAP_T = 0x2803
GL_LINEAR = 0x2601
GL_CLAMP_TO_EDGE = 0x812F
GL_R32F = 0x822E
GL_RED = 0x1903
GL_FLOAT = 0x1406
GL_TRIANGLES = 0x0004
GL_COLOR_BUFFER_BIT = 0x4000
GL_BLEND = 0x0BE2
GL_ONE = 1
GL_ONE_MINUS_SRC_ALPHA = 0x0303
GL_UNPACK_ALIGNMENT = 0x0CF5
GL_RGBA = 0x1908
GL_RGBA8 = 0x8058
GL_UNSIGNED_BYTE = 0x1401

_u, _i, _f, _p, _cp = C.c_uint, C.c_int, C.c_float, C.c_void_p, C.c_char_p

_SIGS = {
    'glCreateShader': (_u, [_u]),
    'glShaderSource': (None, [_u, _i, C.POINTER(_cp), C.POINTER(_i)]),
    'glCompileShader': (None, [_u]),
    'glGetShaderiv': (None, [_u, _u, C.POINTER(_i)]),
    'glGetShaderInfoLog': (None, [_u, _i, C.POINTER(_i), _cp]),
    'glDeleteShader': (None, [_u]),
    'glCreateProgram': (_u, []),
    'glAttachShader': (None, [_u, _u]),
    'glLinkProgram': (None, [_u]),
    'glGetProgramiv': (None, [_u, _u, C.POINTER(_i)]),
    'glGetProgramInfoLog': (None, [_u, _i, C.POINTER(_i), _cp]),
    'glDeleteProgram': (None, [_u]),
    'glUseProgram': (None, [_u]),
    'glGetUniformLocation': (_i, [_u, _cp]),
    'glUniform1f': (None, [_i, _f]),
    'glUniform2f': (None, [_i, _f, _f]),
    'glUniform3f': (None, [_i, _f, _f, _f]),
    'glUniform1i': (None, [_i, _i]),
    'glGenVertexArrays': (None, [_i, C.POINTER(_u)]),
    'glBindVertexArray': (None, [_u]),
    'glDrawArrays': (None, [_u, _i, _i]),
    'glGenTextures': (None, [_i, C.POINTER(_u)]),
    'glDeleteTextures': (None, [_i, C.POINTER(_u)]),
    'glBindTexture': (None, [_u, _u]),
    'glActiveTexture': (None, [_u]),
    'glTexImage2D': (None, [_u, _i, _i, _i, _i, _i, _u, _u, _p]),
    'glTexSubImage2D': (None, [_u, _i, _i, _i, _i, _i, _u, _u, _p]),
    'glTexParameteri': (None, [_u, _u, _i]),
    'glPixelStorei': (None, [_u, _i]),
    'glClearColor': (None, [_f, _f, _f, _f]),
    'glClear': (None, [_u]),
    'glViewport': (None, [_i, _i, _i, _i]),
    'glEnable': (None, [_u]),
    'glDisable': (None, [_u]),
    'glBlendFunc': (None, [_u, _u]),
}


class GL:
    """Resolved GL entry points. Create it while the GLArea's context is current."""

    def __init__(self):
        missing = []
        for name, (res, args) in _SIGS.items():
            addr = _get_proc_address(None, name.encode())
            if not addr:
                missing.append(name)
                continue
            setattr(self, name[2:], C.CFUNCTYPE(res, *args)(addr))
        if missing:
            raise RuntimeError('OpenGL functions unavailable: ' + ', '.join(missing))

    # --- helpers -----------------------------------------------------------
    def compile(self, kind, src):
        sh = self.CreateShader(kind)
        buf = C.c_char_p(src.encode())
        self.ShaderSource(sh, 1, C.byref(buf), None)
        self.CompileShader(sh)
        ok = C.c_int(0)
        self.GetShaderiv(sh, GL_COMPILE_STATUS, C.byref(ok))
        if not ok.value:
            n = C.c_int(0)
            self.GetShaderiv(sh, GL_INFO_LOG_LENGTH, C.byref(n))
            log = C.create_string_buffer(max(1, n.value))
            self.GetShaderInfoLog(sh, n.value, None, log)
            self.DeleteShader(sh)
            raise RuntimeError(log.value.decode(errors='replace'))
        return sh

    def program(self, vs_src, fs_src):
        vs = self.compile(GL_VERTEX_SHADER, vs_src)
        fs = self.compile(GL_FRAGMENT_SHADER, fs_src)
        prog = self.CreateProgram()
        self.AttachShader(prog, vs)
        self.AttachShader(prog, fs)
        self.LinkProgram(prog)
        self.DeleteShader(vs)
        self.DeleteShader(fs)
        ok = C.c_int(0)
        self.GetProgramiv(prog, GL_LINK_STATUS, C.byref(ok))
        if not ok.value:
            n = C.c_int(0)
            self.GetProgramiv(prog, GL_INFO_LOG_LENGTH, C.byref(n))
            log = C.create_string_buffer(max(1, n.value))
            self.GetProgramInfoLog(prog, n.value, None, log)
            self.DeleteProgram(prog)
            raise RuntimeError(log.value.decode(errors='replace'))
        return prog

    def float_texture(self, width, height):
        t = C.c_uint(0)
        self.GenTextures(1, C.byref(t))
        self.BindTexture(GL_TEXTURE_2D, t.value)
        for p, v in ((GL_TEXTURE_MIN_FILTER, GL_LINEAR), (GL_TEXTURE_MAG_FILTER, GL_LINEAR),
                     (GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE), (GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)):
            self.TexParameteri(GL_TEXTURE_2D, p, v)
        self.TexImage2D(GL_TEXTURE_2D, 0, GL_R32F, width, height, 0, GL_RED, GL_FLOAT, None)
        return t.value

    def rgba_texture(self, width, height, data):
        """8-bit RGBA texture (album art). data: uint8 (h, w, 4), bottom row first."""
        t = C.c_uint(0)
        self.GenTextures(1, C.byref(t))
        self.BindTexture(GL_TEXTURE_2D, t.value)
        for p, v in ((GL_TEXTURE_MIN_FILTER, GL_LINEAR), (GL_TEXTURE_MAG_FILTER, GL_LINEAR),
                     (GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE), (GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)):
            self.TexParameteri(GL_TEXTURE_2D, p, v)
        self.PixelStorei(GL_UNPACK_ALIGNMENT, 1)
        self.TexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, width, height, 0, GL_RGBA, GL_UNSIGNED_BYTE,
                        data.ctypes.data_as(C.c_void_p))
        return t.value

    def upload(self, tex, array):
        """array: float32 (rows, cols), C-contiguous."""
        self.BindTexture(GL_TEXTURE_2D, tex)
        self.PixelStorei(GL_UNPACK_ALIGNMENT, 1)
        self.TexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, array.shape[1], array.shape[0], GL_RED, GL_FLOAT,
                           array.ctypes.data_as(C.c_void_p))
