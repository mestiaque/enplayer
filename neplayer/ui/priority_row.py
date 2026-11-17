"""A row of controls that hides its optional ones when it is too narrow for all of them.

A Gtk.Box is at least as wide as all its children together, so a toolbar with many buttons
sets a large minimum width for the whole window (ENPlayer's library toolbar and player
controls made the window impossible to shrink below ~1170 px). GTK 4.6 (Ubuntu 22.04) has
no breakpoints, so PriorityRow does it itself: its minimum width counts only the essential
children (priority 0); when it gets less than its natural width, children with the highest
priority number are hidden first, and they come back as soon as there is room again.
"""
import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Gsk', '4.0')
gi.require_version('Graphene', '1.0')
from gi.repository import Graphene, Gsk, Gtk

H = Gtk.Orientation.HORIZONTAL


class PriorityRow(Gtk.Widget):
    def __init__(self, spacing=0, align_end=False, **kw):
        super().__init__(**kw)
        self._spacing = spacing
        self._align_end = align_end
        self._items = []  # [widget, priority, natural_target, expand], in visual order

    def add(self, child, priority=0, natural=0, expand=False):
        """priority 0 is always shown; larger numbers are hidden first when space runs out.
        natural: width the child grows to when there is room (e.g. a search box).
        expand: the child takes whatever space is left (a spacer or status label)."""
        child.set_parent(self)
        self._items.append([child, priority, natural, expand])
        return child

    def do_dispose(self):
        for child, *_ in self._items:
            child.unparent()
        self._items = []
        Gtk.Widget.do_dispose(self)

    def _shown(self):
        return [it for it in self._items if it[0].get_visible()]

    def _gaps(self, n):
        return self._spacing * max(0, n - 1)

    def do_measure(self, orientation, for_size):
        items = self._shown()
        if orientation == H:
            essential = [it for it in items if it[1] == 0]
            minimum = sum(it[0].measure(H, -1)[0] for it in essential) + self._gaps(len(essential))
            natural = sum(max(it[0].measure(H, -1)[1], it[2]) for it in items) + self._gaps(len(items))
            return minimum, max(minimum, natural), -1, -1
        minimum = natural = 0
        for it in items:
            m, n, _mb, _nb = it[0].measure(orientation, -1)
            minimum, natural = max(minimum, m), max(natural, n)
        return minimum, natural, -1, -1

    def _fit(self, width):
        """The children that fit in `width`, dropping the highest priority numbers first."""
        keep = self._shown()
        mins = {id(it[0]): it[0].measure(H, -1)[0] for it in keep}

        def needed(items):
            return sum(mins[id(it[0])] for it in items) + self._gaps(len(items))

        for prio in sorted({it[1] for it in keep if it[1] > 0}, reverse=True):
            if needed(keep) <= width:
                break
            keep = [it for it in keep if it[1] != prio]
        return keep, mins, width - needed(keep)

    def do_size_allocate(self, width, height, baseline):
        keep, mins, left = self._fit(width)
        widths = {}
        for it in keep:
            w = mins[id(it[0])]
            natural = max(it[0].measure(H, -1)[1], it[2])
            extra = min(max(0, left), max(0, natural - w)) if not it[3] else 0
            widths[id(it[0])] = w + extra
            left -= extra
        expanders = [it for it in keep if it[3]]
        if expanders and left > 0:
            share, rest = divmod(left, len(expanders))
            for i, it in enumerate(expanders):
                widths[id(it[0])] += share + (1 if i < rest else 0)
            left = 0
        x = max(0, left) if self._align_end else 0
        kept = {id(it[0]) for it in keep}
        for child, *_ in self._items:
            if id(child) not in kept:
                child.set_child_visible(False)
                continue
            child.set_child_visible(True)
            w = widths[id(child)]
            child.allocate(w, height, baseline, Gsk.Transform().translate(Graphene.Point().init(x, 0)))
            x += w + self._spacing
