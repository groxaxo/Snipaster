#!/usr/bin/env python3
"""Snipaster desktop capture, tray, and annotation application."""

from __future__ import annotations

import argparse
import fcntl
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional, Union

APP_NAME = "Snipaster"
APP_VERSION = "0.1.0"
SCREENSHOT_DIR = Path.home() / "Pictures" / "Screenshots"

try:
    from PyQt5.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSignal
    from PyQt5.QtGui import (
        QColor,
        QCloseEvent,
        QFont,
        QIcon,
        QImage,
        QKeySequence,
        QMouseEvent,
        QPainter,
        QPainterPath,
        QPen,
    )
    from PyQt5.QtWidgets import (
        QAction,
        QActionGroup,
        QApplication,
        QColorDialog,
        QFileDialog,
        QInputDialog,
        QLabel,
        QMainWindow,
        QMenu,
        QMessageBox,
        QSpinBox,
        QSystemTrayIcon,
        QToolBar,
        QToolButton,
        QWidget,
    )
except ImportError as exc:  # pragma: no cover - exercised on systems missing the runtime
    print(
        "Snipaster needs PyQt5. Re-run the installer or install "
        "the Ubuntu package 'python3-pyqt5'.",
        file=sys.stderr,
    )
    raise SystemExit(2) from exc


@dataclass(frozen=True)
class Stroke:
    """One freehand stroke stored in source-image coordinates."""

    points: tuple[tuple[float, float], ...]
    color: str
    width: int


@dataclass(frozen=True)
class TextAnnotation:
    """Text placed at a source-image coordinate."""

    x: float
    y: float
    text: str
    color: str
    size: int


Annotation = Union[Stroke, TextAnnotation]


@dataclass(frozen=True)
class CanvasState:
    """An immutable history entry for undo and redo."""

    image: QImage
    annotations: tuple[Annotation, ...]


class FileLock:
    """Small non-blocking process lock backed by flock(2)."""

    def __init__(self, name: str) -> None:
        runtime = os.environ.get("XDG_RUNTIME_DIR")
        if runtime:
            root = Path(runtime)
        else:
            root = Path("/tmp") / f"snipaster-{os.getuid()}"
            root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.path = root / name
        self._handle: Optional[object] = None

    def acquire(self) -> bool:
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        handle = self.path.open("a+")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            handle.close()
            return False
        handle.seek(0)
        handle.truncate()
        handle.write(str(os.getpid()))
        handle.flush()
        self._handle = handle
        return True

    def release(self) -> None:
        if self._handle is None:
            return
        try:
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        finally:
            self._handle.close()
            self._handle = None

    def __enter__(self) -> "FileLock":
        if not self.acquire():
            raise RuntimeError(f"Lock is already held: {self.path}")
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:  # type: ignore[no-untyped-def]
        self.release()


def notify(summary: str, body: str) -> None:
    """Send a desktop notification without blocking the capture flow."""

    command = shutil.which("notify-send")
    if not command:
        return
    try:
        subprocess.Popen(
            [command, "--app-name", APP_NAME, summary, body],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        pass


def icon_path() -> Optional[Path]:
    """Return the first installed or source-tree icon path."""

    candidates = (
        Path.home()
        / ".local"
        / "share"
        / "icons"
        / "hicolor"
        / "scalable"
        / "apps"
        / "snipaster.svg",
        Path(__file__).resolve().with_name("snipaster-icon.svg"),
        Path(__file__).resolve().parent / "assets" / "snipaster-icon.svg",
    )
    return next((path for path in candidates if path.is_file()), None)


def app_icon() -> QIcon:
    path = icon_path()
    if path:
        return QIcon(str(path))
    themed = QIcon.fromTheme("camera-photo")
    return themed if not themed.isNull() else QIcon()


def launcher_path() -> Path:
    installed = Path.home() / ".local" / "bin" / "snipaster"
    return installed if installed.is_file() else Path(__file__).resolve()


def launch_detached(*arguments: str) -> None:
    """Launch another Snipaster mode outside the current Qt event loop."""

    launcher = launcher_path()
    if launcher == Path(__file__).resolve():
        command = [sys.executable, str(launcher), *arguments]
    else:
        command = [str(launcher), *arguments]
    subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
    )


def open_screenshot_folder() -> None:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    opener = shutil.which("xdg-open")
    if not opener:
        notify(APP_NAME, f"Screenshots are stored in {SCREENSHOT_DIR}")
        return
    subprocess.Popen(
        [opener, str(SCREENSHOT_DIR)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def _run_capture_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def capture_region(destination: Path) -> tuple[bool, str]:
    """Capture an interactively selected screen region into *destination*."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.unlink(missing_ok=True)
    session = os.environ.get("XDG_SESSION_TYPE", "").lower()
    if not session:
        session = "wayland" if os.environ.get("WAYLAND_DISPLAY") else "x11"
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()

    result: Optional[subprocess.CompletedProcess[str]] = None

    if session == "wayland":
        gnome_screenshot = shutil.which("gnome-screenshot")
        grim = shutil.which("grim")
        slurp = shutil.which("slurp")

        if gnome_screenshot and ("gnome" in desktop or "ubuntu" in desktop):
            result = _run_capture_command(
                [gnome_screenshot, "--area", "--file", str(destination)]
            )
        elif grim and slurp:
            selection = _run_capture_command([slurp])
            geometry = selection.stdout.strip()
            if selection.returncode != 0 or not geometry:
                return False, "Capture cancelled."
            result = _run_capture_command([grim, "-g", geometry, str(destination)])
        elif gnome_screenshot:
            result = _run_capture_command(
                [gnome_screenshot, "--area", "--file", str(destination)]
            )
        else:
            return (
                False,
                "No Wayland capture backend was found. Install gnome-screenshot "
                "or grim + slurp.",
            )
    else:
        scrot = shutil.which("scrot")
        gnome_screenshot = shutil.which("gnome-screenshot")
        if scrot:
            result = _run_capture_command([scrot, "--select", str(destination)])
        elif gnome_screenshot:
            result = _run_capture_command(
                [gnome_screenshot, "--area", "--file", str(destination)]
            )
        else:
            return False, "No X11 capture backend was found. Install scrot."

    if destination.is_file() and destination.stat().st_size > 0:
        return True, ""

    destination.unlink(missing_ok=True)
    if result is None or result.returncode == 0:
        return False, "Capture cancelled."
    details = result.stderr.strip().splitlines()
    reason = details[-1] if details else "Capture failed."
    return False, reason


class AnnotationCanvas(QWidget):
    """Fit-to-window image canvas with lightweight annotation history."""

    state_changed = pyqtSignal()
    selection_changed = pyqtSignal(bool)

    TOOL_DRAW = "draw"
    TOOL_TEXT = "text"
    TOOL_SELECT = "select"

    def __init__(self, image: QImage, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        normalized = image.convertToFormat(QImage.Format_ARGB32)
        self._states: list[CanvasState] = [CanvasState(normalized, tuple())]
        self._state_index = 0
        self._saved_index = 0
        self._tool = self.TOOL_DRAW
        self._color = QColor("#ff3b67")
        self._brush_width = 6
        self._text_size = 32
        self._active_stroke: list[tuple[float, float]] = []
        self._selection_start: Optional[QPointF] = None
        self._selection: Optional[QRectF] = None
        self.setMinimumSize(480, 320)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self._refresh_cursor()

    @property
    def state(self) -> CanvasState:
        return self._states[self._state_index]

    @property
    def dirty(self) -> bool:
        return self._state_index != self._saved_index

    @property
    def can_undo(self) -> bool:
        return self._state_index > 0

    @property
    def can_redo(self) -> bool:
        return self._state_index + 1 < len(self._states)

    @property
    def has_selection(self) -> bool:
        rect = self.selection_image_rect()
        return rect is not None and rect.width() >= 2 and rect.height() >= 2

    def mark_saved(self) -> None:
        self._saved_index = self._state_index
        self.state_changed.emit()

    def set_tool(self, tool: str) -> None:
        if tool not in {self.TOOL_DRAW, self.TOOL_TEXT, self.TOOL_SELECT}:
            raise ValueError(f"Unknown annotation tool: {tool}")
        self._tool = tool
        self._active_stroke.clear()
        self._selection_start = None
        self._refresh_cursor()
        self.update()

    def set_color(self, color: QColor) -> None:
        if color.isValid():
            self._color = QColor(color)

    def color(self) -> QColor:
        return QColor(self._color)

    def set_brush_width(self, width: int) -> None:
        self._brush_width = max(1, min(80, width))

    def set_text_size(self, size: int) -> None:
        self._text_size = max(8, min(160, size))

    def _refresh_cursor(self) -> None:
        self.setCursor(Qt.CrossCursor)

    def _display_geometry(self) -> tuple[QRectF, float]:
        image = self.state.image
        if image.isNull() or self.width() <= 0 or self.height() <= 0:
            return QRectF(), 1.0
        padding = 24.0
        available_width = max(1.0, self.width() - padding * 2)
        available_height = max(1.0, self.height() - padding * 2)
        scale = min(
            available_width / image.width(), available_height / image.height()
        )
        width = image.width() * scale
        height = image.height() * scale
        left = (self.width() - width) / 2.0
        top = (self.height() - height) / 2.0
        return QRectF(left, top, width, height), scale

    def _widget_to_image(self, point: QPointF) -> Optional[QPointF]:
        display, scale = self._display_geometry()
        if display.isEmpty() or not display.contains(point):
            return None
        return QPointF(
            (point.x() - display.left()) / scale,
            (point.y() - display.top()) / scale,
        )

    def _image_to_widget_rect(self, rect: QRectF) -> QRectF:
        display, scale = self._display_geometry()
        return QRectF(
            display.left() + rect.left() * scale,
            display.top() + rect.top() * scale,
            rect.width() * scale,
            rect.height() * scale,
        )

    @staticmethod
    def _draw_annotations(
        painter: QPainter,
        annotations: Iterable[Annotation],
        active_stroke: Optional[Stroke] = None,
    ) -> None:
        for annotation in annotations:
            if isinstance(annotation, Stroke):
                AnnotationCanvas._draw_stroke(painter, annotation)
            else:
                painter.save()
                painter.setPen(QColor(annotation.color))
                font = QFont("Sans Serif")
                font.setPixelSize(annotation.size)
                font.setBold(True)
                painter.setFont(font)
                painter.drawText(
                    QRectF(annotation.x, annotation.y, 100000.0, 100000.0),
                    Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap,
                    annotation.text,
                )
                painter.restore()
        if active_stroke is not None:
            AnnotationCanvas._draw_stroke(painter, active_stroke)

    @staticmethod
    def _draw_stroke(painter: QPainter, stroke: Stroke) -> None:
        if not stroke.points:
            return
        path = QPainterPath(QPointF(*stroke.points[0]))
        for point in stroke.points[1:]:
            path.lineTo(QPointF(*point))
        pen = QPen(QColor(stroke.color), stroke.width)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.save()
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        if len(stroke.points) == 1:
            painter.drawPoint(QPointF(*stroke.points[0]))
        else:
            painter.drawPath(path)
        painter.restore()

    def paintEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.fillRect(self.rect(), QColor("#11131a"))

        display, scale = self._display_geometry()
        if display.isEmpty():
            painter.end()
            return

        painter.fillRect(display.adjusted(-2, -2, 2, 2), QColor("#343845"))
        painter.drawImage(display, self.state.image)

        painter.save()
        painter.setClipRect(display)
        painter.translate(display.left(), display.top())
        painter.scale(scale, scale)
        active: Optional[Stroke] = None
        if self._active_stroke:
            active = Stroke(
                tuple(self._active_stroke), self._color.name(), self._brush_width
            )
        self._draw_annotations(painter, self.state.annotations, active)
        painter.restore()

        if self._selection is not None:
            selection = self._image_to_widget_rect(self._selection.normalized())
            shade = QColor(0, 0, 0, 105)
            painter.fillRect(
                QRectF(
                    display.left(),
                    display.top(),
                    display.width(),
                    selection.top() - display.top(),
                ),
                shade,
            )
            painter.fillRect(
                QRectF(
                    display.left(),
                    selection.bottom(),
                    display.width(),
                    display.bottom() - selection.bottom(),
                ),
                shade,
            )
            painter.fillRect(
                QRectF(
                    display.left(),
                    selection.top(),
                    selection.left() - display.left(),
                    selection.height(),
                ),
                shade,
            )
            painter.fillRect(
                QRectF(
                    selection.right(),
                    selection.top(),
                    display.right() - selection.right(),
                    selection.height(),
                ),
                shade,
            )
            pen = QPen(QColor("#69e7ff"), 2)
            pen.setStyle(Qt.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(selection)

        painter.end()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.LeftButton:
            return
        point = self._widget_to_image(QPointF(event.pos()))
        if point is None:
            return
        self.setFocus(Qt.MouseFocusReason)

        if self._tool == self.TOOL_DRAW:
            self._active_stroke = [(point.x(), point.y())]
            self.update()
        elif self._tool == self.TOOL_SELECT:
            self._selection_start = point
            self._selection = QRectF(point, point)
            self.selection_changed.emit(False)
            self.update()
        elif self._tool == self.TOOL_TEXT:
            text, accepted = QInputDialog.getMultiLineText(
                self,
                "Add text",
                "Text to place on the screenshot:",
            )
            if accepted and text.strip():
                annotation = TextAnnotation(
                    point.x(),
                    point.y(),
                    text.strip(),
                    self._color.name(),
                    self._text_size,
                )
                self._push_state(
                    CanvasState(
                        self.state.image,
                        (*self.state.annotations, annotation),
                    )
                )

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not event.buttons() & Qt.LeftButton:
            return
        point = self._widget_to_image(QPointF(event.pos()))
        if point is None:
            return
        if self._tool == self.TOOL_DRAW and self._active_stroke:
            previous = self._active_stroke[-1]
            if abs(point.x() - previous[0]) + abs(point.y() - previous[1]) >= 0.8:
                self._active_stroke.append((point.x(), point.y()))
                self.update()
        elif self._tool == self.TOOL_SELECT and self._selection_start is not None:
            self._selection = QRectF(self._selection_start, point).normalized()
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.LeftButton:
            return
        if self._tool == self.TOOL_DRAW and self._active_stroke:
            stroke = Stroke(
                tuple(self._active_stroke), self._color.name(), self._brush_width
            )
            self._active_stroke = []
            self._push_state(
                CanvasState(self.state.image, (*self.state.annotations, stroke))
            )
        elif self._tool == self.TOOL_SELECT and self._selection_start is not None:
            point = self._widget_to_image(QPointF(event.pos()))
            if point is not None:
                self._selection = QRectF(self._selection_start, point).normalized()
            self._selection_start = None
            if not self.has_selection:
                self._selection = None
            self.selection_changed.emit(self.has_selection)
            self.update()

    def _push_state(self, state: CanvasState) -> None:
        if self._state_index + 1 < len(self._states):
            if self._saved_index > self._state_index:
                self._saved_index = -1
            del self._states[self._state_index + 1 :]
        self._states.append(state)
        self._state_index += 1
        self._selection = None
        self.selection_changed.emit(False)
        self.state_changed.emit()
        self.update()

    def undo(self) -> None:
        if not self.can_undo:
            return
        self._state_index -= 1
        self._selection = None
        self.selection_changed.emit(False)
        self.state_changed.emit()
        self.update()

    def redo(self) -> None:
        if not self.can_redo:
            return
        self._state_index += 1
        self._selection = None
        self.selection_changed.emit(False)
        self.state_changed.emit()
        self.update()

    def clear_selection(self) -> None:
        if self._selection is None:
            return
        self._selection = None
        self._selection_start = None
        self.selection_changed.emit(False)
        self.update()

    def selection_image_rect(self) -> Optional[QRectF]:
        if self._selection is None:
            return None
        image_bounds = QRectF(
            0.0, 0.0, float(self.state.image.width()), float(self.state.image.height())
        )
        bounded = self._selection.normalized().intersected(image_bounds)
        return bounded if not bounded.isEmpty() else None

    def render_image(self) -> QImage:
        output = self.state.image.copy().convertToFormat(QImage.Format_ARGB32)
        painter = QPainter(output)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        self._draw_annotations(painter, self.state.annotations)
        painter.end()
        return output

    def selected_image(self) -> Optional[QImage]:
        selection = self.selection_image_rect()
        if selection is None:
            return None
        rect = selection.toAlignedRect().intersected(self.render_image().rect())
        if rect.width() < 2 or rect.height() < 2:
            return None
        return self.render_image().copy(rect)

    def crop_to_selection(self) -> None:
        selection = self.selection_image_rect()
        if selection is None:
            return
        rendered = self.render_image()
        rect = selection.toAlignedRect().intersected(rendered.rect())
        if rect.width() < 2 or rect.height() < 2:
            return
        cropped = rendered.copy(rect)
        self._push_state(CanvasState(cropped, tuple()))


class AnnotationWindow(QMainWindow):
    """Main annotation window shown immediately after a capture."""

    def __init__(self, image_path: Path) -> None:
        super().__init__()
        self.image_path = image_path
        self._closing_after_save = False
        image = QImage(str(image_path))
        if image.isNull():
            raise ValueError(f"Could not load screenshot: {image_path}")

        self.canvas = AnnotationCanvas(image, self)
        self.setCentralWidget(self.canvas)
        self.setWindowIcon(app_icon())
        self.resize(1180, 780)
        self._build_toolbar()
        self.canvas.state_changed.connect(self._sync_actions)
        self.canvas.selection_changed.connect(self._sync_selection_actions)
        self._sync_actions()
        self._sync_selection_actions(False)
        self.statusBar().showMessage(
            "Draw, add text, or drag a selection. Save & Close when finished."
        )
        QTimer.singleShot(150, self._copy_initial_capture)

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Annotation tools", self)
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.addToolBar(Qt.TopToolBarArea, toolbar)

        tool_group = QActionGroup(self)
        tool_group.setExclusive(True)

        self.draw_action = QAction(QIcon.fromTheme("draw-freehand"), "Draw", self)
        self.draw_action.setCheckable(True)
        self.draw_action.setChecked(True)
        self.draw_action.setShortcut("D")
        self.draw_action.setToolTip("Freehand drawing (D)")
        self.draw_action.triggered.connect(
            lambda: self.canvas.set_tool(AnnotationCanvas.TOOL_DRAW)
        )
        tool_group.addAction(self.draw_action)
        toolbar.addAction(self.draw_action)

        self.text_action = QAction(QIcon.fromTheme("insert-text"), "Text", self)
        self.text_action.setCheckable(True)
        self.text_action.setShortcut("T")
        self.text_action.setToolTip("Click the image to add text (T)")
        self.text_action.triggered.connect(
            lambda: self.canvas.set_tool(AnnotationCanvas.TOOL_TEXT)
        )
        tool_group.addAction(self.text_action)
        toolbar.addAction(self.text_action)

        self.select_action = QAction(
            QIcon.fromTheme("select-rectangular"), "Select", self
        )
        self.select_action.setCheckable(True)
        self.select_action.setShortcut("S")
        self.select_action.setToolTip("Drag a region to copy or crop (S)")
        self.select_action.triggered.connect(
            lambda: self.canvas.set_tool(AnnotationCanvas.TOOL_SELECT)
        )
        tool_group.addAction(self.select_action)
        toolbar.addAction(self.select_action)

        toolbar.addSeparator()
        toolbar.addWidget(QLabel(" Colour "))
        self.color_button = QToolButton(self)
        self.color_button.setText("      ")
        self.color_button.setToolTip("Choose annotation colour")
        self.color_button.clicked.connect(self._choose_color)
        toolbar.addWidget(self.color_button)
        self._refresh_color_button()

        toolbar.addWidget(QLabel(" Brush "))
        brush_size = QSpinBox(self)
        brush_size.setRange(1, 80)
        brush_size.setValue(6)
        brush_size.setSuffix(" px")
        brush_size.valueChanged.connect(self.canvas.set_brush_width)
        toolbar.addWidget(brush_size)

        toolbar.addWidget(QLabel(" Text "))
        text_size = QSpinBox(self)
        text_size.setRange(8, 160)
        text_size.setValue(32)
        text_size.setSuffix(" px")
        text_size.valueChanged.connect(self.canvas.set_text_size)
        toolbar.addWidget(text_size)

        toolbar.addSeparator()
        self.crop_action = QAction(QIcon.fromTheme("transform-crop"), "Crop", self)
        self.crop_action.setToolTip("Crop to the current selection")
        self.crop_action.triggered.connect(self.canvas.crop_to_selection)
        toolbar.addAction(self.crop_action)

        self.copy_selection_action = QAction(
            QIcon.fromTheme("edit-copy"), "Copy selection", self
        )
        self.copy_selection_action.setShortcut("Ctrl+Shift+C")
        self.copy_selection_action.triggered.connect(self._copy_selection)
        toolbar.addAction(self.copy_selection_action)

        toolbar.addSeparator()
        self.undo_action = QAction(QIcon.fromTheme("edit-undo"), "Undo", self)
        self.undo_action.setShortcut(QKeySequence.Undo)
        self.undo_action.triggered.connect(self.canvas.undo)
        toolbar.addAction(self.undo_action)

        self.redo_action = QAction(QIcon.fromTheme("edit-redo"), "Redo", self)
        self.redo_action.setShortcuts(
            [QKeySequence(QKeySequence.Redo), QKeySequence("Ctrl+Y")]
        )
        self.redo_action.triggered.connect(self.canvas.redo)
        toolbar.addAction(self.redo_action)

        toolbar.addSeparator()
        save_action = QAction(QIcon.fromTheme("document-save"), "Save", self)
        save_action.setShortcut(QKeySequence.Save)
        save_action.triggered.connect(self.save)
        toolbar.addAction(save_action)

        save_as_action = QAction(
            QIcon.fromTheme("document-save-as"), "Save As", self
        )
        save_as_action.setShortcut(QKeySequence.SaveAs)
        save_as_action.triggered.connect(self.save_as)
        toolbar.addAction(save_as_action)

        copy_action = QAction(QIcon.fromTheme("edit-copy"), "Copy", self)
        copy_action.setShortcut(QKeySequence.Copy)
        copy_action.setToolTip("Copy the selection, or the whole image when none is selected")
        copy_action.triggered.connect(self.copy_current)
        toolbar.addAction(copy_action)

        done_action = QAction(QIcon.fromTheme("dialog-ok"), "Save & Close", self)
        done_action.setShortcuts([QKeySequence("Ctrl+Return"), QKeySequence("Ctrl+Enter")])
        done_action.triggered.connect(self.save_and_close)
        toolbar.addAction(done_action)

        escape_action = QAction(self)
        escape_action.setShortcut(QKeySequence.Cancel)
        escape_action.triggered.connect(self._escape)
        self.addAction(escape_action)

    def _choose_color(self) -> None:
        color = QColorDialog.getColor(
            self.canvas.color(), self, "Choose annotation colour"
        )
        if color.isValid():
            self.canvas.set_color(color)
            self._refresh_color_button()

    def _refresh_color_button(self) -> None:
        color = self.canvas.color().name()
        self.color_button.setStyleSheet(
            f"QToolButton {{ background: {color}; border: 1px solid #777; "
            "border-radius: 4px; min-width: 34px; min-height: 22px; }}"
        )

    def _sync_actions(self) -> None:
        self.undo_action.setEnabled(self.canvas.can_undo)
        self.redo_action.setEnabled(self.canvas.can_redo)
        marker = " *" if self.canvas.dirty else ""
        self.setWindowTitle(f"{APP_NAME} — {self.image_path.name}{marker}")

    def _sync_selection_actions(self, selected: bool) -> None:
        self.crop_action.setEnabled(selected)
        self.copy_selection_action.setEnabled(selected)

    def _copy_initial_capture(self) -> None:
        QApplication.clipboard().setImage(self.canvas.render_image())
        notify(
            "Screenshot captured",
            "Snipaster is ready: draw, add text, select, crop, save, or copy.",
        )

    def _copy_selection(self) -> None:
        selected = self.canvas.selected_image()
        if selected is None:
            return
        QApplication.clipboard().setImage(selected)
        self.statusBar().showMessage("Selection copied to the clipboard.", 3500)

    def copy_current(self) -> None:
        selected = self.canvas.selected_image()
        image = selected if selected is not None else self.canvas.render_image()
        QApplication.clipboard().setImage(image)
        message = "Selection copied." if selected is not None else "Image copied."
        self.statusBar().showMessage(f"{message} Paste it with Ctrl+V.", 3500)

    def _write_image(self, path: Path) -> bool:
        path.parent.mkdir(parents=True, exist_ok=True)
        image = self.canvas.render_image()
        if not image.save(str(path)):
            QMessageBox.critical(
                self,
                "Could not save screenshot",
                f"Snipaster could not write:\n{path}",
            )
            return False
        self.image_path = path
        self.canvas.mark_saved()
        QApplication.clipboard().setImage(image)
        self.statusBar().showMessage(
            f"Saved and copied: {path.name}", 4500
        )
        notify("Screenshot saved", f"Saved and copied {path.name}")
        return True

    def save(self) -> bool:
        return self._write_image(self.image_path)

    def save_as(self) -> bool:
        selected, _ = QFileDialog.getSaveFileName(
            self,
            "Save annotated screenshot",
            str(self.image_path),
            "PNG image (*.png)",
        )
        if not selected:
            return False
        path = Path(selected)
        if path.suffix.lower() != ".png":
            path = path.with_suffix(".png")
        return self._write_image(path)

    def save_and_close(self) -> None:
        if self.save():
            self._closing_after_save = True
            self.close()

    def _escape(self) -> None:
        if self.canvas.has_selection:
            self.canvas.clear_selection()
        else:
            self.close()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._closing_after_save or not self.canvas.dirty:
            event.accept()
            return
        box = QMessageBox(self)
        box.setWindowTitle("Save annotations?")
        box.setText("The screenshot has unsaved annotations.")
        box.setInformativeText("Save them before closing Snipaster?")
        box.setIcon(QMessageBox.Question)
        save_button = box.addButton(QMessageBox.Save)
        discard_button = box.addButton(QMessageBox.Discard)
        cancel_button = box.addButton(QMessageBox.Cancel)
        box.setDefaultButton(save_button)
        box.exec_()
        clicked = box.clickedButton()
        if clicked == save_button:
            if self.save():
                event.accept()
            else:
                event.ignore()
        elif clicked == discard_button:
            event.accept()
        elif clicked == cancel_button:
            event.ignore()
        else:
            event.ignore()


class TrayController:
    """Persistent system-tray capture control."""

    def __init__(self, app: QApplication) -> None:
        self.app = app
        self._capture_pending = False
        self.tray = QSystemTrayIcon(app_icon(), app)
        self.tray.setToolTip("Snipaster — click to capture a region")

        self.menu = QMenu()
        capture_action = self.menu.addAction("Capture region")
        capture_action.setIcon(QIcon.fromTheme("camera-photo"))
        capture_action.triggered.connect(lambda: launch_detached("capture"))

        folder_action = self.menu.addAction("Open Screenshots")
        folder_action.setIcon(QIcon.fromTheme("folder-pictures"))
        folder_action.triggered.connect(open_screenshot_folder)

        self.menu.addSeparator()
        quit_action = self.menu.addAction("Quit Snipaster")
        quit_action.triggered.connect(app.quit)

        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self._activated)
        self.tray.show()

        if QSystemTrayIcon.supportsMessages():
            QTimer.singleShot(
                700,
                lambda: self.tray.showMessage(
                    APP_NAME,
                    "Ready. Press F1 or click the capture icon.",
                    QSystemTrayIcon.Information,
                    3500,
                ),
            )

    def _activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason not in (
            QSystemTrayIcon.Trigger,
            QSystemTrayIcon.DoubleClick,
            QSystemTrayIcon.MiddleClick,
        ):
            return
        if self._capture_pending:
            return
        self._capture_pending = True
        launch_detached("capture")
        QTimer.singleShot(700, self._allow_capture)

    def _allow_capture(self) -> None:
        self._capture_pending = False


def create_application(*, tray: bool = False) -> QApplication:
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setDesktopFileName("snipaster")
    app.setWindowIcon(app_icon())
    app.setQuitOnLastWindowClosed(not tray)
    return app


def require_graphical_session() -> None:
    if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
        return
    raise SystemExit("Snipaster requires a graphical desktop session.")


def run_capture() -> int:
    require_graphical_session()
    lock = FileLock("snipaster-capture.lock")
    if not lock.acquire():
        notify(APP_NAME, "A Snipaster capture or editor is already open.")
        return 1

    try:
        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S-%f")[:-3]
        path = SCREENSHOT_DIR / f"screenshot-{timestamp}.png"
        captured, reason = capture_region(path)
        if not captured:
            if reason != "Capture cancelled.":
                notify("Capture failed", reason)
                print(reason, file=sys.stderr)
                return 2
            return 0

        app = create_application()
        try:
            window = AnnotationWindow(path)
        except ValueError as exc:
            notify("Capture failed", str(exc))
            print(str(exc), file=sys.stderr)
            return 2
        window.showMaximized()
        return app.exec_()
    finally:
        lock.release()


def run_editor(path: Path) -> int:
    require_graphical_session()
    if not path.is_file():
        print(f"Screenshot not found: {path}", file=sys.stderr)
        return 2
    app = create_application()
    try:
        window = AnnotationWindow(path)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    window.showMaximized()
    return app.exec_()


def run_tray() -> int:
    require_graphical_session()
    lock = FileLock("snipaster-tray.lock")
    if not lock.acquire():
        return 0
    try:
        app = create_application(tray=True)
        if not QSystemTrayIcon.isSystemTrayAvailable():
            notify(
                APP_NAME,
                "The desktop does not expose a system tray. Use F1 or the desktop icon.",
            )
            return 0
        controller = TrayController(app)
        app._snipaster_tray_controller = controller  # type: ignore[attr-defined]
        return app.exec_()
    finally:
        lock.release()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="snipaster",
        description="Capture, annotate, save, and copy screen regions on Ubuntu.",
    )
    parser.add_argument("--version", action="version", version=APP_VERSION)
    subcommands = parser.add_subparsers(dest="command")
    subcommands.add_parser("capture", help="Capture a region and open the editor")
    subcommands.add_parser("tray", help="Run the persistent capture icon")
    edit = subcommands.add_parser("edit", help="Open an existing image in the editor")
    edit.add_argument("image", type=Path)
    subcommands.add_parser("open-folder", help="Open the screenshot folder")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    arguments = build_parser().parse_args(argv)
    if arguments.command in (None, "capture"):
        return run_capture()
    if arguments.command == "tray":
        return run_tray()
    if arguments.command == "edit":
        return run_editor(arguments.image.expanduser().resolve())
    if arguments.command == "open-folder":
        open_screenshot_folder()
        return 0
    raise AssertionError(f"Unhandled command: {arguments.command}")


if __name__ == "__main__":
    raise SystemExit(main())
