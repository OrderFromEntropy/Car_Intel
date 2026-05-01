"""Dialog for creating and editing user profiles."""

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QScrollArea,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.profile_manager import BUILTIN_FRAMEWORKS, ProfileManager, UserProfile

_SECTION_STYLE = (
    "color: #58a6ff; font-size: 11px; font-weight: 700; letter-spacing: 0.5px; "
    "text-transform: uppercase; padding-top: 8px;"
)
_HINT_STYLE = "color: #484f58; font-size: 11px; font-style: italic;"


class ProfileDialog(QDialog):
    """Create a new profile or edit an existing one."""

    def __init__(self, profile: UserProfile | None = None, parent=None):
        super().__init__(parent)
        self._editing = profile
        self._result_profile: UserProfile | None = None
        self._build_ui(profile)
        self.setWindowTitle("Edit Profile" if profile else "New Profile")
        self.setMinimumWidth(460)
        self.setModal(True)

    def get_profile(self) -> UserProfile | None:
        return self._result_profile

    # ── UI construction ──────────────────────────────────────────────────

    def _build_ui(self, profile: UserProfile | None):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Scrollable form area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)

        content = QWidget()
        form_layout = QVBoxLayout(content)
        form_layout.setContentsMargins(24, 20, 24, 20)
        form_layout.setSpacing(6)

        # ── Identity section ─────────────────────────────────────────
        form_layout.addWidget(_section_label("Profile Identity"))

        id_form = QFormLayout()
        id_form.setSpacing(8)
        id_form.setLabelAlignment(Qt.AlignRight)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("e.g. My Tundra Hunt, Wife's Camry Search")
        if profile:
            self._name_edit.setText(profile.display_name)
        id_form.addRow("Profile name:", self._name_edit)

        self._framework_combo = QComboBox()
        for key, label in BUILTIN_FRAMEWORKS.items():
            self._framework_combo.addItem(label, userData=key)
        if profile:
            idx = self._framework_combo.findData(profile.framework)
            if idx >= 0:
                self._framework_combo.setCurrentIndex(idx)
        self._framework_combo.currentIndexChanged.connect(self._on_framework_changed)
        id_form.addRow("Evaluation framework:", self._framework_combo)

        form_layout.addLayout(id_form)

        # Framework hint
        self._framework_hint = QLabel()
        self._framework_hint.setObjectName("subtitle")
        self._framework_hint.setWordWrap(True)
        self._framework_hint.setStyleSheet(_HINT_STYLE)
        form_layout.addWidget(self._framework_hint)
        self._update_framework_hint()

        form_layout.addWidget(_divider())

        # ── Vehicle defaults section ─────────────────────────────────
        form_layout.addWidget(_section_label("Vehicle Defaults  (pre-fill the interview)"))

        d = profile.defaults if profile else {}

        veh_form = QFormLayout()
        veh_form.setSpacing(8)
        veh_form.setLabelAlignment(Qt.AlignRight)

        self._make_edit = QLineEdit()
        self._make_edit.setPlaceholderText("e.g. Toyota")
        self._make_edit.setText(str(d.get("make", "")))
        veh_form.addRow("Make:", self._make_edit)

        self._model_edit = QLineEdit()
        self._model_edit.setPlaceholderText("e.g. Tundra")
        self._model_edit.setText(str(d.get("model", "")))
        veh_form.addRow("Model:", self._model_edit)

        year_row = QHBoxLayout()
        year_row.setSpacing(8)
        self._year_min = _year_spin(d.get("year_min"))
        self._year_max = _year_spin(d.get("year_max"))
        year_row.addWidget(self._year_min)
        year_row.addWidget(QLabel("–"))
        year_row.addWidget(self._year_max)
        year_row.addStretch()
        veh_form.addRow("Year range:", year_row)

        self._trim_edit = QLineEdit()
        self._trim_edit.setPlaceholderText("e.g. 1794 Edition, Limited, or leave blank")
        self._trim_edit.setText(str(d.get("trim", "")))
        veh_form.addRow("Trim:", self._trim_edit)

        form_layout.addLayout(veh_form)
        form_layout.addWidget(_divider())

        # ── Search defaults ──────────────────────────────────────────
        form_layout.addWidget(_section_label("Search Defaults"))

        search_form = QFormLayout()
        search_form.setSpacing(8)
        search_form.setLabelAlignment(Qt.AlignRight)

        self._zip_edit = QLineEdit()
        self._zip_edit.setPlaceholderText("e.g. 75001")
        self._zip_edit.setMaxLength(10)
        self._zip_edit.setText(str(d.get("zipcode", "")))
        search_form.addRow("ZIP code:", self._zip_edit)

        self._radius_spin = QSpinBox()
        self._radius_spin.setRange(25, 1000)
        self._radius_spin.setSingleStep(25)
        self._radius_spin.setSuffix(" miles")
        self._radius_spin.setValue(int(d.get("radius_miles", 200)))
        search_form.addRow("Search radius:", self._radius_spin)

        self._price_spin = _dollar_spin(d.get("price_max"), maximum=500000, step=1000)
        self._price_spin.setSpecialValueText("No limit")
        search_form.addRow("Max budget ($):", self._price_spin)

        self._mileage_spin = _dollar_spin(d.get("mileage_max"), maximum=500000, step=5000)
        self._mileage_spin.setSuffix(" mi")
        self._mileage_spin.setSpecialValueText("No limit")
        search_form.addRow("Max mileage:", self._mileage_spin)

        form_layout.addLayout(search_form)
        form_layout.addWidget(_divider())

        # ── Notes ────────────────────────────────────────────────────
        form_layout.addWidget(_section_label("Notes / Must-Haves"))

        self._notes_edit = QTextEdit()
        self._notes_edit.setPlaceholderText(
            "e.g. No fleet vehicles, prefer original owner, must have factory tow mirrors…"
        )
        self._notes_edit.setFixedHeight(72)
        self._notes_edit.setPlainText(str(d.get("extra_notes", "")))
        form_layout.addWidget(self._notes_edit)

        form_layout.addStretch()
        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        # ── Buttons ──────────────────────────────────────────────────
        btn_bar = QWidget()
        btn_bar.setStyleSheet("background: #161b22; border-top: 1px solid #21262d;")
        btn_layout = QHBoxLayout(btn_bar)
        btn_layout.setContentsMargins(16, 10, 16, 10)

        if profile:
            delete_btn = _danger_button("Delete Profile")
            delete_btn.clicked.connect(self._on_delete)
            btn_layout.addWidget(delete_btn)

        btn_layout.addStretch()

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setObjectName("primary")
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        btn_layout.addWidget(buttons)

        root.addWidget(btn_bar)

    # ── Slots ────────────────────────────────────────────────────────────

    def _on_framework_changed(self):
        self._update_framework_hint()
        # Auto-fill make/model for tundra framework
        key = self._framework_combo.currentData()
        if key == "tundra" and not self._make_edit.text():
            self._make_edit.setText("Toyota")
            self._model_edit.setText("Tundra")
            if self._year_min.value() == 0:
                self._year_min.setValue(2014)
            if self._year_max.value() == 0:
                self._year_max.setValue(2021)

    def _update_framework_hint(self):
        key = self._framework_combo.currentData()
        hints = {
            "generic": "Standard ranking — works for any make and model.",
            "tundra": (
                "Applies hard disqualifiers (CrewMax, 5.7L V8, 4x4, 38-gal tank, "
                "approved-state provenance) and grades S–F per the Tundra Evaluation Framework."
            ),
        }
        self._framework_hint.setText(hints.get(key, ""))

    def _on_save(self):
        name = self._name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Validation", "Profile name is required.")
            return

        framework = self._framework_combo.currentData()
        defaults: dict = {}

        if self._make_edit.text().strip():
            defaults["make"] = self._make_edit.text().strip()
        if self._model_edit.text().strip():
            defaults["model"] = self._model_edit.text().strip()
        if self._year_min.value() > 0:
            defaults["year_min"] = self._year_min.value()
        if self._year_max.value() > 0:
            defaults["year_max"] = self._year_max.value()
        if self._trim_edit.text().strip():
            defaults["trim"] = self._trim_edit.text().strip()
        if self._zip_edit.text().strip():
            defaults["zipcode"] = self._zip_edit.text().strip()
        defaults["radius_miles"] = self._radius_spin.value()
        if self._price_spin.value() > 0:
            defaults["price_max"] = self._price_spin.value()
        if self._mileage_spin.value() > 0:
            defaults["mileage_max"] = self._mileage_spin.value()
        notes = self._notes_edit.toPlainText().strip()
        if notes:
            defaults["extra_notes"] = notes

        if self._editing:
            self._editing.display_name = name
            self._editing.framework = framework
            self._editing.defaults = defaults
            self._result_profile = self._editing
        else:
            self._result_profile = UserProfile(
                display_name=name,
                framework=framework,
                defaults=defaults,
            )

        ProfileManager.save(self._result_profile)
        self.accept()

    def _on_delete(self):
        if not self._editing:
            return
        reply = QMessageBox.question(
            self,
            "Delete Profile",
            f"Delete '{self._editing.display_name}'? This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            ProfileManager.delete(self._editing.id)
            self._result_profile = None
            self.accept()


# ── Widget helpers ────────────────────────────────────────────────────────────

def _section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(_SECTION_STYLE)
    return lbl


def _divider() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    f.setStyleSheet("color: #21262d; margin: 8px 0;")
    return f


def _danger_button(text: str):
    from PyQt5.QtWidgets import QPushButton
    btn = QPushButton(text)
    btn.setStyleSheet(
        "QPushButton { color: #f85149; border: 1px solid #f8514955; "
        "border-radius: 6px; padding: 5px 14px; background: transparent; }"
        "QPushButton:hover { background: #f8514915; border-color: #f85149; }"
    )
    return btn


def _year_spin(value=None) -> QSpinBox:
    spin = QSpinBox()
    spin.setRange(0, 2030)
    spin.setSpecialValueText("—")
    spin.setValue(int(value) if value else 0)
    spin.setFixedWidth(80)
    return spin


def _dollar_spin(value=None, maximum: int = 200000, step: int = 1000) -> QSpinBox:
    spin = QSpinBox()
    spin.setRange(0, maximum)
    spin.setSingleStep(step)
    spin.setValue(int(value) if value else 0)
    spin.setFixedWidth(120)
    return spin
