"""Main window: assembles all tabs and owns cross-tab coordination."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QIcon, QPalette
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox, QTabWidget

from mm_toolkit.core import format_timestamp
from mm_toolkit.ui.about_tab import AboutTab
from mm_toolkit.ui.clips_tab import ClipsTab
from mm_toolkit.ui.converter_tab import ConverterTab
from mm_toolkit.ui.history_tab import HistoryTab
from mm_toolkit.ui.settings_tab import SettingsTab
from mm_toolkit.ui.style import bundled_asset, material_icon
from mm_toolkit.ui.video_generator import VideoGeneratorTab


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("MM Toolkit", "MM Toolkit")
        self.setWindowTitle("MM Toolkit")
        self.setMinimumSize(820, 620)
        self.resize(1100, 820)

        self.video_generator = VideoGeneratorTab(self.settings)
        self.clips = ClipsTab(self.settings)
        self.converter = ConverterTab(self.settings)
        self.app_settings = SettingsTab(self.settings)
        self.history = HistoryTab(self.settings)
        self.about = AboutTab()
        self.tabs = QTabWidget()
        icon_color = self.palette().color(QPalette.ColorRole.WindowText).name()
        self.tabs.addTab(self.video_generator, material_icon("music_video", icon_color), "Video Generator")
        self.tabs.addTab(self.clips, material_icon("content_cut", icon_color), "Media Cutter")
        self.tabs.addTab(self.converter, material_icon("swap_horiz", icon_color), "Media Converter")
        self.tabs.addTab(self.history, material_icon("history", icon_color), "History")
        self.tabs.addTab(self.app_settings, material_icon("settings", icon_color), "Settings")
        self.tabs.addTab(self.about, material_icon("info", icon_color), "About")
        self.setCentralWidget(self.tabs)

        self.app_settings.changed.connect(self.apply_app_settings)
        self.video_generator.job_completed.connect(self.add_history)
        self.clips.job_completed.connect(self.add_history)
        self.converter.job_completed.connect(self.add_history)
        self.history.load_requested.connect(self.load_history_job)
        self.apply_app_settings()

    def apply_app_settings(self) -> None:
        default_output = self.settings.value("general/default_output", "")
        if default_output and Path(default_output).is_dir():
            if not self.video_generator.output.path:
                self.video_generator.output.set_path(default_output)
            if not self.clips.output.path:
                self.clips.output.set_path(default_output)
            if not self.converter.output.path:
                self.converter.output.set_path(default_output)

    def add_history(self, record: dict) -> None:
        try:
            records = json.loads(self.settings.value("history/jobs", "[]"))
        except (TypeError, json.JSONDecodeError):
            records = []
        records.insert(0, record)
        self.settings.setValue("history/jobs", json.dumps(records[:20]))
        self.history.refresh()

    def load_history_job(self, record: dict) -> None:
        if record.get("tool") == "promo":
            self.video_generator.music.set_path(record.get("source", ""))
            self.video_generator.cover.set_path(record.get("cover", ""))
            self.video_generator.output.set_path(record.get("output", ""))
            self.video_generator.bass_effect.setChecked(record.get("bass_effect", True))
            self.video_generator.video_fade.setChecked(record.get("video_fade", True))
            self.video_generator.audio_fade.setChecked(record.get("audio_fade", True))
            self.video_generator.mute_original_video_audio.setChecked(record.get("mute_original_video_audio", True))
            stored_tracks = {item.get("path"): item for item in record.get("tracks", [])}
            for row in range(self.video_generator.promo_tracks.rowCount()):
                path = self.video_generator.promo_tracks.item(row, 0).data(Qt.ItemDataRole.UserRole)
                if path in stored_tracks:
                    self.video_generator.promo_tracks.cellWidget(row, 1).setText(format_timestamp(stored_tracks[path].get("start", 0)))
                    self.video_generator.promo_tracks.cellWidget(row, 2).setValue(stored_tracks[path].get("duration", 60))
            self.video_generator.analysis_status.setText("✓ Loaded saved per-track timings.")
            self.video_generator.fps.setValue(record.get("fps", 24))
            profile = record.get("profile")
            self.video_generator.profile.setCurrentIndex(max(0, self.video_generator.profile.findData(tuple(profile) if profile else None)))
            self.tabs.setCurrentIndex(0)
        elif record.get("tool") == "clips":
            self.clips.source.set_path(record.get("source", ""))
            self.clips.output.set_path(record.get("output", ""))
            self.clips.table.setRowCount(0)
            for clip in record.get("clips", []):
                self.clips.add_row(
                    clip.get("title", ""),
                    format_timestamp(clip.get("start", 0)),
                    "",
                    str(clip.get("duration", 60)),
                )
            if self.clips.table.rowCount() == 0:
                self.clips.add_row()
            self.tabs.setCurrentIndex(1)
        elif record.get("tool") == "converter":
            self.converter.set_files(record.get("sources", []))
            self.converter.output.set_path(record.get("output", ""))
            format_index = self.converter.output_format.findData(record.get("format", ""))
            if format_index >= 0:
                self.converter.output_format.setCurrentIndex(format_index)
            bitrate_index = self.converter.mp3_bitrate.findData(record.get("bitrate", "320k"))
            if bitrate_index >= 0:
                self.converter.mp3_bitrate.setCurrentIndex(bitrate_index)
            self.tabs.setCurrentIndex(2)

    def closeEvent(self, event):  # noqa: N802, ANN001
        promo_running = self.video_generator.worker and self.video_generator.worker.isRunning()
        analysis_running = self.video_generator.analysis_worker and self.video_generator.analysis_worker.isRunning()
        clips_running = self.clips.worker and self.clips.worker.isRunning()
        converter_running = self.converter.worker and self.converter.worker.isRunning()
        if promo_running or analysis_running or clips_running or converter_running:
            QMessageBox.warning(self, "Rendering in progress", "Wait for rendering to finish before closing the app.")
            event.ignore()
            return
        self.video_generator.stop_promo_preview()
        event.accept()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("MM Toolkit")
    app.setOrganizationName("MM Toolkit")
    app.setWindowIcon(QIcon(os.fspath(bundled_asset("mm-toolkit-icon.png"))))
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
