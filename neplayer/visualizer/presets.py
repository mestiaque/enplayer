"""Visualizer preset registry.

Each preset is a GLSL file in ./presets with a small header:

    // name: Classic Vertical EQ Bars
    // category: Bars

and a `vec4 render()` function using the helpers in header.glsl. Adding a file
adds a preset; the audio engine and renderer don't change.
"""
from dataclasses import dataclass
from pathlib import Path

PRESET_DIR = Path(__file__).resolve().parent / 'presets'
HEADER = (Path(__file__).resolve().parent / 'header.glsl').read_text(encoding='utf-8')


@dataclass(frozen=True)
class Preset:
    id: str
    name: str
    category: str
    body: str

    @property
    def source(self):
        return HEADER + '\n#line 1\n' + self.body


def load_presets(directory=PRESET_DIR):
    out = []
    for f in sorted(Path(directory).glob('*.glsl')):
        text = f.read_text(encoding='utf-8')
        meta = {}
        for line in text.splitlines()[:6]:
            if line.startswith('//') and ':' in line:
                k, v = line[2:].split(':', 1)
                meta[k.strip().lower()] = v.strip()
        pid = f.stem.split('-', 1)[-1] if f.stem[:2].isdigit() else f.stem
        out.append(Preset(pid, meta.get('name', pid.replace('-', ' ').title()), meta.get('category', 'Other'), text))
    return out
