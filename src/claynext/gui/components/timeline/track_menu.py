"""Compact track / clip context menus for the NLE timeline."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QMenu, QWidget

from claynext.constants.timeline_constants import FX_KINDS, OVERLAY_KINDS
from claynext.gui.icons import icon
from claynext.gui.components.timeline.models import TimelineClip, TimelineTrack

_SOUND_KINDS = frozenset({"video", "voice", "audio"})
_VISUAL_KINDS = OVERLAY_KINDS | FX_KINDS | {"video"}
_ADDABLE_KINDS = OVERLAY_KINDS | FX_KINDS
_SOURCE_KINDS = frozenset({"video", "voice", "audio"})

_KIND_TITLE = {
    "video": "Source",
    "voice": "Voice",
    "audio": "Audio",
    "caption": "Caption",
    "text": "Text",
    "image": "Image",
    "shape": "Element",
    "effect": "Effect",
    "filter": "Filter",
}


@dataclass
class TrackMenuHandlers:
    """Callbacks wired by TimelinePanel (or TrackHeader fallback)."""

    rename: Callable[[], None] | None = None
    set_locked: Callable[[bool], None] | None = None
    set_muted: Callable[[bool], None] | None = None
    set_solo: Callable[[bool], None] | None = None
    set_volume: Callable[[int], None] | None = None
    set_hidden: Callable[[bool], None] | None = None
    set_opacity: Callable[[int], None] | None = None
    set_height: Callable[[int], None] | None = None
    move_up: Callable[[], None] | None = None
    move_down: Callable[[], None] | None = None
    duplicate_track: Callable[[], None] | None = None
    delete_track: Callable[[], None] | None = None
    clear_track_keys: Callable[[], None] | None = None
    auto_mix: Callable[[], None] | None = None
    record_voice: Callable[[], None] | None = None
    add_clip_at_playhead: Callable[[], None] | None = None
    zoom_fit: Callable[[], None] | None = None
    split_at_playhead: Callable[[], None] | None = None
    split_here: Callable[[], None] | None = None
    duplicate_clip: Callable[[], None] | None = None
    delete_clip: Callable[[], None] | None = None
    toggle_key: Callable[[], None] | None = None
    clear_clip_keys: Callable[[], None] | None = None
    show_transcripts: Callable[[], None] | None = None
    retry_transcript: Callable[[], None] | None = None
    retry_translate: Callable[[], None] | None = None
    retry_tts: Callable[[], None] | None = None
    retry_all: Callable[[], None] | None = None
    import_script: Callable[[], None] | None = None
    export_script: Callable[[], None] | None = None
    # Extract / split audio from video
    extract_audio_to_track: Callable[[], None] | None = None
    extract_audio_save: Callable[[], None] | None = None
    # Studio action menu (same as timeline sparkles Tools)
    studio_action: Callable[[str], None] | None = None


def _ico(name: str, color: str = "#e7ecf3"):
    return icon(name, color=color, size=13)


def _act(
    menu: QMenu,
    label: str,
    slot: Callable[[], None] | None,
    *,
    icon_name: str = "",
    color: str = "#e7ecf3",
    enabled: bool = True,
    shortcut: str = "",
) -> QAction | None:
    """Add a menu action; optional shortcut is shown (Widget ShortcutContext)."""
    if slot is None:
        return None
    action = menu.addAction(_ico(icon_name, color), label) if icon_name else menu.addAction(label)
    action.setEnabled(enabled)
    action.setIconVisibleInMenu(True)
    if shortcut:
        action.setShortcut(QKeySequence(shortcut))
        action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        action.setShortcutVisibleInContextMenu(True)
    action.triggered.connect(slot)
    return action


def _sub(menu: QMenu, title: str, icon_name: str = "") -> QMenu:
    if icon_name:
        sub = menu.addMenu(_ico(icon_name), title)
    else:
        sub = menu.addMenu(title)
    return sub


def _fill_extract_audio_menu(menu: QMenu, handlers: TrackMenuHandlers) -> None:
    """Split audio stream out of the Cover / video source."""
    if handlers.extract_audio_to_track is None and handlers.extract_audio_save is None:
        return
    ex = _sub(menu, "Extract Audio", "volume")
    _act(
        ex, "Split to Audio Track", handlers.extract_audio_to_track,
        icon_name="split", shortcut="Ctrl+Shift+E",
    )
    _act(
        ex, "Save Audio As…", handlers.extract_audio_save,
        icon_name="download",
    )


def _fill_studio_tools_menu(menu: QMenu, handlers: TrackMenuHandlers) -> None:
    """Dubbing tools popup — same actions as the timeline sparkles menu."""
    if handlers.studio_action is None:
        return
    tools = _sub(menu, "Tools", "sparkles")
    for tip, action, icn in (
        ("Vocal isolation · extract BGM bed", "vocal", "volume"),
        ("AI translate subtitles", "translate", "globe"),
        ("Scan characters & assign voices", "scan", "chat"),
        ("Generate all dialogue audio", "generate", "sparkles"),
        ("Import SRT / VTT / JSON", "import_srt", "folder"),
        ("Export SRT subtitles", "export_srt", "download"),
        ("Load background music", "bgm", "activity"),
        ("Export video", "export_video", "video"),
    ):
        _act(
            tools, tip,
            (lambda _=False, a=action: handlers.studio_action(a)),
            icon_name=icn,
        )


def _fill_transcripts_menu(menu: QMenu, handlers: TrackMenuHandlers) -> None:
    """Audio transcripts extras for source (video / voice / audio) tracks."""
    tx = _sub(menu, "Audio Transcripts", "mic")
    _act(
        tx, "Open Script Panel", handlers.show_transcripts,
        icon_name="chat", shortcut="Ctrl+Shift+S",
    )
    tx.addSeparator()
    _act(
        tx, "Transcribe / Retry ASR", handlers.retry_transcript,
        icon_name="mic", shortcut="Ctrl+Shift+A",
    )
    _act(
        tx, "Retry Translate", handlers.retry_translate,
        icon_name="globe", shortcut="Ctrl+Shift+L",
    )
    _act(
        tx, "Retry TTS", handlers.retry_tts,
        icon_name="volume", shortcut="Ctrl+Shift+V",
    )
    _act(
        tx, "Retry All (ASR → Translate → TTS)", handlers.retry_all,
        icon_name="refresh", shortcut="Ctrl+Shift+R",
    )
    tx.addSeparator()
    _act(tx, "Import Script…", handlers.import_script, icon_name="folder")
    _act(tx, "Export Script…", handlers.export_script, icon_name="download")


def populate_track_menu(
    menu: QMenu,
    track: TimelineTrack,
    handlers: TrackMenuHandlers,
    *,
    clip: TimelineClip | None = None,
) -> None:
    """Compact top-level actions + grouped submenus per track kind."""
    kind = track.kind
    title = _KIND_TITLE.get(kind, kind.title())
    header = menu.addAction(f"{title} · {track.name}")
    header.setEnabled(False)

    # ── Clip (only when right-clicking a clip) ───────────────────────────
    if clip is not None:
        clip_locked = bool(clip.locked or track.locked)
        is_master = bool(clip.extra.get("master"))
        clip_menu = _sub(menu, "Clip", "scissors")
        _act(
            clip_menu, "Split at Playhead", handlers.split_at_playhead,
            icon_name="split", enabled=not clip_locked, shortcut="S",
        )
        _act(
            clip_menu, "Split Here", handlers.split_here,
            icon_name="scissors", enabled=not clip_locked,
        )
        _act(
            clip_menu, "Duplicate", handlers.duplicate_clip,
            icon_name="copy", enabled=not clip_locked, shortcut="Ctrl+D",
        )
        if kind in _SOUND_KINDS:
            clip_menu.addSeparator()
            _act(
                clip_menu, "Toggle Key", handlers.toggle_key,
                icon_name="activity", enabled=not clip_locked,
            )
            _act(
                clip_menu, "Clear Keys", handlers.clear_clip_keys,
                icon_name="trash", enabled=not clip_locked,
            )
        clip_menu.addSeparator()
        _act(
            clip_menu, "Delete", handlers.delete_clip,
            icon_name="trash", color="#f87171",
            enabled=not clip_locked and not is_master,
            shortcut="Delete",
        )

    # ── Kind actions (top-level, few) ────────────────────────────────────
    if kind == "video":
        _act(menu, "Auto Mix", handlers.auto_mix, icon_name="duck", shortcut="D")
        _act(menu, "Zoom to Fit", handlers.zoom_fit, icon_name="aspect", shortcut="Shift+Z")
        _act(menu, "Clear Keys", handlers.clear_track_keys, icon_name="trash")
        _fill_extract_audio_menu(menu, handlers)
        _fill_studio_tools_menu(menu, handlers)
        _fill_transcripts_menu(menu, handlers)
    elif kind == "voice":
        _act(
            menu, "Record", handlers.record_voice,
            icon_name="mic", enabled=not track.locked, shortcut="R",
        )
        _act(menu, "Auto Mix", handlers.auto_mix, icon_name="duck", shortcut="D")
        _act(menu, "Clear Keys", handlers.clear_track_keys, icon_name="trash")
        _fill_studio_tools_menu(menu, handlers)
        _fill_transcripts_menu(menu, handlers)
    elif kind == "audio":
        _act(menu, "Clear Keys", handlers.clear_track_keys, icon_name="trash")
        _fill_studio_tools_menu(menu, handlers)
        _fill_transcripts_menu(menu, handlers)
    elif kind in _ADDABLE_KINDS:
        add_label = {
            "caption": "Add Text",
            "text": "Add Text",
            "image": "Add Image",
            "shape": "Add Shape",
            "mask": "Add Mask",
            "effect": "Add Effect",
            "filter": "Add Filter",
            "logo": "Add Logo",
        }.get(kind, "Add Clip")
        _act(menu, add_label, handlers.add_clip_at_playhead, icon_name="plus", enabled=not track.locked)

    # ── Track ▸ controls ─────────────────────────────────────────────────
    track_menu = _sub(menu, "Track", "settings")
    _act(track_menu, "Rename…", handlers.rename, icon_name="type")
    _act(
        track_menu,
        "Unlock" if track.locked else "Lock",
        (lambda: handlers.set_locked(not track.locked)) if handlers.set_locked else None,
        icon_name="unlock" if track.locked else "lock",
        color="#f59e0b" if track.locked else "#e7ecf3",
        shortcut="L",
    )
    _act(
        track_menu,
        "Show" if track.hidden else "Hide",
        (lambda: handlers.set_hidden(not track.hidden)) if handlers.set_hidden else None,
        icon_name="eye" if track.hidden else "eye-off",
    )

    if kind in _SOUND_KINDS:
        track_menu.addSeparator()
        _act(
            track_menu,
            "Unmute" if track.muted else "Mute",
            (lambda: handlers.set_muted(not track.muted)) if handlers.set_muted else None,
            icon_name="volume" if track.muted else "volume-off",
            color="#f87171" if track.muted else "#e7ecf3",
            shortcut="M",
        )
        solo = bool(getattr(track, "solo", False))
        _act(
            track_menu,
            "Unsolo" if solo else "Solo",
            (lambda: handlers.set_solo(not solo)) if handlers.set_solo else None,
            icon_name="volume",
            color="#fbbf24" if solo else "#e7ecf3",
        )
        if handlers.set_volume:
            vol = _sub(track_menu, "Volume", "volume")
            for pct in (200, 150, 100, 75, 50, 25, 0):
                act = vol.addAction(f"{pct}%")
                if pct == track.volume:
                    act.setCheckable(True)
                    act.setChecked(True)
                act.triggered.connect(lambda _=False, v=pct: handlers.set_volume(v))

    if kind in _VISUAL_KINDS and kind != "video" and handlers.set_opacity:
        op = _sub(track_menu, "Opacity", "eye")
        for pct in (100, 75, 50, 25, 0):
            act = op.addAction(f"{pct}%")
            if pct == track.opacity:
                act.setCheckable(True)
                act.setChecked(True)
            act.triggered.connect(lambda _=False, v=pct: handlers.set_opacity(v))

    if handlers.set_height:
        h_menu = _sub(track_menu, "Height")
        for label, h in (("Compact", 28), ("Standard", 44), ("Tall", 72), ("Expanded", 96)):
            act = h_menu.addAction(label)
            if h == track.height:
                act.setCheckable(True)
                act.setChecked(True)
            act.triggered.connect(lambda _=False, val=h: handlers.set_height(val))

    # ── Arrange ▸ ────────────────────────────────────────────────────────
    arrange = _sub(menu, "Arrange", "grab")
    _act(arrange, "Move Up", handlers.move_up, icon_name="chevron-up")
    _act(arrange, "Move Down", handlers.move_down, icon_name="chevron-down")
    _act(arrange, "Duplicate Track", handlers.duplicate_track, icon_name="copy")

    menu.addSeparator()
    _act(menu, "Delete Track", handlers.delete_track, icon_name="trash", color="#f87171")


def open_track_menu(
    parent: QWidget,
    track: TimelineTrack,
    handlers: TrackMenuHandlers,
    global_pos,
    *,
    clip: TimelineClip | None = None,
) -> None:
    menu = QMenu(parent)
    menu.setObjectName("timeline_context_menu")
    menu.setToolTipsVisible(True)
    populate_track_menu(menu, track, handlers, clip=clip)
    menu.exec(global_pos)

