"""One spelling per file path.

On Windows, Python may join paths with "\\" (os.path) or "/" (pathlib under MSYS2), so the
same file could be stored and looked up under two different strings. Every path that goes
into or is looked up in the library passes through norm_path().
"""
import os


def norm_path(p):
    return os.path.normpath(os.fspath(p))
