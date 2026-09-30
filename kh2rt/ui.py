"""PySide6 interface: Live run, History, Stats, Race, Notes."""
from __future__ import annotations

import bisect
import datetime as dt
import os
import time
from contextlib import contextmanager
from pathlib import Path

from PySide6.QtCore import QEasingCurve, QEvent, QObject, QPointF, QRectF, QSize, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QFontDatabase, QFontMetricsF, QIcon, QPalette, QLinearGradient, QPainter, QPainterPath, QPen,
                           QPixmap)
from PySide6.QtWidgets import (
    QAbstractItemView, QAbstractScrollArea, QApplication, QCheckBox, QComboBox, QDialog, QFrame, QGridLayout, QHBoxLayout,
    QFileDialog, QHeaderView, QInputDialog, QLabel, QLineEdit, QListWidget, QProxyStyle, QScrollArea, QStyleFactory, QListWidgetItem, QMainWindow, QMessageBox, QPlainTextEdit, QPushButton,
    QSplitter, QStackedWidget, QStyle, QStyledItemDelegate, QStyleOptionViewItem, QTableWidget, QTableWidgetItem, QTabWidget, QToolTip, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)

from . import game_data as gd
from . import race as race_file
from .controller import Controller
from .storage import Store, run_from_dict
from .tracker import Run, fmt, is_check, milestone_splits, world_breakdown, world_totals

# ------------------------------------------------------------------ theme
BG = "#131A2E"        # deep navy, like the KH2 pause menu backdrop
PANEL = "#1B2442"
RAISED = "#26325A"
LINE = "#33406B"
TEXT = "#E9EDF8"
MUTED = "#8F9ABD"
GOLD = "#E7BE62"      # KH menu gold
GOOD = "#6FD39B"
BAD = "#EE7A7A"

KH = ["KHMenu"]


def is_boss(milestone: str) -> bool:
    """Boss, Data Org and Absent Silhouette fights all get the gold highlight."""
    return any(tag in milestone for tag in ("(Boss)", "(Data)", "(AS)"))


TITLE_STYLE = "header_kh"   # "header" | "center" | "header_kh"
DISPLAY = ["KHMenu", "Bahnschrift", "Segoe UI", "DejaVu Sans"]
BODY = ["KHMenu", "Segoe UI", "DejaVu Sans"]
SYMBOLS = ["Segoe UI Symbol", "Segoe UI", "DejaVu Sans"]   # KHMenu has no ◆ ★ ✕ ▲

KIND_GLYPH = {"check": "◆", "milestone": "★", "boss": "★", "drive": "⬆", "death": "✕", "level": "▲"}
BOSS_COLOUR = "#FF9F80"    # soft salmon: boss / Data / AS fights (other milestones stay gold)
DRIVE_COLOUR = "#9CCBFF"   # soft light blue: drive level-ups
KIND_COLOUR = {"check": TEXT, "milestone": GOLD, "boss": BOSS_COLOUR, "drive": DRIVE_COLOUR, "death": BAD,
               "level": MUTED}

_ICONS = (Path(__file__).parent / "icons").as_posix()
ARROW, ARROW_HOVER = f"{_ICONS}/combo_arrow.png", f"{_ICONS}/combo_arrow_hover.png"

QSS = f"""
* {{ color: {TEXT}; }}
QMainWindow, QWidget#root {{ background: {BG}; }}
QTabWidget::pane {{ border: none; }}
QTabWidget::tab-bar {{ left: 12px; }}
QTabBar {{ background: transparent; }}
QTabBar::tab {{ background: transparent; color: {MUTED}; padding: 7px 18px; margin: 10px 4px 6px 4px;
               border: 1px solid transparent; border-radius: 14px; }}
QTabBar::tab:selected {{ background: {RAISED}; border: 1px solid {LINE}; color: {GOLD}; }}
QTabBar::tab:hover:!selected {{ color: {TEXT}; background: rgba(255, 255, 255, 0.04); }}
QFrame#panel {{ background: {PANEL}; border-radius: 10px; }}
QFrame#statbox {{ background: rgba(255, 255, 255, 0.03); border: 1px solid rgba(143, 154, 189, 0.22);
                  border-radius: 8px; }}
QFrame#header {{ background: {PANEL}; border: none; }}
QPushButton {{ background: {RAISED}; border: 1px solid {LINE}; border-radius: 6px; padding: 7px 12px; }}
QPushButton:hover {{ border-color: {GOLD}; }}
QPushButton:disabled {{ color: #59648A; border-color: {RAISED}; }}
QPushButton#primary {{ background: {GOLD}; color: #1A1A1A; border: none; font-weight: 600; }}
QPushButton#primary:disabled {{ background: #6B5E3D; color: #2A2A2A; }}
QPushButton#danger:hover {{ border-color: {BAD}; }}
QLineEdit, QPlainTextEdit {{ background: {BG}; border: 1px solid {LINE}; border-radius: 6px; padding: 6px;
                             selection-background-color: {GOLD}; selection-color: #111; }}
QLineEdit:focus, QPlainTextEdit:focus {{ border-color: {GOLD}; }}
QTreeWidget, QTableWidget, QListWidget {{ background: {PANEL}; border: none; outline: none;
    alternate-background-color: #1E2849; }}
QTreeWidget::item, QListWidget::item {{ padding: 5px 2px; }}
QTreeWidget::item:selected, QTableWidget::item:selected, QListWidget::item:selected {{
    background: {RAISED}; color: {TEXT}; }}
QHeaderView::section {{ background: {PANEL}; color: {MUTED}; border: none; border-bottom: 1px solid {LINE};
    padding: 6px; font-family: "KHMenu", "Segoe UI"; font-size: 9.5pt; }}
QTableWidget {{ gridline-color: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 18px; margin: 4px 1px 4px 7px; }}
QScrollBar:horizontal {{ background: transparent; height: 18px; margin: 7px 4px 1px 4px; }}
QScrollBar::sub-page:vertical {{ background: rgba(0, 0, 0, 0.28); border-top-left-radius: 4px; border-top-right-radius: 4px; }}
QScrollBar::add-page:vertical {{ background: rgba(0, 0, 0, 0.28); border-bottom-left-radius: 4px; border-bottom-right-radius: 4px; }}
QScrollBar::sub-page:horizontal {{ background: rgba(0, 0, 0, 0.28); border-top-left-radius: 4px; border-bottom-left-radius: 4px; }}
QScrollBar::add-page:horizontal {{ background: rgba(0, 0, 0, 0.28); border-top-right-radius: 4px; border-bottom-right-radius: 4px; }}
QAbstractScrollArea::corner {{ background: transparent; }}
QScrollBar::handle:vertical {{ min-height: 36px; border-radius: 4px; border: 1px solid rgba(0, 0, 0, 0.55);
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #5A6BA3, stop:1 #38457A); }}
QScrollBar::handle:horizontal {{ min-width: 36px; border-radius: 4px; border: 1px solid rgba(0, 0, 0, 0.55);
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #5A6BA3, stop:1 #38457A); }}
QScrollBar::handle:hover {{ background: #6577B0; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QSplitter::handle {{ background: {BG}; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {LINE}; border-radius: 4px;
    background: {BG}; }}
QCheckBox::indicator:checked {{ background: {GOLD}; border-color: {GOLD}; }}
QToolTip {{ background: {RAISED}; color: {TEXT}; border: 1px solid {LINE}; padding: 4px; }}
QDialog, QMessageBox, QInputDialog {{ background: {BG}; }}
QComboBox {{ background: {BG}; border: 1px solid {LINE}; border-radius: 6px; padding: 6px 8px;
    combobox-popup: 0; }}
QComboBox:hover, QComboBox:on {{ border-color: {GOLD}; }}
QComboBox::drop-down {{ subcontrol-origin: padding; subcontrol-position: center right; width: 22px;
    border: none; background: transparent; }}
QComboBox::down-arrow {{ image: url("{ARROW}"); width: 10px; height: 6px; }}
QComboBox::down-arrow:hover, QComboBox::down-arrow:on {{ image: url("{ARROW_HOVER}"); }}
QComboBoxPrivateContainer {{ background: {RAISED}; border: 1px solid {LINE}; border-radius: 0; }}
QComboBox QAbstractItemView {{ background: {RAISED}; border: none; outline: none; padding: 4px;
    selection-background-color: {LINE}; }}
"""


def font(families, size, weight=QFont.Weight.Normal):
    f = QFont()
    f.setFamilies(families)
    f.setPointSizeF(size)
    f.setWeight(weight)
    # Windows hinting snaps glyphs to the pixel grid, which mangles KHMenu at small sizes.
    f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    f.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    if size < 11:  # a touch of tracking keeps small KHMenu letters from running together
        f.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 104)
    return f


DRIVE_GRADIENT = ("#F29E14", "#FFEE40")   # the tracker's drive star


def wgrad(world: str) -> tuple[str, str]:
    if world == "Drive Forms":
        return DRIVE_GRADIENT
    if world == "General":
        return (GOLD, "#FFE3A0")
    return gd.WORLD_GRADIENTS.get(world, (MUTED, MUTED))


def wcol(world: str) -> str:
    return wgrad(world)[0]


def gradient(world: str, rect: QRectF, vertical=False) -> QLinearGradient:
    a, b = wgrad(world)
    g = QLinearGradient(rect.topLeft(), rect.bottomLeft() if vertical else rect.topRight())
    g.setColorAt(0, QColor(a))
    g.setColorAt(1, QColor(b))
    return g


def qss_gradient(world: str) -> str:
    a, b = wgrad(world)
    return f"qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {a}, stop:1 {b})"


def text_on(world: str) -> QColor:
    """Dark or light label text, whichever reads better on this world's gradient."""
    def lum(hexc):
        c = QColor(hexc)
        return 0.2126 * c.redF() + 0.7152 * c.greenF() + 0.0722 * c.blueF()
    a, b = wgrad(world)
    return QColor("#12141F") if (lum(a) + lum(b)) / 2 > 0.62 else QColor("#FFFFFF")


ICON_DIR = Path(__file__).parent / "icons"
_icon_cache: dict = {}


def world_pixmap(world: str, size: int) -> QPixmap:
    """The world's tracker icon, filled with the world's gradient. Falls back to a rounded square."""
    key = (world, size)
    if key in _icon_cache:
        return _icon_cache[key]
    a, b = wgrad(world)
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
    rect = QRectF(0, 0, size, size)
    g = QLinearGradient(rect.bottomLeft(), rect.topLeft())   # dark at the bottom, light at the top
    g.setColorAt(0, QColor(a))
    g.setColorAt(1, QColor(b))
    f = ICON_DIR / f"{gd.WORLD_ICONS.get(world, '')}.png"
    if world in gd.WORLD_ICONS and f.exists():
        src = QPixmap(str(f)).scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                                     Qt.TransformationMode.SmoothTransformation)
        p.drawPixmap(0, 0, src)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        p.fillRect(rect, g)
    else:
        p.setBrush(g)
        p.setPen(Qt.PenStyle.NoPen)
        m = size * 0.2
        p.drawRoundedRect(rect.adjusted(m, m, -m, -m), 3, 3)
    p.end()
    _icon_cache[key] = pm
    return pm


def glyph_pixmap(kind: str, size: int) -> QPixmap:
    key = ("_glyph", kind, size)
    if key not in _icon_cache:
        pm = QPixmap(size, size)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        p.setPen(QColor(KIND_COLOUR[kind]))
        p.setFont(font(SYMBOLS, size * 0.42))
        p.drawText(QRectF(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, KIND_GLYPH[kind])
        p.end()
        _icon_cache[key] = pm
    return _icon_cache[key]


def kind_icon(kind: str) -> QIcon:
    """Marker for a route event. Drive level-ups use the Drive Forms icon."""
    if kind == "drive":
        return swatch("Drive Forms")
    icon = QIcon()
    for sz in (16, 20, 24, 32, 48):
        icon.addPixmap(glyph_pixmap(kind, sz))
    return icon


def swatch(world: str, *_):
    icon = QIcon()
    for sz in (16, 20, 24, 32, 48, 64):
        icon.addPixmap(world_pixmap(world, sz))
    return icon


def label(text="", size=10, colour=TEXT, families=BODY, weight=QFont.Weight.Normal):
    l = QLabel(text)
    l.setFont(font(families, size, weight))
    l.setStyleSheet(f"color:{colour}; background:transparent;")
    return l


def panel() -> QFrame:
    f = QFrame()
    f.setObjectName("panel")
    return f


# ------------------------------------------------------------------ perf
PERF = os.environ.get("RETRACE_PERF") == "1"


@contextmanager
def perf(what: str):
    """Timing for the slow paths, printed only when RETRACE_PERF=1."""
    if not PERF:
        yield
        return
    t0 = time.perf_counter()
    try:
        yield
    finally:
        print(f"[perf] {what}: {(time.perf_counter() - t0) * 1000:.1f} ms", flush=True)


@contextmanager
def bulk_fill(table: QTableWidget):
    """Hold ResizeToContents columns still while a table is refilled.

    Left alone, those columns re-measure every row on each setItem, which makes filling an
    n-row table O(n**2) and costs ~240 ms for the Stats tables. Restoring the modes at the
    end runs one resize pass, so the final column widths are unchanged.
    """
    head = table.horizontalHeader()
    modes = [head.sectionResizeMode(i) for i in range(table.columnCount())]
    auto = QHeaderView.ResizeMode.ResizeToContents
    for i, mode in enumerate(modes):
        if mode == auto:
            head.setSectionResizeMode(i, QHeaderView.ResizeMode.Fixed)
    try:
        yield
    finally:
        for i, mode in enumerate(modes):
            if mode == auto:
                head.setSectionResizeMode(i, mode)


# ------------------------------------------------------------------ crisp text everywhere
_PATH_CACHE = {}
_CELL_CACHE = {}
_ORIGIN_CACHE = {}


def cached_path(cache, key, build):
    """Outlines are expensive to trace and identical every frame, so keep them keyed by shape."""
    path = cache.get(key)
    if path is None:
        if len(cache) > 5000:   # keep memory bounded
            cache.clear()
        path = cache[key] = build()
    return path


def _build_text_path(f, flags, w, h, text):
    fm = QFontMetricsF(f)
    lines = []
    for para in text.replace("&&", "\0").replace("&", "").replace("\0", "&").split("\n"):
        if flags & Qt.TextFlag.TextWordWrap and fm.horizontalAdvance(para) > w:
            cur = ""
            for word in para.split(" "):
                trial = f"{cur} {word}".strip()
                if cur and fm.horizontalAdvance(trial) > w:
                    lines.append(cur)
                    cur = word
                else:
                    cur = trial
            lines.append(cur)
        else:
            lines.append(para)
    lh = fm.height()
    total = lh * len(lines)
    if flags & Qt.AlignmentFlag.AlignBottom:
        y = h - total
    elif flags & Qt.AlignmentFlag.AlignTop:
        y = 0.0
    else:
        y = (h - total) / 2
    path = QPainterPath()
    for line in lines:
        tw = fm.horizontalAdvance(line)
        if flags & Qt.AlignmentFlag.AlignRight:
            x = w - tw
        elif flags & Qt.AlignmentFlag.AlignHCenter:
            x = (w - tw) / 2
        else:
            x = 0.0
        path.addText(QPointF(x, y + fm.ascent()), f, line)
        y += lh
    return path


def vector_text(painter, rect, flags, text, colour):
    f = painter.font()
    key = (f.key(), int(flags), round(rect.width()), round(rect.height()), text)
    path = cached_path(_PATH_CACHE, key,
                       lambda: _build_text_path(f, flags, rect.width(), rect.height(), text))
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.translate(rect.topLeft())
    painter.fillPath(path, colour)
    painter.restore()


class VectorStyle(QProxyStyle):
    """App-wide: every label, button, checkbox, tab and header draws its text as vector outlines."""

    def drawItemText(self, painter, rect, flags, pal, enabled, text, role=QPalette.ColorRole.NoRole):
        if not text:
            return
        if role == QPalette.ColorRole.NoRole:
            role = QPalette.ColorRole.WindowText
        group = QPalette.ColorGroup.Active if enabled else QPalette.ColorGroup.Disabled
        vector_text(painter, QRectF(rect), flags, text, pal.color(group, role))


# ------------------------------------------------------------------ smooth scrolling
class SmoothScroller(QObject):
    """Wheel scrolling glides to its target instead of jumping. Touchpads scroll pixel by pixel."""
    STEP = 90          # pixels per wheel notch
    DURATION = 260     # ms

    def __init__(self, area):
        super().__init__(area)
        self.area = area
        self.anims = {}
        self.targets = {}
        area.viewport().installEventFilter(self)
        if isinstance(area, QAbstractItemView):
            area.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
            area.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
            area.verticalScrollBar().setSingleStep(12)

    def eventFilter(self, obj, ev):
        if ev.type() != QEvent.Type.Wheel:
            return False
        horizontal = bool(ev.modifiers() & Qt.KeyboardModifier.ShiftModifier) or \
            abs(ev.angleDelta().x()) > abs(ev.angleDelta().y())
        bar = self.area.horizontalScrollBar() if horizontal else self.area.verticalScrollBar()
        if bar.maximum() == bar.minimum():
            return False  # nothing to scroll here; let the parent scroll instead
        pixel = ev.pixelDelta()
        if not pixel.isNull():  # touchpad: already smooth, follow it directly
            bar.setValue(bar.value() - (pixel.x() if horizontal else pixel.y()))
            return True
        notches = (ev.angleDelta().x() if horizontal else ev.angleDelta().y()) / 120
        anim = self.anims.get(bar)
        start_from = self.targets.get(bar, bar.value()) if anim and anim.state() == QVariantAnimation.State.Running \
            else bar.value()
        target = max(bar.minimum(), min(bar.maximum(), round(start_from - notches * self.STEP)))
        self.targets[bar] = target
        if anim is None:
            anim = QVariantAnimation(self)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            anim.valueChanged.connect(lambda v, b=bar: b.setValue(int(v)))
            self.anims[bar] = anim
        anim.stop()
        anim.setDuration(self.DURATION)
        anim.setStartValue(bar.value())
        anim.setEndValue(target)
        anim.start()
        return True


def enable_smooth_scrolling(root: QWidget):
    for area in root.findChildren(QAbstractScrollArea):
        if not area.property("_smooth"):
            area.setProperty("_smooth", True)
            SmoothScroller(area)


# ------------------------------------------------------------------ crisp cell text
def origin_text_path(f, text):
    """Outlines with the baseline at the origin, so painter.translate() places them."""
    path = QPainterPath()
    path.addText(QPointF(0, 0), f, text)
    return path


def _build_cell_path(f, align, w, h, text):
    """One cell's outlines, positioned relative to the cell's top-left corner."""
    fm = QFontMetricsF(f)
    text = fm.elidedText(text, Qt.TextElideMode.ElideRight, w)
    tw = fm.horizontalAdvance(text)
    if align & Qt.AlignmentFlag.AlignRight:
        x = w - tw
    elif align & Qt.AlignmentFlag.AlignHCenter:
        x = (w - tw) / 2
    else:
        x = 0.0
    path = QPainterPath()
    path.addText(QPointF(x, (h + fm.ascent() - fm.descent()) / 2), f, text)
    return path


class VectorTextDelegate(QStyledItemDelegate):
    """Draws list/table cell text as filled outlines so small KHMenu text stays smooth on Windows."""

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        text = opt.text
        opt.text = ""
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)  # bg, selection, icon
        if not text:
            return
        rect = QRectF(style.subElementRect(QStyle.SubElement.SE_ItemViewItemText, opt, opt.widget)).adjusted(2, 0, -2, 0)
        align = opt.displayAlignment
        # the elided text is part of the built path, so a hit skips measuring and eliding too
        key = (opt.font.key(), int(align), round(rect.width()), round(rect.height()), text)
        path = cached_path(_CELL_CACHE, key,
                           lambda: _build_cell_path(opt.font, align, rect.width(), rect.height(), text))
        fg = index.data(Qt.ItemDataRole.ForegroundRole)
        colour = fg.color() if isinstance(fg, QBrush) else (fg if isinstance(fg, QColor) else QColor(TEXT))
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.translate(rect.topLeft())
        painter.fillPath(path, colour)
        painter.restore()


# ------------------------------------------------------------------ wordmark
class Wordmark(QWidget):
    """RE:Trace in the KH menu font, gold with the same dark-bottom/light-top gradient as the icons."""

    def __init__(self, size=26.0, text="RE:Trace"):
        super().__init__()
        self.text = text
        self.f = font(KH, size, QFont.Weight.Bold)
        self.f.setItalic(True)
        # the wordmark never changes, so trace it once instead of on every repaint
        base = origin_text_path(self.f, text)
        self.box = base.boundingRect()
        self.setFixedSize(int(self.box.width()) + 8, int(self.box.height()) + 8)
        self.path = base.translated(4 - self.box.left(), 4 - self.box.top())
        self.shadow = self.path.translated(1.5, 2)
        self.r = self.path.boundingRect()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path, r = self.path, self.r
        p.fillPath(self.shadow, QColor(0, 0, 0, 110))                      # soft drop shadow
        g = QLinearGradient(r.bottomLeft(), r.topLeft())
        g.setColorAt(0, QColor("#B07A1E"))
        g.setColorAt(0.55, QColor("#E7BE62"))
        g.setColorAt(1, QColor("#FFF0B8"))
        p.fillPath(path, g)
        p.setPen(QPen(QColor(90, 60, 10, 140), 0.8))
        p.drawPath(path)
        p.end()


# ------------------------------------------------------------------ route ribbon
class RouteRibbon(QWidget):
    """The run at a glance: one proportional band per world visit, in order."""

    def __init__(self, height=46):
        super().__init__()
        self.setMinimumHeight(height)
        self.setMouseTracking(True)
        self.segments = []
        self.total = 0.0
        self.live = False
        self.track = QColor(PANEL)   # shows through past the end of a run shorter than the scale
        self._rects = []

    def set_run(self, segments, total, live=False):
        self.segments, self.total, self.live = segments, max(total, 1.0), live
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        clip = QPainterPath()
        clip.addRoundedRect(r, 8, 8)
        p.fillPath(clip, self.track)
        p.setClipPath(clip)
        self._rects = []
        x = r.left()
        name_f = font(KH, 10, QFont.Weight.Bold)
        time_f = font(KH, 9.5)
        p.setFont(name_f)
        for i, s in enumerate(self.segments):
            w = (s.end - s.start) / self.total * r.width()
            rect = QRectF(x, r.top(), max(w, 1.5), r.height())
            p.fillRect(rect, gradient(s.world, rect))
            if s.world == "Garden of Assemblage":
                p.fillRect(rect, QColor(19, 26, 46, 120))  # GoA recedes; worlds stand out
            p.fillRect(QRectF(rect.right() - 1, rect.top(), 1, rect.height()), QColor(BG))
            if w > 70:
                name = s.world.replace("The World That Never Was", "TWTNW").replace("Simulated Twilight Town", "STT")
                text = p.fontMetrics().elidedText(name, Qt.TextElideMode.ElideRight, int(w - 14))
                half = rect.height() / 2
                self._vector_text(p, text, name_f, rect.left() + 8, rect.top() + half - 3, s.world)
                self._vector_text(p, fmt(s.end - s.start), time_f, rect.left() + 8, rect.top() + half + 13, s.world)
            self._rects.append((rect, s, i))
            x += w
        if self.live and self.segments:
            rect = self._rects[-1][0]
            p.setClipping(False)
            p.setPen(QPen(QColor(TEXT), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 4, 4)
        p.end()

    @staticmethod
    def _vector_text(p, text, f, x, baseline, world):
        """Text drawn as filled outlines: smooth at small sizes, same approach as the logo.

        Deliberately uncached: only the few segments wider than 70px carry text, so the whole
        ribbon repaints in ~2.5 ms, and caching at the origin shifts the antialiasing of these
        fractional positions by a hair.
        """
        path = QPainterPath()
        path.addText(QPointF(x, baseline), f, text)
        colour = text_on(world)
        if colour.lightness() > 128:
            p.fillPath(path.translated(0, 1.2), QColor(0, 0, 0, 120))
        p.fillPath(path, colour)

    def mouseMoveEvent(self, e):
        for rect, s, i in self._rects:
            if rect.contains(e.position()):
                QToolTip.showText(e.globalPosition().toPoint(),
                                  f"#{i + 1} {s.world}\n{fmt(s.start)} – {fmt(s.end)}  ({fmt(s.end - s.start)})"
                                  + (f"\nDeaths: {s.deaths}" if s.deaths else ""), self)
                return
        QToolTip.hideText()


# ------------------------------------------------------------------ route tree
class RouteTree(QTreeWidget):
    """World visits in order; expand a visit to see what happened inside it."""

    def __init__(self):
        super().__init__()
        self.setColumnCount(3)
        self.setHeaderLabels(["", "At", "Time"])
        self.setRootIsDecorated(True)
        self.setIndentation(18)
        self.setIconSize(QSize(20, 20))
        self.setItemDelegate(VectorTextDelegate(self))
        self.setFont(font(BODY, 10))
        self.headerItem().setTextAlignment(1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.headerItem().setTextAlignment(2, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.setUniformRowHeights(False)
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        h = self.header()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        h.setStretchLastSection(False)
        self.show_levels = False
        self.event_filter = lambda e: True
        self._run: Run | None = None

    def set_run(self, run: Run, expand_last=True):
        self._run = run
        expanded = {i for i in range(self.topLevelItemCount()) if self.topLevelItem(i).isExpanded()}
        self.clear()
        starts = [s.start for s in run.segments]
        buckets: list[list] = [[] for _ in run.segments]
        all_evs: list[list] = [[] for _ in run.segments]
        for e in run.events:
            if all_evs:
                all_evs[max(0, bisect.bisect_right(starts, e.t) - 1)].append(e)
            if (e.kind == "level" and not self.show_levels) or not self.event_filter(e):
                continue
            i = max(0, bisect.bisect_right(starts, e.t) - 1)
            if buckets:
                buckets[i].append(e)
        bold = font(DISPLAY, 10.5, QFont.Weight.DemiBold)
        for i, (s, evs) in enumerate(zip(run.segments, buckets)):
            checks = sum(1 for e in all_evs[i] if is_check(e))
            extra = f"   {checks} check{'s' if checks != 1 else ''}" if checks else ""
            top = QTreeWidgetItem([f"{i + 1}.  {s.world}{extra}", fmt(s.start), fmt(s.end - s.start)])
            top.setIcon(0, swatch(s.world, 12, 12))
            top.setFont(0, bold)
            top.setFont(2, bold)
            top.setFont(1, font(BODY, 10))
            top.setForeground(1, QBrush(QColor(MUTED)))
            top.setForeground(0, QBrush(QColor(TEXT)))
            top.setForeground(2, QBrush(QColor(TEXT)))
            for col in (1, 2):
                top.setTextAlignment(col, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            for e in evs:
                name = e.name + (f"  ·  {e.category}" if e.category else "")
                c = QTreeWidgetItem([name, fmt(e.t), ""])
                style = "boss" if e.kind == "milestone" and is_boss(e.name) else e.kind
                c.setIcon(0, kind_icon(style))
                c.setForeground(0, QBrush(QColor(KIND_COLOUR[style])))
                c.setForeground(1, QBrush(QColor(MUTED)))
                c.setTextAlignment(1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                top.addChild(c)
            self.addTopLevelItem(top)
            if i in expanded or (expand_last and i == len(run.segments) - 1):
                top.setExpanded(True)
        if expand_last and self.topLevelItemCount():
            self.scrollToBottom()

    def refresh_last_time(self):
        if self._run and self._run.segments and self.topLevelItemCount():
            s = self._run.segments[-1]
            self.topLevelItem(self.topLevelItemCount() - 1).setText(2, fmt(s.end - s.start))


# ------------------------------------------------------------------ bar chart
class WorldBars(QWidget):
    """Average time per world, longest first."""

    def __init__(self, empty_text="Finish a run to see world averages here."):
        super().__init__()
        self.rows = []
        self.empty_text = empty_text
        self.setMinimumHeight(200)

    def set_rows(self, rows):
        self.rows = sorted(rows, key=lambda r: -r[1])
        self.setMinimumHeight(max(200, 36 * len(self.rows) + 10))
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.rows:
            p.setPen(QColor(MUTED))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.empty_text)
            return
        mx = max(r[1] for r in self.rows) or 1
        p.setFont(font(BODY, 10.5))
        icon_w = 30
        lw = icon_w + max(p.fontMetrics().horizontalAdvance(w) for w, _ in self.rows) + 16
        tw = p.fontMetrics().horizontalAdvance("00:00") + 14
        for i, (w, secs) in enumerate(self.rows):
            y = 6 + i * 36
            fm = p.fontMetrics()
            base = y + 11 + (fm.ascent() - fm.descent()) / 2
            pm = world_pixmap(w, 44)
            pm.setDevicePixelRatio(2)
            p.drawPixmap(QPointF(0, y), pm)
            self._text(p, w, icon_w, base, QColor(TEXT))
            bw = (self.width() - lw - tw) * secs / mx
            path = QPainterPath()
            path.addRoundedRect(QRectF(lw, y + 1, max(bw, 3), 20), 6, 6)
            p.fillPath(path, gradient(w, QRectF(lw, y + 1, max(bw, 3), 20)))
            self._text(p, fmt(secs), lw + bw + 8, base, QColor(MUTED))
        p.end()

    @staticmethod
    def _text(p, text, x, baseline, colour):
        f = p.font()
        path = cached_path(_ORIGIN_CACHE, (f.key(), text), lambda: origin_text_path(f, text))
        p.fillPath(path.translated(x, baseline), colour)


# ------------------------------------------------------------------ tables
def data_table(headers) -> QTableWidget:
    """Read-only table in the Stats style: alternating rows, first column stretches."""
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.verticalHeader().setVisible(False)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)   # read-only figures: nothing to pick
    t.setFocusPolicy(Qt.FocusPolicy.NoFocus)                          # no focus outline on click either
    t.setAlternatingRowColors(True)
    t.setShowGrid(False)
    t.setItemDelegate(VectorTextDelegate(t))
    t.setFont(font(BODY, 10))
    t.horizontalHeader().setFont(font(BODY, 9.5))
    t.setWordWrap(False)
    t.setTextElideMode(Qt.TextElideMode.ElideRight)
    t.setIconSize(QSize(20, 20))
    t.verticalHeader().setDefaultSectionSize(30)
    t.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
    for i in range(1, len(headers)):
        t.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
    return t


def table_cell(text, sort=None, colour=None) -> QTableWidgetItem:
    it = QTableWidgetItem(text)
    if sort is not None:
        it.setData(Qt.ItemDataRole.UserRole, sort)
    it.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | (Qt.AlignmentFlag.AlignLeft if sort is None
                                                        else Qt.AlignmentFlag.AlignRight))
    if colour:
        it.setForeground(QBrush(QColor(colour)))
    return it


def milestone_colour(world: str, name: str) -> str | None:
    return BOSS_COLOUR if is_boss(name) else (DRIVE_COLOUR if world == "Drive Forms" else None)


def fill_world_table(table: QTableWidget, rows, times):
    """rows: (world, data) pairs; times(data) gives the time columns, then visits, deaths, checks follow."""
    with bulk_fill(table):
        table.setRowCount(len(rows))
        for r, (w, d) in enumerate(rows):
            name = table_cell(w)
            name.setIcon(swatch(w))
            table.setItem(r, 0, name)
            vals = list(times(d)) + [d["visits"], d["deaths"], d["checks"]]
            deaths_col = len(vals) - 1
            for c, v in enumerate(vals, 1):
                text = v if isinstance(v, str) else (f"{v:.1f}" if isinstance(v, float) else str(v))
                table.setItem(r, c, table_cell(text, 0, BAD if c == deaths_col and d["deaths"] >= 1 else None))


def fill_milestone_table(table: QTableWidget, rows):
    """rows: (world, name, *time columns already formatted)."""
    with bulk_fill(table):
        table.setRowCount(len(rows))
        for r, (world, name, *vals) in enumerate(rows):
            table.setItem(r, 0, table_cell(name, colour=milestone_colour(world, name)))
            wi = table_cell("")
            wi.setIcon(swatch(world))
            wi.setToolTip(world)
            table.setItem(r, 1, wi)
            for c, v in enumerate(vals, 2):
                table.setItem(r, c, table_cell(v, 0))


def milestone_table(headers) -> QTableWidget:
    """Milestone name, then a narrow world-icon column, then the given time columns."""
    t = data_table(["Milestone", ""] + headers)
    t.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
    t.setColumnWidth(1, 34)
    return t


def ask_username(parent, ctl: Controller) -> str:
    """Your racer name, asking for it the first time. Empty if you cancel."""
    if not ctl.username:
        name, ok = QInputDialog.getText(parent, "Your racer name", "Your Racer Name:")
        if ok:
            ctl.set_username(name)
    return ctl.username


# ------------------------------------------------------------------ presets
class ComboDelegate(VectorTextDelegate):
    """Crisp popup text for combo boxes, with thin separator lines."""

    @staticmethod
    def _separator(index):
        return index.data(Qt.ItemDataRole.AccessibleDescriptionRole) == "separator"

    def paint(self, painter, option, index):
        if self._separator(index):
            r = option.rect
            painter.fillRect(QRectF(r.left() + 6, r.center().y(), r.width() - 12, 1), QColor(LINE))
            return
        super().paint(painter, option, index)

    def sizeHint(self, option, index):
        if self._separator(index):
            return QSize(0, 9)
        s = super().sizeHint(option, index)
        return QSize(s.width(), max(s.height(), 28))


def styled_combo(width: int) -> QComboBox:
    c = QComboBox()
    c.setItemDelegate(ComboDelegate(c))
    c.setFixedWidth(width)
    return c


class PresetCombo(QComboBox):
    """Choose a run's preset. The last entries create a new preset or open the preset manager."""
    NEW, MANAGE = "new", "manage"
    picked = Signal(object)   # preset id, or None for no preset

    def __init__(self, store: Store, ctl: Controller, width=160):
        super().__init__()
        self.store, self.ctl = store, ctl
        self._current: int | None = None
        self.setItemDelegate(ComboDelegate(self))
        self.setFixedWidth(width)
        self.setToolTip("Preset: groups seeds played with the same settings, so Stats can compare them")
        self.activated.connect(self._activated)
        ctl.presets_changed.connect(self.refill)
        self.refill()

    def refill(self):
        self.blockSignals(True)
        self.clear()
        self.addItem("No preset", None)
        for p in self.store.list_presets():
            self.addItem(p["name"], p["id"])
        self.insertSeparator(self.count())
        self.addItem("New preset…", self.NEW)
        self.addItem("Manage presets…", self.MANAGE)
        self.blockSignals(False)
        self.set_preset(self._current)

    def set_preset(self, preset_id: int | None):
        i = self.findData(preset_id) if preset_id is not None else 0
        self._current = preset_id if i >= 0 else None
        self.setCurrentIndex(max(i, 0))

    def _activated(self, i):
        data = self.itemData(i)
        if data == self.NEW:
            self.set_preset(self._current)
            name, ok = QInputDialog.getText(self, "New preset", "Preset name (for example FF4 or 1 Hour):")
            if ok and name.strip():
                pid = self.store.create_preset(name)
                self.ctl.presets_edited()
                self._pick(pid)
        elif data == self.MANAGE:
            self.set_preset(self._current)
            PresetManager(self.store, self.ctl, self.window()).exec()
        elif data != self._current:
            self._pick(data)

    def _pick(self, preset_id):
        self.set_preset(preset_id)
        self.picked.emit(preset_id)


class PresetManager(QDialog):
    """Add, rename and delete presets. Deleting one keeps its runs; they just lose the preset."""

    def __init__(self, store: Store, ctl: Controller, parent=None):
        super().__init__(parent)
        self.store, self.ctl = store, ctl
        self.setWindowTitle("Presets")
        self.resize(380, 400)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)
        lay.addWidget(label("Presets", 15, TEXT, DISPLAY, QFont.Weight.Bold))
        hint = label("Group seeds played with the same settings, then compare them in Stats.", 9.5, MUTED)
        hint.setWordWrap(True)
        lay.addWidget(hint)
        self.list = QListWidget()
        self.list.setItemDelegate(VectorTextDelegate(self.list))
        self.list.setAlternatingRowColors(True)
        self.list.setFont(font(BODY, 10.5))
        self.list.itemDoubleClicked.connect(lambda _it: self._rename())
        lay.addWidget(self.list, 1)
        row = QHBoxLayout()
        for text, fn, name in (("New", self._new, ""), ("Rename", self._rename, ""), ("Delete", self._delete, "danger")):
            b = QPushButton(text)
            b.setObjectName(name)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch()
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        row.addWidget(close)
        lay.addLayout(row)
        self._fill()

    def _fill(self, select: int | None = None):
        counts = self.store.preset_run_counts()
        self.list.clear()
        for p in self.store.list_presets():
            n = counts.get(p["id"], 0)
            it = QListWidgetItem(f"{p['name']}   ·   {n} run{'s' if n != 1 else ''}")
            it.setData(Qt.ItemDataRole.UserRole, (p["id"], p["name"], n))
            self.list.addItem(it)
            if p["id"] == select:
                self.list.setCurrentItem(it)

    def _selected(self):
        it = self.list.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it else None

    def _new(self):
        name, ok = QInputDialog.getText(self, "New preset", "Preset name (for example FF4 or 1 Hour):")
        if ok and name.strip():
            pid = self.store.create_preset(name)
            self.ctl.presets_edited()
            self._fill(pid)

    def _rename(self):
        sel = self._selected()
        if not sel:
            return
        pid, old, _n = sel
        name, ok = QInputDialog.getText(self, "Rename preset", "New name:", text=old)
        if not ok or not name.strip() or name.strip() == old:
            return
        if not self.store.rename_preset(pid, name):
            QMessageBox.warning(self, "Rename preset", f"There's already a preset called \"{name.strip()}\".")
            return
        self.ctl.presets_edited()
        self._fill(pid)

    def _delete(self):
        sel = self._selected()
        if not sel:
            return
        pid, name, n = sel
        kept = f" Its {n} run{'s' if n != 1 else ''} will be kept without a preset." if n else ""
        if QMessageBox.question(self, "Delete preset", f"Delete the preset \"{name}\"?{kept}") \
                == QMessageBox.StandardButton.Yes:
            self.store.delete_preset(pid)
            self.ctl.presets_edited(deleted=pid)
            self._fill()


# ------------------------------------------------------------------ live tab
class LiveTab(QWidget):
    def __init__(self, ctl: Controller, store: Store):
        super().__init__()
        self.ctl, self.store = ctl, store
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 18)
        root.setSpacing(14)

        self.ribbon = RouteRibbon(52)
        root.addWidget(self.ribbon)

        split = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(split, 1)

        left = panel()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(14, 12, 14, 12)
        top = QHBoxLayout()
        top.addWidget(label("Route", 12, TEXT, DISPLAY, QFont.Weight.DemiBold))
        top.addStretch()
        self.auto = QCheckBox("Auto-start on new game")
        self.auto.setChecked(ctl.auto_start)
        self.auto.toggled.connect(ctl.set_auto_start)
        top.addWidget(self.auto)
        top.addSpacing(12)
        self.keyblades = QCheckBox("Track keyblades")
        self.keyblades.setToolTip("Show keyblade pickups in the live route. They never count as checks.")
        self.keyblades.setChecked(ctl.track_keyblades)
        self.keyblades.toggled.connect(ctl.set_track_keyblades)
        top.addWidget(self.keyblades)
        top.addSpacing(12)
        self.levels = QCheckBox("Show level-ups")
        self.levels.toggled.connect(self._toggle_levels)
        top.addWidget(self.levels)
        ll.addLayout(top)
        self.tree = RouteTree()
        self.tree.event_filter = ctl.event_visible
        ll.addWidget(self.tree, 1)
        self.empty = label("Start a run and your route will build up here, world by world.", 10.5, MUTED)
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setWordWrap(True)
        ll.addWidget(self.empty)
        split.addWidget(left)

        # current world card
        right = panel()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(20, 16, 20, 16)
        rl.setSpacing(4)
        self.you_are_in = label("You are in", 9.5, MUTED)
        rl.addWidget(self.you_are_in)
        wrow = QHBoxLayout()
        wrow.setSpacing(12)
        self.world_icon = QLabel()
        self.world_icon.setFixedSize(46, 46)
        self.world_icon.setStyleSheet("background:transparent;")
        wrow.addWidget(self.world_icon)
        self.world = label("—", 22, TEXT, DISPLAY, QFont.Weight.Bold)
        self.world.setWordWrap(True)
        wrow.addWidget(self.world, 1)
        rl.addLayout(wrow)
        self.bar = QFrame()
        self.bar.setFixedHeight(4)
        rl.addWidget(self.bar)
        rl.addSpacing(10)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        self.stat = {}
        # Right column: this run's total in the world above your average total, so they compare at a glance
        for i, (key, cap) in enumerate([("visit", "This visit"), ("total", "In this world, this run"),
                                        ("deaths", "Deaths here"), ("avg", "Your average total here")]):
            box = QFrame()
            box.setObjectName("statbox")
            bl = QVBoxLayout(box)
            bl.setContentsMargins(12, 8, 12, 9)
            bl.setSpacing(1)
            cap_l = label(cap, 9.5, MUTED)
            cap_l.setFixedHeight(cap_l.fontMetrics().height())
            bl.addWidget(cap_l)
            v = label("—", 17, TEXT, DISPLAY, QFont.Weight.DemiBold)
            v.setTextFormat(Qt.TextFormat.PlainText)   # rich text uses a different baseline
            v.setFixedHeight(v.fontMetrics().height())
            v.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(10)
            row.addWidget(v)
            if key == "avg":
                # the +/- difference sits beside the average, on the same line box
                self.delta = label("", 12, GOOD, DISPLAY, QFont.Weight.DemiBold)
                self.delta.setTextFormat(Qt.TextFormat.PlainText)
                self.delta.setFixedHeight(v.fontMetrics().height())
                self.delta.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)
                self.delta.setContentsMargins(0, 0, 0, v.fontMetrics().descent() - self.delta.fontMetrics().descent())
                row.addWidget(self.delta)
            row.addStretch()
            bl.addLayout(row)
            bl.addStretch()
            grid.addWidget(box, i // 2, i % 2)
            self.stat[key] = v
        rl.addLayout(grid)
        rl.addSpacing(14)

        nh = QHBoxLayout()
        nh.addWidget(label("World Notes", 10.5, TEXT, DISPLAY, QFont.Weight.DemiBold))
        nh.addStretch()
        rl.addLayout(nh)
        self.note = QPlainTextEdit()
        self.note.setPlaceholderText("Things to remember here...")
        self.note.textChanged.connect(self._note_edited)
        rl.addWidget(self.note, 1)
        self._note_world = None
        self._note_dirty = False
        self._note_timer = QTimer(self, singleShot=True, interval=600, timeout=self._save_note)
        ctl.note_changed.connect(self._note_changed_elsewhere)
        split.addWidget(right)
        split.setSizes([640, 420])

        ctl.run_changed.connect(self.rebuild)
        ctl.events_added.connect(lambda _e: self.rebuild())
        ctl.filters_changed.connect(self.rebuild)
        ctl.ticked.connect(self._tick)
        self.rebuild()

    def _toggle_levels(self, on):
        self.tree.show_levels = on
        self.rebuild()

    def rebuild(self):
        rec = self.ctl.recorder
        has = rec is not None and bool(rec.run.segments)
        self.empty.setVisible(not has)
        self.tree.setVisible(has)
        if rec:
            self.tree.set_run(rec.run)
            self._tick(self.ctl.clock())
        else:
            self.tree.clear()
            self.ribbon.set_run([], 1)
            self._set_world(None)

    def _set_world(self, world):
        self.world.setText(world or "Not in a run")
        self.you_are_in.setVisible(bool(world))
        if not world:  # no run: clear the card
            for k, v in (("visit", "0:00"), ("total", "0:00"), ("deaths", "0"), ("avg", "—")):
                self.stat[k].setText(v)
            self.stat["avg"].setStyleSheet(f"color:{TEXT}; background:transparent;")
            self.delta.setText("")
        self.world_icon.setVisible(bool(world))
        if world:
            pm = world_pixmap(world, 46 * 2)
            pm.setDevicePixelRatio(2)
            self.world_icon.setPixmap(pm)
        self.bar.setStyleSheet(f"background:{qss_gradient(world) if world else LINE}; border-radius:2px;")
        if world != self._note_world:
            self._save_note()
            self._note_world = world
            self._reload_note()
            self.note.setEnabled(bool(world))

    def _tick(self, t):
        rec = self.ctl.recorder
        if not rec or not rec.current:
            return
        run = rec.run
        self.ribbon.set_run(run.segments, t, live=True)
        self.tree.refresh_last_time()
        cur = rec.current
        self._set_world(cur.world)
        total = world_totals(run.segments).get(cur.world, 0)
        self.stat["visit"].setText(fmt(cur.end - cur.start))
        self.stat["total"].setText(fmt(total))
        deaths = sum(s.deaths for s in run.segments if s.world == cur.world)
        self.stat["deaths"].setText(str(deaths))
        avg = self.ctl.world_avgs.get(cur.world)
        if avg:
            d = total - avg
            self.stat["avg"].setText(fmt(avg))
            self.stat["avg"].setStyleSheet(f"color:{TEXT}; background:transparent;")
            self.delta.setText(f"{'-' if d <= 0 else '+'}{fmt(abs(d))}")
            self.delta.setStyleSheet(f"color:{GOOD if d <= 0 else BAD}; background:transparent;")
        else:
            self.stat["avg"].setText("no data yet")
            self.stat["avg"].setStyleSheet(f"color:{MUTED}; background:transparent;")
            self.delta.setText("")

    def _note_edited(self):
        self._note_dirty = True
        self._note_timer.start()

    def _save_note(self):
        """Only writes when you actually typed here, so it can never clobber edits from the Notes tab."""
        self._note_timer.stop()
        if self._note_world and self._note_dirty:
            self.store.set_world_note(self._note_world, self.note.toPlainText())
            self._note_dirty = False
            self.ctl.note_changed.emit(self._note_world, self)

    def _note_changed_elsewhere(self, world, source):
        if source is not self and world == self._note_world and not self._note_dirty:
            self._reload_note()

    def _reload_note(self):
        self.note.blockSignals(True)
        self.note.setPlainText(self.store.world_note(self._note_world) if self._note_world else "")
        self.note.blockSignals(False)


# ------------------------------------------------------------------ history tab
class HistoryTab(QWidget):
    def __init__(self, store: Store, ctl: Controller):
        super().__init__()
        self.store = store
        self.ctl = ctl
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget()
        outer.addWidget(self.stack)

        # page 0: nothing recorded yet
        empty = QWidget()
        el = QVBoxLayout(empty)
        el.setContentsMargins(18, 16, 18, 18)
        ep = panel()
        epl = QVBoxLayout(ep)
        epl.addStretch(2)
        art = QLabel()
        pm = world_pixmap("General", 160)
        pm.setDevicePixelRatio(2)
        art.setPixmap(pm)
        art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        art.setStyleSheet("background:transparent;")
        epl.addWidget(art)
        epl.addSpacing(14)
        t = label("No runs yet", 20, TEXT, DISPLAY, QFont.Weight.Bold)
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        epl.addWidget(t)
        sub = label("Every run you track lands here with its full route, times and notes.\n"
                    "Start a new seed and RE:Trace will pick it up automatically.", 10.5, MUTED)
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        epl.addWidget(sub)
        epl.addStretch(3)
        el.addWidget(ep)
        self.stack.addWidget(empty)

        # page 1: run list + details
        content = QWidget()
        self.stack.addWidget(content)
        root = QHBoxLayout(content)
        root.setContentsMargins(18, 16, 18, 18)
        root.setSpacing(14)

        lp = panel()
        ll = QVBoxLayout(lp)
        ll.setContentsMargins(10, 12, 10, 10)
        ll.addWidget(label("  Past runs", 12, TEXT, DISPLAY, QFont.Weight.DemiBold))
        self.list = QListWidget()
        self.list.setAlternatingRowColors(True)
        self.list.currentRowChanged.connect(self._show)
        ll.addWidget(self.list, 1)
        lp.setFixedWidth(360)
        root.addWidget(lp)

        rp = panel()
        rl = QVBoxLayout(rp)
        rl.setContentsMargins(16, 14, 16, 14)
        rl.setSpacing(10)
        head = QHBoxLayout()
        self.title = label("", 15, TEXT, DISPLAY, QFont.Weight.Bold)
        head.addWidget(self.title)
        head.addStretch()
        self.preset = PresetCombo(store, ctl, 150)
        self.preset.picked.connect(self._set_preset)
        head.addWidget(self.preset)
        self.seed = QLineEdit()
        self.seed.setPlaceholderText("Seed name / hash")
        self.seed.setFixedWidth(170)
        self.seed.editingFinished.connect(lambda: self._set("seed", self.seed.text()))
        head.addWidget(self.seed)
        self.export = QPushButton("Export")
        self.export.setToolTip("Save this run as a .retrace file to share with other racers")
        self.export.clicked.connect(self._export)
        head.addWidget(self.export)
        self.delete = QPushButton("Delete run")
        self.delete.setObjectName("danger")
        self.delete.clicked.connect(self._delete)
        head.addWidget(self.delete)
        rl.addLayout(head)
        self.summary = label("", 10, MUTED)
        rl.addWidget(self.summary)
        self.ribbon = RouteRibbon(46)
        rl.addWidget(self.ribbon)
        self.tree = RouteTree()
        self.tree.show_levels = True   # History always shows the full record, including keyblades and level-ups
        self.tree.setAlternatingRowColors(True)
        self.bars = WorldBars("No world time recorded in this run.")
        bars = QScrollArea()
        bars.setWidget(self.bars)
        bars.setWidgetResizable(True)
        bars.setFrameShape(QFrame.Shape.NoFrame)
        bars.setStyleSheet("background:transparent;")
        self.worlds = data_table(["World", "Time", "Visits", "Deaths", "Checks"])
        self.ms = milestone_table(["At"])
        self.views = QTabWidget()   # this run's own route, world times and splits, like the Stats panels
        self.views.setDocumentMode(True)
        self.views.tabBar().setFont(font(DISPLAY, 10))
        self.views.tabBar().setDrawBase(False)
        for w, name in ((self.tree, "Route"), (bars, "Time per world"), (self.worlds, "World breakdown"),
                        (self.ms, "Milestone splits")):
            self.views.addTab(w, name)
        rl.addWidget(self.views, 3)
        rl.addWidget(label("Run notes", 10.5, TEXT, DISPLAY, QFont.Weight.DemiBold))
        self.notes = QPlainTextEdit()
        self.notes.setPlaceholderText("What went well, what cost time, what to practice next…")
        self.notes.setMaximumHeight(110)
        self.notes.textChanged.connect(lambda: self._nt.start())
        self._nt = QTimer(self, singleShot=True, interval=600,
                          timeout=lambda: self._set("notes", self.notes.toPlainText()))
        rl.addWidget(self.notes)
        root.addWidget(rp, 1)
        self.detail = rp

        self.runs = []
        ctl.run_changed.connect(self.reload)
        ctl.presets_changed.connect(self.reload)
        self.reload()

    def reload(self):
        cur = self.list.currentRow()
        self.runs = self.store.list_runs()
        self.list.blockSignals(True)
        self.list.clear()
        for r in self.runs:
            d = dt.datetime.fromtimestamp(r["started_at"])
            when = f"{d:%b} {d.day}, {d.hour % 12 or 12}:{d:%M} {d:%p}"
            done = r["status"] == "finished"
            card = QWidget()
            card.setStyleSheet("background:transparent;")
            cl = QVBoxLayout(card)
            cl.setContentsMargins(10, 8, 10, 8)
            cl.setSpacing(3)
            row = QHBoxLayout()
            row.addWidget(label(fmt(r["duration"], True), 12, TEXT if done else MUTED, DISPLAY, QFont.Weight.Bold))
            row.addStretch()
            row.addWidget(label(when, 9.5, MUTED))
            cl.addLayout(row)
            sub = ("Finished" if done else "Unfinished") + (f"  -  {r['seed']}" if r["seed"] else "")
            row = QHBoxLayout()
            row.addWidget(label(sub, 9.5, GOOD if done else MUTED))
            row.addStretch()
            if r["preset"]:
                row.addWidget(label(r["preset"], 9.5, GOLD))
            cl.addLayout(row)
            it = QListWidgetItem()
            it.setSizeHint(QSize(0, card.sizeHint().height() + 16))
            self.list.addItem(it)
            self.list.setItemWidget(it, card)
        self.list.blockSignals(False)
        self.stack.setCurrentIndex(1 if self.runs else 0)
        if self.runs:
            self.list.setCurrentRow(min(max(cur, 0), len(self.runs) - 1))
            self._show(self.list.currentRow())

    def _show(self, row):
        if row < 0 or row >= len(self.runs):
            return
        r = self.runs[row]
        run = self.store.load_run(r["id"])
        self.title.setText(("Finished run" if r["status"] == "finished" else "Unfinished run")
                           + f"  ·  {fmt(r['duration'], True)}")
        checks = sum(1 for e in run.events if is_check(e))
        deaths = sum(1 for e in run.events if e.kind == "death")
        worlds = len({s.world for s in run.segments})
        rta = f"  ·  real time {fmt(run.real_time, True)}" if run.real_time and run.real_time - r["duration"] > 1 else ""
        self.summary.setText(f"{len(run.segments)} visits across {worlds} worlds, "
                             f"{checks} checks, {deaths} deaths{rta}")
        self.ribbon.set_run(run.segments, r["duration"])
        self.tree.set_run(run, expand_last=False)
        worlds = sorted(world_breakdown(run).items(), key=lambda kv: -kv[1]["time"])
        self.bars.set_rows([(w, d["time"]) for w, d in worlds])
        fill_world_table(self.worlds, worlds, lambda d: (fmt(d["time"]),))
        fill_milestone_table(self.ms, [(w, name, fmt(t, True)) for w, name, t in sorted(milestone_splits(run), key=lambda m: m[2])])
        self.preset.set_preset(r["preset_id"])
        for w, v in ((self.seed, r["seed"]), (self.notes, r["notes"])):
            w.blockSignals(True)
            (w.setText if isinstance(w, QLineEdit) else w.setPlainText)(v or "")
            w.blockSignals(False)

    def _set(self, field, value):
        row = self.list.currentRow()
        if 0 <= row < len(self.runs):
            self.store.set_run_field(self.runs[row]["id"], field, value)
            self.runs[row][field] = value

    def _set_preset(self, preset_id):
        row = self.list.currentRow()
        if 0 <= row < len(self.runs):
            self.store.set_run_preset(self.runs[row]["id"], preset_id)
            self.reload()                   # the card shows the new preset
            self.ctl.history_changed.emit()  # Stats and the Live averages regroup

    def _export(self):
        row = self.list.currentRow()
        if not 0 <= row < len(self.runs):
            return
        racer = ask_username(self, self.ctl)
        if not racer:
            return
        run = self.store.export_run(self.runs[row]["id"])
        folder = self.store.setting("export_dir", str(Path.home() / "Desktop"))
        path, _ = QFileDialog.getSaveFileName(self, "Export run", str(Path(folder) / race_file.suggested_name(racer, run)),
                                              f"RE:Trace run (*{race_file.EXTENSION})")
        if not path:
            return
        try:
            race_file.write_file(Path(path), racer, run)
        except OSError as e:
            QMessageBox.warning(self, "Export run", f"Couldn't save the file:\n{e}")
            return
        self.store.set_setting("export_dir", str(Path(path).parent))

    def _delete(self):
        row = self.list.currentRow()
        if row < 0:
            return
        if QMessageBox.question(self, "Delete run", "Delete this run from your history? This can't be undone.") \
                == QMessageBox.StandardButton.Yes:
            self.store.delete_run(self.runs[row]["id"])
            self.reload()
            self.ctl.history_changed.emit()


# ------------------------------------------------------------------ stats tab
class StatsTab(QWidget):
    def __init__(self, store: Store, ctl: Controller):
        super().__init__()
        self.store = store
        self.ctl = ctl
        self._dirty = True
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 18)
        root.setSpacing(14)

        top = QHBoxLayout()
        self.cards = {}
        for key, cap in [("runs", "Runs tracked"), ("finished", "Finished"), ("avg", "Average finish"),
                         ("best", "Best finish")]:
            f = panel()
            fl = QVBoxLayout(f)
            fl.setContentsMargins(16, 10, 16, 10)
            v = label("—", 20, TEXT, DISPLAY, QFont.Weight.Bold)
            fl.addWidget(v)
            fl.addWidget(label(cap, 9.5, MUTED))
            self.cards[key] = v
            top.addWidget(f)
        top.addStretch()
        top.addWidget(label("Preset", 10, MUTED))
        self.preset = styled_combo(170)
        self.preset.setToolTip("Only compare seeds from this preset")
        self.preset.currentIndexChanged.connect(self.reload)
        ctl.presets_changed.connect(self._fill_presets)
        self._fill_presets()
        top.addWidget(self.preset)
        top.addSpacing(12)
        self.finished_only = QCheckBox("Finished runs only")
        self.finished_only.toggled.connect(self.reload)
        top.addWidget(self.finished_only)
        root.addLayout(top)

        split = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(split, 1)

        lp = panel()
        ll = QVBoxLayout(lp)
        ll.setContentsMargins(14, 12, 14, 12)
        ll.addWidget(label("Time per world", 15, TEXT, DISPLAY, QFont.Weight.Bold))
        ll.addWidget(label("Average total time spent in each world per run", 9.5, MUTED))
        self.bars = WorldBars()
        scroll = QScrollArea()
        scroll.setWidget(self.bars)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background:transparent;")
        ll.addWidget(scroll, 1)

        # the per-world table gets its own panel, so the two scroll areas are clearly separate
        tp = panel()
        tl = QVBoxLayout(tp)
        tl.setContentsMargins(14, 12, 14, 12)
        tl.addWidget(label("World breakdown", 12, TEXT, DISPLAY, QFont.Weight.DemiBold))
        tl.addWidget(label("Per-run averages, best and worst times for each world", 9.5, MUTED))
        self.table = data_table(["World", "Runs", "Average", "Best", "Worst", "Visits", "Deaths", "Checks"])
        tl.addWidget(self.table, 1)

        split.addWidget(lp)   # Time per world: the headline, full height on the left

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(14)
        rv.addWidget(tp, 1)

        rp = panel()
        rl = QVBoxLayout(rp)
        rl.setContentsMargins(14, 12, 14, 12)
        rl.addWidget(label("Milestone splits", 12, TEXT, DISPLAY, QFont.Weight.DemiBold))
        rl.addWidget(label("How far into a run you usually reach each milestone", 9.5, MUTED))
        self.ms = milestone_table(["Done", "Average", "Best"])
        rl.addWidget(self.ms, 1)
        rv.addWidget(rp, 1)
        split.addWidget(right)
        split.setStretchFactor(0, 5)
        split.setStretchFactor(1, 6)
        split.setSizes([520, 620])

        ctl.run_changed.connect(self.reload)
        ctl.history_changed.connect(self.reload)
        self.reload()

    def showEvent(self, e):
        super().showEvent(e)
        if self._dirty:
            self.reload()

    def _fill_presets(self):
        """All presets (which includes runs without one), then each preset. Keeps the choice unless it was deleted."""
        keep = self.preset.currentData()
        self.preset.blockSignals(True)
        self.preset.clear()
        self.preset.addItem("All presets", None)
        for p in self.store.list_presets():
            self.preset.addItem(p["name"], p["id"])
        i = self.preset.findData(keep) if keep is not None else 0
        self.preset.setCurrentIndex(max(i, 0))
        self.preset.blockSignals(False)
        if i < 0:
            self.reload()

    def reload(self):
        """A run change while another tab is up only marks the stats stale; showEvent fills them in."""
        if not self.isVisible():
            self._dirty = True
            return
        self._dirty = False
        with perf("StatsTab.reload"):
            self._fill()

    def _fill(self):
        s = self.store.stats(self.finished_only.isChecked(), self.preset.currentData())
        self.cards["runs"].setText(str(s["runs"]))
        self.cards["finished"].setText(str(s["finished"]))
        self.cards["avg"].setText(fmt(s["avg_duration"], True) if s["finished"] else "—")
        self.cards["best"].setText(fmt(s["best_duration"], True) if s["finished"] else "—")
        worlds = sorted(s["worlds"].items(), key=lambda kv: -kv[1]["avg"])
        self.bars.set_rows([(w, d["avg"]) for w, d in worlds])
        self.table.setSortingEnabled(False)
        fill_world_table(self.table, worlds, lambda d: (str(d["runs"]), fmt(d["avg"]), fmt(d["best"]), fmt(d["worst"])))
        fill_milestone_table(self.ms, [(m["world"], m["name"], str(m["count"]), fmt(m["avg"], True), fmt(m["best"], True))
                                       for m in s["milestones"]])


# ------------------------------------------------------------------ race tab
RACER_COLOURS = [GOLD, "#9CCBFF", "#FF9F80", "#C9A2FF", "#FF8FC8", "#7FE3E0", "#F2F28A", "#D6DCF0"]  # no green: that marks "fastest"
GROUP_SHADE = "#1E2849"   # same light blue as alternating rows


class Racer:
    """One run in a race, with what every view needs worked out once."""

    def __init__(self, entry: dict, index: int):
        self.id, self.name, self.data = entry["id"], entry["racer"], entry["run"]
        self.colour = RACER_COLOURS[index % len(RACER_COLOURS)]
        self.run = run_from_dict(self.data)
        self.duration = self.data["duration"]
        self.finished = self.data["status"] == "finished"
        self.worlds = world_breakdown(self.run)
        self.splits = {(w, n): t for w, n, t in milestone_splits(self.run)}


def standings(racers: list[Racer]) -> list[Racer]:
    """Finished runs fastest first, then unfinished ones furthest along first."""
    return sorted(racers, key=lambda r: (not r.finished, r.duration if r.finished else -r.duration))


def delta(t: float, best: float) -> str:
    return "fastest" if t - best < 1 else f"+{fmt(t - best)}"


def close_icon() -> QIcon:
    """A drawn ✕, so it never depends on a symbol font being installed."""
    icon = QIcon()
    for sz in (10, 20, 30):
        pm = QPixmap(sz, sz)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor(MUTED), sz / 7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        m = sz * 0.15
        p.drawLine(QPointF(m, m), QPointF(sz - m, sz - m))
        p.drawLine(QPointF(sz - m, m), QPointF(m, sz - m))
        p.end()
        icon.addPixmap(pm)
    return icon


class RacerRow(QWidget):
    """A racer's name and time beside their route ribbon. Double-click to rename."""
    remove = Signal(object)
    rename = Signal(object)

    def __init__(self, racer: Racer, scale: float):
        super().__init__()
        self.racer = racer
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        bar = QFrame()
        bar.setFixedSize(4, 40)
        bar.setStyleSheet(f"background:{racer.colour}; border-radius:2px;")
        lay.addWidget(bar)
        col = QVBoxLayout()
        col.setSpacing(0)
        name = label("", 11, racer.colour, DISPLAY, QFont.Weight.DemiBold)
        name.setFixedWidth(150)
        name.setText(name.fontMetrics().elidedText(racer.name, Qt.TextElideMode.ElideRight, 150))
        name.setToolTip(f"{racer.name}\nDouble-click to rename")
        col.addWidget(name)
        status = fmt(racer.duration, True) + ("" if racer.finished else "  unfinished")
        col.addWidget(label(status, 9.5, TEXT if racer.finished else MUTED))
        lay.addLayout(col)
        ribbon = RouteRibbon(40)
        ribbon.track = QColor(BG)
        ribbon.set_run(racer.run.segments, scale)
        lay.addWidget(ribbon, 1)
        x = QPushButton()
        x.setIcon(close_icon())
        x.setIconSize(QSize(10, 10))
        x.setObjectName("danger")
        x.setStyleSheet("padding:0;")
        x.setFixedSize(30, 30)
        x.setToolTip("Remove from this race")
        x.clicked.connect(lambda: self.remove.emit(self.racer))
        lay.addWidget(x)

    def mouseDoubleClickEvent(self, e):
        self.rename.emit(self.racer)


class RaceBars(QWidget):
    """Time per world: one bar per racer under each world, all on the same scale."""
    HEAD, ROW, GAP = 28, 24, 10

    def __init__(self):
        super().__init__()
        self.groups = []
        self.racers = []

    def set_racers(self, racers: list[Racer]):
        self.racers = racers
        worlds = {w for r in racers for w in r.worlds}
        longest = {w: max(r.worlds[w]["time"] for r in racers if w in r.worlds) for w in worlds}
        self.groups = [(w, [(r, r.worlds[w]["time"] if w in r.worlds else None) for r in racers])
                       for w in sorted(worlds, key=lambda w: -longest[w])]
        self.max = max(longest.values(), default=1) or 1
        self.setMinimumHeight(sum(self.HEAD + self.ROW * len(racers) + self.GAP for _ in self.groups) + 10)
        self.update()

    def paintEvent(self, _):
        if not self.groups:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        head_f, body_f = font(DISPLAY, 10.5, QFont.Weight.DemiBold), font(BODY, 10)
        p.setFont(body_f)
        fm = p.fontMetrics()
        name_w = max(fm.horizontalAdvance(r.name) for r in self.racers) + 16
        time_w = fm.horizontalAdvance("00:00:00") + 14
        x0 = 30 + name_w
        span = max(40, self.width() - x0 - time_w)
        y = 4
        for w, rows in self.groups:
            pm = world_pixmap(w, 44)
            pm.setDevicePixelRatio(2)
            p.drawPixmap(QPointF(0, y), pm)
            p.setFont(head_f)
            WorldBars._text(p, w, 30, y + 16, QColor(TEXT))
            p.setFont(body_f)
            y += self.HEAD
            times = [t for _r, t in rows if t is not None]
            best = min(times) if times else 0
            for r, t in rows:
                base = y + 12 + (fm.ascent() - fm.descent()) / 2
                WorldBars._text(p, r.name, 30, base, QColor(r.colour))
                if t is None:
                    WorldBars._text(p, "—", x0, base, QColor(MUTED))
                else:
                    bw = span * t / self.max
                    rect = QRectF(x0, y + 4, max(bw, 3), 16)
                    path = QPainterPath()
                    path.addRoundedRect(rect, 5, 5)
                    p.fillPath(path, gradient(w, rect))
                    win = len(times) > 1 and t - best < 1
                    WorldBars._text(p, fmt(t), x0 + bw + 8, base, QColor(GOOD if win else MUTED))
                y += self.ROW
            y += self.GAP
        p.end()


class PickRunsDialog(QDialog):
    """Choose your own runs to add to a race. Runs on the race's seed are listed first."""

    def __init__(self, store: Store, seeds: set[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add my runs")
        self.resize(460, 480)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)
        lay.addWidget(label("Add my runs", 15, TEXT, DISPLAY, QFont.Weight.Bold))
        lay.addWidget(label("Pick one or more runs from your history (Ctrl-click for several).", 9.5, MUTED))
        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list.setItemDelegate(VectorTextDelegate(self.list))
        self.list.setAlternatingRowColors(True)
        self.list.setFont(font(BODY, 10.5))
        runs = sorted(store.list_runs(), key=lambda r: r["seed"] not in seeds)   # stable: newest first within each
        for r in runs:
            d = dt.datetime.fromtimestamp(r["started_at"])
            parts = [fmt(r["duration"], True), "Finished" if r["status"] == "finished" else "Unfinished",
                     r["seed"], r["preset"], f"{d:%b} {d.day}"]
            it = QListWidgetItem("   ·   ".join(p for p in parts if p))
            it.setData(Qt.ItemDataRole.UserRole, r["id"])
            if r["seed"] and r["seed"] in seeds:
                it.setForeground(QBrush(QColor(GOLD)))
                it.setToolTip("Same seed as this race")
            self.list.addItem(it)
        self.list.itemDoubleClicked.connect(lambda _it: self.accept())
        lay.addWidget(self.list, 1)
        row = QHBoxLayout()
        row.addStretch()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        add = QPushButton("Add to race")
        add.setObjectName("primary")
        add.clicked.connect(self.accept)
        row.addWidget(cancel)
        row.addWidget(add)
        lay.addLayout(row)

    def run_ids(self) -> list[int]:
        return [it.data(Qt.ItemDataRole.UserRole) for it in self.list.selectedItems()]


class RaceTab(QWidget):
    def __init__(self, store: Store, ctl: Controller):
        super().__init__()
        self.store, self.ctl = store, ctl
        self.races: list[dict] = []
        self.racers: list[Racer] = []
        self.setAcceptDrops(True)   # drop .retrace files anywhere on the tab
        root = QHBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 18)
        root.setSpacing(14)

        # left: your name + saved races
        lp = panel()
        ll = QVBoxLayout(lp)
        ll.setContentsMargins(10, 12, 10, 10)
        ll.setSpacing(6)
        ll.addWidget(label("  Your racer name", 10.5, TEXT, DISPLAY, QFont.Weight.DemiBold))
        self.username = QLineEdit(ctl.username)
        self.username.setPlaceholderText("Shown to other racers")
        self.username.setToolTip("Saved into every run you export, so other racers can see who ran it")
        self.username.editingFinished.connect(lambda: ctl.set_username(self.username.text()))
        ctl.username_changed.connect(lambda: self.username.setText(ctl.username))
        ll.addWidget(self.username)
        ll.addSpacing(8)
        races_head = QHBoxLayout()
        races_head.addWidget(label("  Races", 12, TEXT, DISPLAY, QFont.Weight.DemiBold))
        races_head.addStretch()
        new = QPushButton("New race")
        new.setObjectName("primary")
        new.clicked.connect(self._new_race)
        races_head.addWidget(new)
        ll.addLayout(races_head)
        self.list = QListWidget()
        self.list.setAlternatingRowColors(True)
        self.list.currentRowChanged.connect(self._show)
        ll.addWidget(self.list, 1)
        lp.setFixedWidth(300)
        root.addWidget(lp)

        # right: empty state, or the race
        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)
        ep = panel()
        epl = QVBoxLayout(ep)
        epl.addStretch(2)
        t = label("Race other players", 20, TEXT, DISPLAY, QFont.Weight.Bold)
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        epl.addWidget(t)
        sub = label("Make a race, then add your own runs and import .retrace files from other racers\n"
                    "who played the same seed. Export your runs from the History tab.", 10.5, MUTED)
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        epl.addWidget(sub)
        epl.addSpacing(12)
        b = QPushButton("New race")
        b.setObjectName("primary")
        b.clicked.connect(self._new_race)
        brow = QHBoxLayout()
        brow.addStretch()
        brow.addWidget(b)
        brow.addStretch()
        epl.addLayout(brow)
        epl.addStretch(3)
        self.stack.addWidget(ep)

        rp = panel()
        rl = QVBoxLayout(rp)
        rl.setContentsMargins(16, 14, 16, 14)
        rl.setSpacing(10)
        head = QHBoxLayout()
        self.title = label("", 15, TEXT, DISPLAY, QFont.Weight.Bold)
        head.addWidget(self.title)
        head.addStretch()
        for text, fn, name, tip in (("Add my run…", self._add_mine, "", "Add runs from your own history"),
                                    ("Import .retrace…", self._import, "", "Add runs other racers sent you"),
                                    ("Rename", self._rename_race, "", ""),
                                    ("Delete race", self._delete_race, "danger", "")):
            btn = QPushButton(text)
            btn.setObjectName(name)
            btn.setToolTip(tip)
            btn.clicked.connect(fn)
            head.addWidget(btn)
        rl.addLayout(head)
        self.hint = label("", 10, MUTED)
        self.hint.setWordWrap(True)
        rl.addWidget(self.hint)

        self.rows = QWidget()
        self.rows.setStyleSheet("background:transparent;")
        self.rows_lay = QVBoxLayout(self.rows)
        self.rows_lay.setContentsMargins(0, 0, 6, 0)
        self.rows_lay.setSpacing(8)
        self.rows_scroll = QScrollArea()
        self.rows_scroll.setWidget(self.rows)
        self.rows_scroll.setWidgetResizable(True)
        self.rows_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.rows_scroll.setStyleSheet("background:transparent;")
        rl.addWidget(self.rows_scroll)

        self.summary = data_table(["Racer", "Status", "Time", "Behind", "Real time", "Visits", "Worlds", "Checks",
                                   "Deaths", "Seed", "Preset"])
        self.routes = QWidget()
        self.routes.setStyleSheet("background:transparent;")
        self.routes_lay = QHBoxLayout(self.routes)
        self.routes_lay.setContentsMargins(0, 6, 0, 0)
        self.routes_lay.setSpacing(12)
        routes = QScrollArea()
        routes.setWidget(self.routes)
        routes.setWidgetResizable(True)
        routes.setFrameShape(QFrame.Shape.NoFrame)
        routes.setStyleSheet("background:transparent;")
        self.bars = RaceBars()
        bars = QScrollArea()
        bars.setWidget(self.bars)
        bars.setWidgetResizable(True)
        bars.setFrameShape(QFrame.Shape.NoFrame)
        bars.setStyleSheet("background:transparent;")
        self.worlds = data_table(["World", "Racer", "Time", "Behind", "Visits", "Deaths", "Checks"])
        self.worlds.setAlternatingRowColors(False)   # shaded per world instead, so each group reads as one
        self.worlds.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.worlds.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.ms = milestone_table([])
        self.views = QTabWidget()
        self.views.setDocumentMode(True)
        self.views.tabBar().setFont(font(DISPLAY, 10))
        self.views.tabBar().setDrawBase(False)
        for w, name in ((self.summary, "Summary"), (routes, "Route"), (bars, "Time per world"),
                        (self.worlds, "World breakdown"), (self.ms, "Milestone splits")):
            self.views.addTab(w, name)
        rl.addWidget(self.views, 1)
        self.stack.addWidget(rp)
        self.reload()

    # ---- race list
    def _race_id(self) -> int | None:
        row = self.list.currentRow()
        return self.races[row]["id"] if 0 <= row < len(self.races) else None

    def reload(self, select: int | None = None):
        select = select if select is not None else self._race_id()
        self.races = self.store.list_races()
        self.list.blockSignals(True)
        self.list.clear()
        for r in self.races:
            d = dt.datetime.fromtimestamp(r["created_at"])
            card = QWidget()
            card.setStyleSheet("background:transparent;")
            cl = QVBoxLayout(card)
            cl.setContentsMargins(10, 8, 10, 8)
            cl.setSpacing(3)
            name = label("", 12, TEXT, DISPLAY, QFont.Weight.Bold)
            name.setText(name.fontMetrics().elidedText(r["name"], Qt.TextElideMode.ElideRight, 240))
            cl.addWidget(name)
            n = r["racers"]
            cl.addWidget(label(f"{n} racer{'s' if n != 1 else ''}  -  {d:%b} {d.day}", 9.5, MUTED))
            it = QListWidgetItem()
            it.setSizeHint(QSize(0, card.sizeHint().height() + 16))
            self.list.addItem(it)
            self.list.setItemWidget(it, card)
        self.list.blockSignals(False)
        ids = [r["id"] for r in self.races]
        self.list.setCurrentRow(ids.index(select) if select in ids else (0 if ids else -1))
        self._show(self.list.currentRow())

    def _new_race(self):
        d = dt.datetime.now()
        name, ok = QInputDialog.getText(self, "New race", "Race name:", text=f"Race {d:%b} {d.day}")
        if ok and name.strip():
            self.reload(self.store.create_race(name))

    def _rename_race(self):
        rid = self._race_id()
        if rid is None:
            return
        old = self.races[self.list.currentRow()]["name"]
        name, ok = QInputDialog.getText(self, "Rename race", "Race name:", text=old)
        if ok and name.strip():
            self.store.rename_race(rid, name)
            self.reload()

    def _delete_race(self):
        rid = self._race_id()
        if rid is not None and QMessageBox.question(
                self, "Delete race", "Delete this race? Your own runs stay in History.") == QMessageBox.StandardButton.Yes:
            self.store.delete_race(rid)
            self.reload()

    # ---- adding racers
    def _add_mine(self):
        rid = self._race_id()
        if rid is None:
            return
        dlg = PickRunsDialog(self.store, {r.data["seed"] for r in self.racers if r.data["seed"]}, self)
        if dlg.exec() != QDialog.DialogCode.Accepted or not dlg.run_ids():
            return
        racer = ask_username(self, self.ctl)
        if not racer:
            return
        skipped = sum(self.store.add_race_entry(rid, racer, self.store.export_run(i), "local") is None
                      for i in dlg.run_ids())
        self.reload()
        if skipped:
            QMessageBox.information(self, "Add my run", f"{skipped} run{'s were' if skipped != 1 else ' was'} "
                                                        "already in this race.")

    def _import(self):
        if self._race_id() is None:
            return
        folder = self.store.setting("import_dir", str(Path.home() / "Downloads"))
        paths, _ = QFileDialog.getOpenFileNames(self, "Import runs", folder,
                                                f"RE:Trace runs (*{race_file.EXTENSION});;All files (*)")
        if paths:
            self.store.set_setting("import_dir", str(Path(paths[0]).parent))
            self.import_files([Path(p) for p in paths])

    def import_files(self, paths: list[Path]):
        rid = self._race_id()
        if rid is None:   # dropped files with no race yet: start one
            rid = self.store.create_race(f"Race {dt.datetime.now():%b} {dt.datetime.now().day}")
            self.reload(rid)
        problems = []
        for path in paths:
            try:
                racer, run = race_file.read_file(path)
            except race_file.RaceFileError as e:
                problems.append(f"{path.name}: {e}")
                continue
            if self.store.add_race_entry(rid, racer, run, "import") is None:
                problems.append(f"{path.name}: {racer}'s run is already in this race.")
        self.reload()
        if problems:
            QMessageBox.warning(self, "Import runs", "\n".join(problems))

    def dragEnterEvent(self, e):
        if any(u.toLocalFile().lower().endswith(race_file.EXTENSION) for u in e.mimeData().urls()):
            e.acceptProposedAction()

    def dropEvent(self, e):
        paths = [Path(u.toLocalFile()) for u in e.mimeData().urls()
                 if u.toLocalFile().lower().endswith(race_file.EXTENSION)]
        if paths:
            self.import_files(paths)

    # ---- racers
    def _remove_racer(self, racer: Racer):
        if QMessageBox.question(self, "Remove racer", f"Remove {racer.name}'s run from this race?") \
                == QMessageBox.StandardButton.Yes:
            self.store.remove_race_entry(racer.id)
            self.reload()

    def _rename_racer(self, racer: Racer):
        name, ok = QInputDialog.getText(self, "Rename racer", "Racer name:", text=racer.name)
        if ok and name.strip():
            self.store.rename_racer(racer.id, name)
            self.reload()

    # ---- the race view
    def _show(self, row):
        if not 0 <= row < len(self.races):
            self.stack.setCurrentIndex(0)
            return
        self.stack.setCurrentIndex(1)
        race = self.races[row]
        self.title.setText(race["name"])
        self.racers = [Racer(e, i) for i, e in enumerate(self.store.race_entries(race["id"]))]
        racers = standings(self.racers)
        seeds = sorted({r.data["seed"] for r in racers if r.data["seed"]})
        if not racers:
            self.hint.setText("Add your own runs or import .retrace files to start comparing. "
                              "You can also drop .retrace files onto this tab.")
        elif len(seeds) > 1:
            self.hint.setText(f"Heads up: these runs are on different seeds ({', '.join(seeds)}).")
        else:
            self.hint.setText((f"Seed {seeds[0]}  ·  " if seeds else "") + "Double-click a racer to rename them.")
        self.hint.setStyleSheet(f"color:{GOLD if len(seeds) > 1 else MUTED}; background:transparent;")
        self._fill_rows(racers)
        self._fill_summary(racers)
        self._fill_routes(racers)
        self.bars.set_racers(racers)
        self._fill_worlds(racers)
        self._fill_splits(racers)

    @staticmethod
    def _clear(lay):
        while lay.count():
            w = lay.takeAt(0).widget()
            if w:
                w.hide()            # gone right away, not just when the deferred delete runs
                w.setParent(None)
                w.deleteLater()

    def _fill_rows(self, racers):
        self._clear(self.rows_lay)
        scale = max((r.duration for r in racers), default=1) or 1   # one scale, so the ribbons line up
        for r in racers:
            row = RacerRow(r, scale)
            row.remove.connect(self._remove_racer)
            row.rename.connect(self._rename_racer)
            self.rows_lay.addWidget(row)
        self.rows_scroll.setVisible(bool(racers))
        self.rows_scroll.setFixedHeight(min(len(racers), 5) * 48)
        self.views.setVisible(bool(racers))

    def _fill_summary(self, racers):
        best = min((r.duration for r in racers if r.finished), default=None)
        t = self.summary
        with bulk_fill(t):
            t.setRowCount(len(racers))
            for i, r in enumerate(racers):
                ev = r.run.events
                behind = delta(r.duration, best) if r.finished and best is not None else "—"
                vals = ["Finished" if r.finished else "Unfinished", fmt(r.duration, True), behind,
                        fmt(r.run.real_time, True) if r.run.real_time else "—", str(len(r.run.segments)),
                        str(len(r.worlds)), str(sum(1 for e in ev if is_check(e))),
                        str(sum(1 for e in ev if e.kind == "death")), r.data["seed"] or "—", r.data["preset"] or "—"]
                t.setItem(i, 0, table_cell(r.name, colour=r.colour))
                for c, v in enumerate(vals, 1):
                    colour = (GOOD if r.finished else MUTED) if c == 1 else (GOOD if v == "fastest" else None)
                    t.setItem(i, c, table_cell(v, 0, colour))

    def _fill_routes(self, racers):
        self._clear(self.routes_lay)
        for r in racers:
            col = QFrame()
            col.setObjectName("statbox")
            col.setMinimumWidth(330)
            cl = QVBoxLayout(col)
            cl.setContentsMargins(10, 8, 10, 8)
            head = QHBoxLayout()
            name = label("", 11, r.colour, DISPLAY, QFont.Weight.DemiBold)
            name.setText(name.fontMetrics().elidedText(r.name, Qt.TextElideMode.ElideRight, 200))
            name.setToolTip(r.name)
            head.addWidget(name)
            head.addStretch()
            head.addWidget(label(fmt(r.duration, True), 11, TEXT if r.finished else MUTED, DISPLAY,
                                 QFont.Weight.DemiBold))
            cl.addLayout(head)
            tree = RouteTree()
            tree.show_levels = True
            tree.setAlternatingRowColors(True)
            tree.setStyleSheet("background:transparent;")
            tree.set_run(r.run, expand_last=False)
            cl.addWidget(tree, 1)
            self.routes_lay.addWidget(col, 1)
        enable_smooth_scrolling(self.routes)

    def _fill_worlds(self, racers):
        worlds = {w for r in racers for w in r.worlds}
        longest = {w: max(r.worlds[w]["time"] for r in racers if w in r.worlds) for w in worlds}
        t = self.worlds
        rows = []
        for g, w in enumerate(sorted(worlds, key=lambda w: -longest[w])):
            present = [r for r in racers if w in r.worlds]
            best = min(r.worlds[w]["time"] for r in present)
            for k, r in enumerate(sorted(present, key=lambda r: r.worlds[w]["time"])):
                rows.append((g, w if k == 0 else "", r, r.worlds[w], best))
        with bulk_fill(t):
            t.setRowCount(len(rows))
            for i, (g, w, r, d, best) in enumerate(rows):
                name = table_cell(w)
                if w:
                    name.setIcon(swatch(w))
                cells = [name, table_cell(r.name, colour=r.colour)]
                behind = delta(d["time"], best) if len(racers) > 1 else ""
                for c, v in enumerate([fmt(d["time"]), behind, str(d["visits"]), str(d["deaths"]), str(d["checks"])], 2):
                    colour = GOOD if v == "fastest" else (BAD if c == 5 and d["deaths"] else None)
                    cells.append(table_cell(v, 0, colour))
                for c, it in enumerate(cells):
                    if g % 2:
                        it.setBackground(QBrush(QColor(GROUP_SHADE)))
                    t.setItem(i, c, it)

    def _fill_splits(self, racers):
        t = self.ms
        t.setColumnCount(2 + len(racers))
        t.setHorizontalHeaderLabels(["Milestone", ""] + [r.name for r in racers])
        head = t.horizontalHeader()
        head.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        head.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        head.setMinimumSectionSize(34)
        for c in range(2, t.columnCount()):
            head.setSectionResizeMode(c, QHeaderView.ResizeMode.Interactive)
            t.setColumnWidth(c, max(96, min(170, head.fontMetrics().horizontalAdvance(racers[c - 2].name) + 28)))
        keys = {k for r in racers for k in r.splits}
        first = {k: min(r.splits[k] for r in racers if k in r.splits) for k in keys}
        rows, wins = [], []
        for k in sorted(keys, key=lambda k: first[k]):
            times = [r.splits.get(k) for r in racers]
            contested = sum(x is not None for x in times) > 1
            rows.append((*k, *[fmt(x, True) if x is not None else "—" for x in times]))
            wins.append([contested and x is not None and x - first[k] < 1 for x in times])
        fill_milestone_table(t, rows)
        for i, row_wins in enumerate(wins):
            for c, won in enumerate(row_wins, 2):
                if won:
                    t.item(i, c).setForeground(QBrush(QColor(GOOD)))


# ------------------------------------------------------------------ notes tab
class NotesTab(QWidget):
    GENERAL = "General"

    def __init__(self, store: Store, ctl: Controller):
        super().__init__()
        self.store = store
        self.ctl = ctl
        self._dirty = False
        ctl.note_changed.connect(self._changed_elsewhere)
        root = QHBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 18)
        root.setSpacing(14)
        lp = panel()
        ll = QVBoxLayout(lp)
        ll.setContentsMargins(10, 12, 10, 10)
        ll.addWidget(label("  Practice notes", 12, TEXT, DISPLAY, QFont.Weight.DemiBold))
        self.list = QListWidget()
        self.list.setIconSize(QSize(20, 20))
        self.list.setItemDelegate(VectorTextDelegate(self.list))
        self.list.setFont(font(BODY, 10.5))
        for w in [self.GENERAL] + gd.WORLD_ORDER:
            it = QListWidgetItem(swatch(w), w)
            self.list.addItem(it)
        self.list.currentTextChanged.connect(self._load)
        ll.addWidget(self.list, 1)
        lp.setFixedWidth(280)
        root.addWidget(lp)
        rp = panel()
        rl = QVBoxLayout(rp)
        rl.setContentsMargins(16, 14, 16, 14)
        self.heading = label("", 15, TEXT, DISPLAY, QFont.Weight.Bold)
        rl.addWidget(self.heading)
        rl.addWidget(label("World notes also show up on the Live tab whenever you enter that world.", 9.5, MUTED))
        self.edit = QPlainTextEdit()
        self.edit.textChanged.connect(self._edited)
        self._t = QTimer(self, singleShot=True, interval=600, timeout=self._save)
        rl.addWidget(self.edit, 1)
        root.addWidget(rp, 1)
        self._world = None
        self.list.setCurrentRow(0)

    def _edited(self):
        self._dirty = True
        self._t.start()

    def _load(self, w):
        self._save()
        self._world = w
        self.heading.setText(w)
        self._reload()

    def _reload(self):
        self.edit.blockSignals(True)
        self.edit.setPlainText(self.store.world_note(self._world) if self._world else "")
        self.edit.blockSignals(False)

    def _save(self):
        """Only writes what you typed here, so it never overwrites edits made on the Live tab."""
        self._t.stop()
        if self._world and self._dirty:
            self.store.set_world_note(self._world, self.edit.toPlainText())
            self._dirty = False
            self.ctl.note_changed.emit(self._world, self)

    def _changed_elsewhere(self, world, source):
        if source is not self and world == self._world and not self._dirty:
            self._reload()


# ------------------------------------------------------------------ main window
class MainWindow(QMainWindow):
    def __init__(self, store: Store, ctl: Controller):
        super().__init__()
        self.ctl = ctl
        self.setWindowTitle("RE:Trace" + ("  (demo)" if ctl.demo else ""))
        self.resize(1280, 800)
        rootw = QWidget()
        rootw.setObjectName("root")
        root = QVBoxLayout(rootw)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame()
        header.setObjectName("header")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(20, 12, 20, 12)
        hl.setSpacing(10)
        if TITLE_STYLE in ("header", "header_kh"):
            hl.addWidget(Wordmark(24))
            div = QFrame()
            div.setFixedSize(1, 38)
            div.setStyleSheet(f"background:{LINE};")
            hl.addSpacing(6)
            hl.addWidget(div)
            hl.addSpacing(6)
        clock_font = KH if TITLE_STYLE == "header_kh" else DISPLAY
        self.clock = label("0:00:00", 30, TEXT, clock_font, QFont.Weight.Bold)
        self.clock.setMinimumWidth(self.clock.fontMetrics().horizontalAdvance("0:00:00") + 6)
        hl.addWidget(self.clock)
        col = QVBoxLayout()
        col.setSpacing(0)
        self.state = label("No run", 11, TEXT, DISPLAY, QFont.Weight.DemiBold)
        self.conn = label("Looking for KH2…", 9.5, MUTED)
        # fixed-width status area: changing status text never resizes the window
        for l in (self.state, self.conn):
            l.setFixedWidth(180)
        col.addWidget(self.state)
        col.addWidget(self.conn)
        hl.addLayout(col)
        hl.addStretch()
        if TITLE_STYLE == "center":
            hl.addWidget(Wordmark(26))
            hl.addStretch()
        self.seed = QLineEdit()
        self.seed.setPlaceholderText("Seed name")
        self.seed.setFixedWidth(150)
        self.seed.textChanged.connect(lambda t: setattr(ctl, "seed", t))
        hl.addWidget(self.seed)
        self.preset = PresetCombo(store, ctl, 150)   # applies to the run in progress and the ones after it
        self.preset.set_preset(ctl.preset_id)
        self.preset.picked.connect(ctl.set_preset)
        ctl.preset_selected.connect(lambda: self.preset.set_preset(ctl.preset_id))
        hl.addWidget(self.preset)
        self.b_start = QPushButton("Start run")
        self.b_start.setObjectName("primary")
        self.b_start.clicked.connect(ctl.start_run)
        self.b_pause = QPushButton("Pause")
        self.b_pause.clicked.connect(ctl.toggle_pause)
        self.b_finish = QPushButton("Finish")
        self.b_finish.clicked.connect(ctl.finish_run)
        self.b_stop = QPushButton("End unfinished")
        self.b_stop.setObjectName("danger")
        self.b_stop.setToolTip("Stop tracking and save this run as unfinished")
        self.b_stop.clicked.connect(ctl.abandon_run)
        for b in (self.b_start, self.b_pause, self.b_finish, self.b_stop):
            hl.addWidget(b)
        root.addWidget(header)

        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        tabs.tabBar().setFont(font(DISPLAY, 11))
        tabs.tabBar().setDrawBase(False)   # no thin line under/over the tabs
        self.live = LiveTab(ctl, store)
        tabs.addTab(self.live, "Live run")
        tabs.addTab(HistoryTab(store, ctl), "History")
        tabs.addTab(StatsTab(store, ctl), "Stats")
        self.race = RaceTab(store, ctl)
        tabs.addTab(self.race, "Race")
        self.notes_tab = NotesTab(store, ctl)
        tabs.addTab(self.notes_tab, "Notes")
        tabs.tabBar().setContentsMargins(12, 0, 0, 0)
        tabs.currentChanged.connect(lambda _i: (self.live._save_note(), self.notes_tab._save()))
        root.addWidget(tabs, 1)
        self.tabs = tabs
        self.setCentralWidget(rootw)
        enable_smooth_scrolling(self)

        self._connected = False
        ctl.status_changed.connect(self._status)
        ctl.run_changed.connect(self._buttons)
        # header clock refreshes at ~30 fps straight from the run clock, so it never lags the real time
        self._clock_timer = QTimer(self, interval=33, timeout=self._refresh_clock)
        self._clock_timer.start()
        self._ui_timer = QTimer(self, interval=250, timeout=self._refresh)
        self._ui_timer.start()
        self._buttons()

    def _refresh_clock(self):
        text = fmt(self.ctl.clock(), True)
        if self.clock.text() != text:
            self.clock.setText(text)

    def _refresh(self):
        self._buttons()
        self.conn.setToolTip(self.ctl.diagnostics())

    def _status(self, text, ok):
        self._connected = ok
        full = ("● " if ok else "○ ") + text
        self.conn.setText(self.conn.fontMetrics().elidedText(full, Qt.TextElideMode.ElideRight, self.conn.width()))
        self.conn.setStyleSheet(f"color:{GOOD if ok else MUTED}; background:transparent;")
        self._buttons()

    def _buttons(self):
        c = self.ctl
        running = c.recorder is not None
        self.b_start.setEnabled(c.can_start())
        self.b_pause.setEnabled(running)
        self.b_pause.setText("Resume" if c.paused else "Pause")
        self.b_finish.setEnabled(running)
        self.b_stop.setEnabled(running)
        if running:
            loading = c.clk.loading and c.loadless and not c.paused
            self.state.setText("Paused" if c.paused else ("Loading · timer held" if loading else "Run in progress"))
            self.state.setStyleSheet(f"color:{GOLD if c.paused or loading else GOOD}; background:transparent;")
        else:
            self.state.setText("No run" if not self._connected else "Ready")
            self.state.setStyleSheet(f"color:{TEXT}; background:transparent;")
            self.clock.setText(fmt(c.clock(), True))

    def closeEvent(self, e):
        if self.ctl.recorder:
            r = QMessageBox.question(self, "Run in progress",
                                     "A run is still going. Save it as unfinished and quit?")
            if r != QMessageBox.StandardButton.Yes:
                e.ignore()
                return
            self.ctl.abandon_run()
        self.live._save_note()
        self.notes_tab._save()
        super().closeEvent(e)


def apply_theme(app: QApplication):
    for f in sorted((Path(__file__).parent / "fonts").glob("*.otf")):
        QFontDatabase.addApplicationFont(str(f))
    app.setStyle(VectorStyle(QStyleFactory.create("Fusion")))
    app.setFont(font(BODY, 10))
    app.setStyleSheet(QSS)
