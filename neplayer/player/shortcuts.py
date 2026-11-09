"""Keyboard shortcuts for the player, documented in one place."""
import gi

gi.require_version('Gdk', '4.0')
from gi.repository import Gdk

K = Gdk

# (keyval(s), modifier, action, argument)
PLAYER_KEYS = [
    ((K.KEY_space, K.KEY_k, K.KEY_K), 0, 'toggle-pause', None),
    ((K.KEY_Left,), 0, 'seek', -5),
    ((K.KEY_Right,), 0, 'seek', 5),
    ((K.KEY_Left,), K.ModifierType.SHIFT_MASK, 'seek', -1),
    ((K.KEY_Right,), K.ModifierType.SHIFT_MASK, 'seek', 1),
    ((K.KEY_Left,), K.ModifierType.CONTROL_MASK, 'seek', -60),
    ((K.KEY_Right,), K.ModifierType.CONTROL_MASK, 'seek', 60),
    ((K.KEY_j, K.KEY_J), 0, 'seek', -10),
    ((K.KEY_l, K.KEY_L), 0, 'seek', 10),
    ((K.KEY_Up,), 0, 'volume', 5),
    ((K.KEY_Down,), 0, 'volume', -5),
    ((K.KEY_f, K.KEY_F, K.KEY_F11), 0, 'fullscreen', None),
    ((K.KEY_m, K.KEY_M), 0, 'mute', None),
    ((K.KEY_Escape,), 0, 'escape', None),
    ((K.KEY_s, K.KEY_S), 0, 'cycle-sub', None),
    ((K.KEY_a, K.KEY_A), 0, 'cycle-audio', None),
    ((K.KEY_bracketleft,), 0, 'speed', -0.25),
    ((K.KEY_bracketright,), 0, 'speed', 0.25),
    ((K.KEY_BackSpace,), 0, 'speed-reset', None),
    ((K.KEY_n, K.KEY_N, K.KEY_Page_Down), 0, 'next', None),
    ((K.KEY_p, K.KEY_P, K.KEY_Page_Up), 0, 'prev', None),
    ((K.KEY_Home,), 0, 'restart', None),
    ((K.KEY_period,), 0, 'frame-step', 1),
    ((K.KEY_comma,), 0, 'frame-step', -1),
    ((K.KEY_i, K.KEY_I), 0, 'stats', None),
    ((K.KEY_s, K.KEY_S), K.ModifierType.CONTROL_MASK, 'screenshot', None),
    ((K.KEY_v, K.KEY_V), 0, 'toggle-sub-visibility', None),
    ((K.KEY_e, K.KEY_E), 0, 'equalizer', None),
]

_MODS = K.ModifierType.SHIFT_MASK | K.ModifierType.CONTROL_MASK | K.ModifierType.ALT_MASK


def lookup(keyval, state):
    mods = state & _MODS
    for keys, mod, action, arg in PLAYER_KEYS:
        if keyval in keys and mods == mod:
            return action, arg
    if mods == 0 and K.KEY_0 <= keyval <= K.KEY_9:
        return 'seek-percent', (keyval - K.KEY_0) * 10
    return None


HELP = [
    ('Playback', [('Space / K', 'Play / Pause'), ('← / →', 'Seek 5 seconds'),
                  ('Shift + ← / →', 'Seek 1 second'), ('Ctrl + ← / →', 'Seek 1 minute'),
                  ('J / L', 'Seek 10 seconds'), ('0 – 9', 'Jump to 0% – 90%'),
                  ('Home', 'Restart'), (', / .', 'Previous / next frame'),
                  ('[ / ]', 'Slower / faster'), ('Backspace', 'Normal speed'),
                  ('N / P', 'Next / previous video')]),
    ('Music', [('V', 'Visualizer on / off'), (', / .', 'Previous / next visualizer preset'),
               ('R', 'Random visualizer preset'), ('F', 'Fullscreen visualizer')]),
    ('Audio & Subtitles', [('↑ / ↓', 'Volume'), ('M', 'Mute'), ('E', 'Equalizer'), ('A', 'Next audio track'),
                           ('S', 'Next subtitle'), ('V', 'Show / hide subtitles')]),
    ('View', [('F / Double-click', 'Fullscreen'), ('Esc', 'Exit fullscreen / close player'),
              ('I', 'Statistics'), ('Ctrl + S', 'Screenshot')]),
    ('Library', [('Ctrl + O', 'Open file'), ('Ctrl + F', 'Search'), ('Ctrl + N', 'Add folder'),
                 ('F5', 'Rescan library'), ('Ctrl + Q', 'Quit')]),
]
