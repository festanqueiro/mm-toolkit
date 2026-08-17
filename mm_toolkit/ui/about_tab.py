"""About tab: app info, logo, and update check."""

from __future__ import annotations

import html
import json
import os

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from mm_toolkit import __version__
from mm_toolkit.ui.helpers import page_title
from mm_toolkit.ui.style import bundled_asset
from mm_toolkit.versioning import is_newer_version


class AboutTab(QWidget):
    def __init__(self):
        super().__init__()
        page_heading = page_title("About")
        logo = QLabel()
        pixmap = QPixmap(os.fspath(bundled_asset("mm-toolkit-logo.png")))
        logo.setPixmap(
            pixmap.scaled(
                300,
                300,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = QLabel("MM Toolkit")
        title.setFont(QFont("", 22, QFont.Weight.DemiBold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version = QLabel(f"Version {__version__}")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.update_link = QLabel()
        self.update_link.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.update_link.setOpenExternalLinks(True)
        self.update_link.hide()
        description = QLabel(
            "Audio & Video tools for all"
        )
        description.setWordWrap(True)
        description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        repository = QLabel(
            '<a href="https://github.com/festanqueiro/mm-toolkit">'
            "github.com/festanqueiro/mm-toolkit</a>"
        )
        repository.setOpenExternalLinks(True)
        repository.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_credit = QLabel(
            '<a href="https://fonts.google.com/icons">Google Material Icons</a> '
            "used under the Apache License 2.0."
        )
        icon_credit.setOpenExternalLinks(True)
        icon_credit.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.addWidget(page_heading)
        layout.addStretch()
        layout.addWidget(logo)
        layout.addWidget(title)
        layout.addWidget(version)
        layout.addWidget(self.update_link)
        layout.addSpacing(10)
        layout.addWidget(description)
        layout.addWidget(repository)
        layout.addWidget(icon_credit)
        layout.addStretch()

        self.update_manager = QNetworkAccessManager(self)
        request = QNetworkRequest(
            QUrl("https://api.github.com/repos/festanqueiro/mm-toolkit/releases/latest")
        )
        request.setRawHeader(b"Accept", b"application/vnd.github+json")
        request.setRawHeader(b"User-Agent", b"MM-Toolkit-update-check")
        reply = self.update_manager.get(request)
        reply.finished.connect(lambda reply=reply: self.on_update_check_finished(reply))

    def on_update_check_finished(self, reply: QNetworkReply) -> None:
        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                return
            release = json.loads(bytes(reply.readAll()).decode("utf-8"))
            tag = str(release.get("tag_name", ""))
            url = str(release.get("html_url", ""))
            if not url.startswith("https://github.com/festanqueiro/mm-toolkit/releases/"):
                return
            if is_newer_version(__version__, tag):
                display_version = tag.removeprefix("v")
                self.update_link.setText(
                    f'<a href="{html.escape(url, quote=True)}">'
                    f"Download MM Toolkit {html.escape(display_version)}</a>"
                )
                self.update_link.show()
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
            return
        finally:
            reply.deleteLater()
