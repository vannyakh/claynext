"""Volume, fades, and auto-key controls."""
from __future__ import annotations

from PySide6.QtWidgets import QLabel

from claynext.gui.components.inspector.properties.const import db10_to_pct, db_text, pct_to_db10

class PropsAudio:
    def show_level(self, level: float, on_key: bool, has_prev: bool, has_next: bool):
        """Reflect the clip level under the playhead (called as the playhead moves)."""
        value = pct_to_db10(level)
        self.spin_db.blockSignals(True)
        self.spin_db.setValue(value)
        self.spin_db.blockSignals(False)
        self.lbl_db.setText(db_text(value))
        self.btn_key.setText("◆" if on_key else "◇")
        self.btn_key_prev.setEnabled(has_prev)
        self.btn_key_next.setEnabled(has_next)

    def show_key_count(self, count: int):
        self.keys_row.setVisible(count > 0)
        self.lbl_keys.setText(f"{count} key point{'s' if count != 1 else ''} on the source")

    def show_bed_state(self, has_bed: bool):
        self._has_bed = has_bed
        self._sync_autokey_enabled()

    def auto_key_state(self) -> dict:
        return {
            "on": self.chk_autokey.isChecked(),
            "detect": self.chk_detect.isChecked(),
            "level": self.spin_duck.value(),
        }

    def _on_db(self, value: int):
        self.lbl_db.setText(db_text(value))
        if not self._block:
            self.level_changed.emit(db10_to_pct(value))

    def _on_fade(self, *_):
        fade_in = self.spin_fade_in.value() * 100
        fade_out = self.spin_fade_out.value() * 100
        self.lbl_fade_in.setText(f"Fade in · {fade_in / 1000:.1f}s")
        self.lbl_fade_out.setText(f"Fade out · {fade_out / 1000:.1f}s")
        if not self._block:
            self.fades_changed.emit(fade_in, fade_out)

    def _on_duck(self, value: int):
        self.lbl_duck.setText(f"Duck to · {value}%")
        if not self._block and self.chk_autokey.isChecked():
            self.auto_key_changed.emit(self.auto_key_state())

    def _sync_autokey_enabled(self):
        on = self.chk_autokey.isChecked()
        self.chk_detect.setEnabled(on)
        duck_enabled = on and not self._has_bed
        self.spin_duck.setEnabled(duck_enabled)
        self.lbl_duck.setEnabled(duck_enabled)

    def _on_autokey(self, *_):
        self._sync_autokey_enabled()
        if not self._block:
            self.auto_key_changed.emit(self.auto_key_state())

    def _relabel(self, label: QLabel, name: str, value: str):
        label.setText(f"{name} · {value}")
        self._emit()
