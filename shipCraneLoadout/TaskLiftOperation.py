# -*- coding: utf-8 -*-
"""
TaskLiftOperation.py - Single Hook Lift Operation für Schiffskräne
Maximiert die Auslage basierend auf Lastfähigkeit (Laststufen oder Automatik)
Erweitert um automatische Stabilitätskette.
"""

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtGui, QtCore
import math


class SingleHookLift:
    """
    Berechnet und setzt die optimale Boom-Position für eine gegebene Last.
    Kann als eigenständige Operation oder als Basis für Tandem-Lift verwendet werden.
    """

    def __init__(self, crane_obj):
        self.crane = crane_obj
        self.target_weight = 0.0
        self.max_allowed_radius = 0.0
        self.calculated_radius = 0.0
        self.warning_message = ""

    def calculate_optimal_radius(self, weight_t):
        """
        Berechnet die maximale mögliche Auslage für die gegebene Last.
        Returns: (radius_mm, is_limited_by_capacity, warning_msg)
        """
        self.target_weight = weight_t

        if not hasattr(self.crane, "UseLoadStages"):
            return 0, False, "Kran hat keine Lastfähigkeitsdaten"

        crane = self.crane
        radius_mm = 0
        is_capacity_limited = True
        warning = ""

        if crane.UseLoadStages:
            stages = [
                (crane.Stage1_Weight, crane.Stage1_MinRadius, crane.Stage1_MaxRadius),
                (crane.Stage2_Weight, crane.Stage2_MinRadius, crane.Stage2_MaxRadius),
                (crane.Stage3_Weight, crane.Stage3_MinRadius, crane.Stage3_MaxRadius),
            ]

            found_stage = None
            for weight, r_min, r_max in stages:
                if weight_t <= weight:
                    radius_mm = r_max
                    found_stage = (weight, r_min, r_max)
                    break

            if found_stage is None:
                max_capacity = max([s[0] for s in stages])
                return 0, False, (f"Last {weight_t:.1f}t überschreitet maximale "
                                  f"Kapazität {max_capacity:.1f}t!")

        else:
            r_min_mm = float(crane.Auto_MinRadius)
            r_max_mm = float(crane.Auto_MaxRadius)
            w_max    = float(crane.Auto_MaxWeight)
            w_min    = float(crane.Auto_MinWeight)

            if weight_t <= 0:
                return 0, False, "Ungültiges Gewicht!"
            if weight_t > w_max:
                return 0, False, (f"Last {weight_t:.1f}t überschreitet maximale "
                                  f"Kapazität {w_max:.1f}t!")

            if weight_t <= w_min:
                radius_mm = r_max_mm
                is_capacity_limited = False
                warning = f"Auslage durch Boom-Maximum begrenzt ({r_max_mm/1000:.1f}m)"
            else:
                t = (weight_t - w_min) / (w_max - w_min)
                radius_mm = r_max_mm + t * (r_min_mm - r_max_mm)
                is_capacity_limited = True

        if crane.UseLoadStages:
            absolute_max_mm = float(crane.BoomLength)
        else:
            absolute_max_mm = float(crane.Auto_MaxRadius)

        if radius_mm > absolute_max_mm:
            radius_mm = absolute_max_mm
            is_capacity_limited = False
            warning = (f"Auslage auf konfig. Maximum begrenzt "
                       f"({absolute_max_mm/1000:.1f}m)")

        self.calculated_radius  = radius_mm
        self.max_allowed_radius = radius_mm
        return radius_mm, is_capacity_limited, warning

    def set_boom_to_radius(self, target_radius_mm):
        """
        Setzt den Boom-Winkel so, dass die gewünschte horizontale Auslage
        erreicht wird.
        """
        try:
            crane       = self.crane
            boom_len_mm = float(crane.BoomLength)
            boom_len_m  = boom_len_mm / 1000.0
            target_r_m  = target_radius_mm / 1000.0

            if target_r_m > boom_len_m:
                App.Console.PrintWarning(
                    f"  Zielauslage {target_r_m:.2f}m > Baumlänge "
                    f"{boom_len_m:.2f}m – wird auf Baumlänge begrenzt!\n"
                )
                target_r_m = boom_len_m * 0.999

            cos_luffing = max(-1.0, min(1.0, target_r_m / boom_len_m))
            luffing_deg = math.degrees(math.acos(cos_luffing))

            crane.LuffingAngle = luffing_deg

            App.Console.PrintMessage(
                f"  Boom auf {luffing_deg:.1f}° eingestellt "
                f"(Auslage {target_r_m:.2f}m, Baumlänge {boom_len_m:.2f}m)\n"
            )
            return True

        except Exception as e:
            App.Console.PrintError(f"Fehler bei Boom-Positionierung: {e}\n")
            return False

    def execute_lift(self, weight_t, target_slew_angle=None):
        """
        Führt den kompletten Lift-Vorgang aus.
        Returns: (success, message, actual_radius_mm)
        """
        radius_mm, is_limited, warning = self.calculate_optimal_radius(weight_t)

        if radius_mm == 0:
            return False, warning, 0

        if target_slew_angle is not None:
            self.crane.SlewAngle = target_slew_angle

        success = self.set_boom_to_radius(radius_mm)

        if not success:
            return False, "Boom-Positionierung fehlgeschlagen", 0

        self.crane.Document.recompute()

        radius_m       = radius_mm / 1000.0
        capacity_note  = "Lastfähigkeit" if is_limited else "Boom-Maximum"
        msg = (f"Lift konfiguriert: {weight_t:.1f}t bei {radius_m:.2f}m Auslage "
               f"(Begrenzung: {capacity_note})")
        if warning:
            msg += f"\nHinweis: {warning}"

        App.Console.PrintMessage(
            f"  Lastfähigkeit: {weight_t:.1f}t bei {radius_m:.2f}m Auslage\n")
        return True, msg, radius_mm


# =============================================================================
# DIALOG
# =============================================================================

class SingleHookLiftDialog(QtGui.QDialog):
    """
    UI für Single Hook Lift Operation.
    Ermöglicht Eingabe von Gewicht und automatische Positionierung.
    Unterstützt zweiten Kran als Counterweight oder Tandem-Partner.
    """

    def __init__(self, parent=None):
        super(SingleHookLiftDialog, self).__init__(parent)
        self.setWindowTitle("Single Hook Lift")
        self.setMinimumWidth(440)

        self.selected_crane  = None
        self.lift_calculator = None

        self.setupUI()
        self.findCranes()

    # ── UI ───────────────────────────────────────────────────────────────────

    def setupUI(self):
        layout = QtGui.QVBoxLayout()

        # ── Hauptkran ────────────────────────────────────────────────────────
        crane_group  = QtGui.QGroupBox("Hauptkran")
        crane_layout = QtGui.QVBoxLayout()

        self.crane_combo = QtGui.QComboBox()
        self.crane_combo.currentIndexChanged.connect(self.onCraneChanged)
        crane_layout.addWidget(self.crane_combo)

        self.capacity_info = QtGui.QLabel("Kein Kran ausgewählt")
        self.capacity_info.setWordWrap(True)
        crane_layout.addWidget(self.capacity_info)

        crane_group.setLayout(crane_layout)
        layout.addWidget(crane_group)

        # ── Zweiter Kran (Counterweight / Tandem) ────────────────────────────
        cw_group  = QtGui.QGroupBox("Zweiter Kran  (Counterweight / Tandem-Partner)")
        cw_layout = QtGui.QFormLayout()

        self.cw_combo = QtGui.QComboBox()
        cw_layout.addRow("Kran:", self.cw_combo)

        self.cw_slew_input = QtGui.QDoubleSpinBox()
        self.cw_slew_input.setRange(0, 360)
        self.cw_slew_input.setValue(180)
        self.cw_slew_input.setSuffix(" °")
        self.cw_slew_input.setDecimals(1)
        self.cw_slew_input.setToolTip(
            "180° = Gegenseite (typisch für Counterweight-Betrieb)")
        cw_layout.addRow("Drehwinkel:", self.cw_slew_input)

        self.cw_weight_input = QtGui.QDoubleSpinBox()
        self.cw_weight_input.setRange(0.0, 1000.0)
        self.cw_weight_input.setValue(0.0)
        self.cw_weight_input.setSuffix(" t")
        self.cw_weight_input.setDecimals(1)
        self.cw_weight_input.setToolTip(
            "0 t = reines Counterweight (nur Baumgewicht wirkt)\n"
            "> 0 t = Tandem-Lift (Last am Haken des zweiten Krans)")
        cw_layout.addRow("Last am Haken  (0 = Counterweight):", self.cw_weight_input)

        cw_group.setLayout(cw_layout)
        layout.addWidget(cw_group)

        # ── Last-Parameter Hauptkran ──────────────────────────────────────────
        load_group  = QtGui.QGroupBox("Last-Parameter  (Hauptkran)")
        load_layout = QtGui.QFormLayout()

        self.weight_input = QtGui.QDoubleSpinBox()
        self.weight_input.setRange(0.1, 1000)
        self.weight_input.setValue(5.0)
        self.weight_input.setSuffix(" t")
        self.weight_input.setDecimals(1)
        load_layout.addRow("Gewicht:", self.weight_input)

        self.slew_input = QtGui.QDoubleSpinBox()
        self.slew_input.setRange(0, 360)
        self.slew_input.setValue(0)
        self.slew_input.setSuffix(" °")
        self.slew_input.setDecimals(1)
        load_layout.addRow("Drehwinkel  (Slew):", self.slew_input)

        self.max_radius_check = QtGui.QCheckBox("Maximale Auslage für Gewicht")
        self.max_radius_check.setChecked(True)
        self.max_radius_check.setToolTip(
            "Boom wird automatisch auf maximale Auslage positioniert")
        load_layout.addRow("", self.max_radius_check)

        self.manual_radius = QtGui.QSpinBox()
        self.manual_radius.setRange(1000, 50000)
        self.manual_radius.setValue(10000)
        self.manual_radius.setSuffix(" mm")
        self.manual_radius.setEnabled(False)
        load_layout.addRow("Manuelle Auslage:", self.manual_radius)

        self.max_radius_check.toggled.connect(self.manual_radius.setDisabled)

        load_group.setLayout(load_layout)
        layout.addWidget(load_group)

        # ── Berechnungs-Ergebnis ──────────────────────────────────────────────
        self.result_group  = QtGui.QGroupBox("Berechnung")
        result_layout      = QtGui.QVBoxLayout()

        self.result_label = QtGui.QLabel("Berechnung ausstehend...")
        self.result_label.setWordWrap(True)
        result_layout.addWidget(self.result_label)

        self.result_group.setLayout(result_layout)
        layout.addWidget(self.result_group)

        # ── Export-Button (ERWEITERT mit Stabilitätskette) ────────────────────
        self.export_btn = QtGui.QPushButton(
            "📋  Transfer & Stabilitätsberechnung")
        self.export_btn.setEnabled(False)
        self.export_btn.setStyleSheet(
            "QPushButton{background:#2d6a4f;color:white;font-weight:bold;"
            "padding:8px;border-radius:4px;font-size:11px;}"
            "QPushButton:hover{background:#1b4332;}"
            "QPushButton:disabled{background:#cccccc;color:#666;}"
        )
        self.export_btn.setToolTip(
            "1. Schreibt Kran-Daten ins LoadCondition\n"
            "2. Führt LoadCondition-Recalculation durch\n"
            "3. Berechnet Hydrostatik (ShipSinkAndTrim)\n"
            "Erst nach 'Ausführen' verfügbar.")
        self.export_btn.clicked.connect(self._export_to_loadcondition)
        layout.addWidget(self.export_btn)

        # ── Buttons ───────────────────────────────────────────────────────────
        button_layout = QtGui.QHBoxLayout()

        self.calc_btn = QtGui.QPushButton("Berechnen")
        self.calc_btn.clicked.connect(self.calculateLift)

        self.execute_btn = QtGui.QPushButton("Ausführen")
        self.execute_btn.setDefault(True)
        self.execute_btn.clicked.connect(self.executeLift)

        cancel_btn = QtGui.QPushButton("Schließen")
        cancel_btn.clicked.connect(self.reject)

        button_layout.addStretch()
        button_layout.addWidget(self.calc_btn)
        button_layout.addWidget(self.execute_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)

        self.setLayout(layout)

    # ── Kräne suchen ─────────────────────────────────────────────────────────

    def findCranes(self):
        doc = App.activeDocument()
        if not doc:
            return

        self.crane_combo.clear()
        self.crane_combo.addItem("-- Kran wählen --", None)

        self.cw_combo.clear()
        self.cw_combo.addItem("-- Kein zweiter Kran --", None)

        for obj in doc.Objects:
            if getattr(getattr(obj, "Proxy", None), "Type", "") == "ShipCrane":
                mode  = "Stufen" if obj.UseLoadStages else "Automatik"
                label = f"{obj.Label}  ({mode})"
                self.crane_combo.addItem(label, obj)
                self.cw_combo.addItem(label, obj)

    # ── Kran-Auswahl geändert ─────────────────────────────────────────────────

    def onCraneChanged(self):
        crane = self.crane_combo.currentData()
        if crane is None:
            self.capacity_info.setText("Kein Kran ausgewählt")
            self.selected_crane  = None
            return

        self.selected_crane  = crane
        self.lift_calculator = SingleHookLift(crane)

        if crane.UseLoadStages:
            info = (f"<b>Modus:</b> Laststufen<br>"
                    f"<b>Stufe 1:</b> {crane.Stage1_Weight:.1f}t "
                    f"bis {float(crane.Stage1_MaxRadius)/1000:.1f}m<br>"
                    f"<b>Stufe 2:</b> {crane.Stage2_Weight:.1f}t "
                    f"bis {float(crane.Stage2_MaxRadius)/1000:.1f}m<br>"
                    f"<b>Stufe 3:</b> {crane.Stage3_Weight:.1f}t "
                    f"bis {float(crane.Stage3_MaxRadius)/1000:.1f}m")
        else:
            r_min_m = float(crane.Auto_MinRadius) / 1000.0
            r_max_m = float(crane.Auto_MaxRadius) / 1000.0
            m1 = crane.Auto_MaxWeight * r_min_m
            m2 = crane.Auto_MinWeight * r_max_m
            info = (f"<b>Modus:</b> Automatik (lineare Interpolation)<br>"
                    f"<b>Punkt 1:</b> {crane.Auto_MaxWeight:.1f}t @ {r_min_m:.1f}m "
                    f"(M={m1:.0f} tm)<br>"
                    f"<b>Punkt 2:</b> {crane.Auto_MinWeight:.1f}t @ {r_max_m:.1f}m "
                    f"(M={m2:.0f} tm)<br>"
                    f"<b>Baumlänge:</b> {float(crane.BoomLength)/1000:.1f}m")

        self.capacity_info.setText(info)

    # ── Berechnen (nur Vorschau) ──────────────────────────────────────────────

    def calculateLift(self):
        if not self.selected_crane:
            QtGui.QMessageBox.warning(
                self, "Fehler", "Bitte zuerst einen Kran auswählen!")
            return

        weight    = self.weight_input.value()
        radius_mm, is_limited, warning = \
            self.lift_calculator.calculate_optimal_radius(weight)

        if radius_mm == 0:
            self.result_label.setText(
                f"<span style='color:red'><b>Fehler:</b> {warning}</span>")
            return

        radius_m = radius_mm / 1000.0
        luffing  = self._calculate_luffing_for_radius(radius_mm)

        result_text = (f"<b>Max. Auslage:</b> {radius_m:.2f}m<br>"
                       f"<b>Luffing-Winkel:</b> {luffing:.1f}°<br>")
        if is_limited:
            result_text += \
                "<span style='color:orange'>(Begrenzt durch Lastfähigkeit)</span>"
        else:
            result_text += \
                "<span style='color:green'>(Boom-Maximum erreicht)</span>"
        if warning:
            result_text += \
                f"<br><span style='color:orange'>{warning}</span>"

        # Zweiter Kran
        c2 = self.cw_combo.currentData()
        if c2 and c2 is not self.selected_crane:
            cw_hook = self.cw_weight_input.value()
            cw_boom = float(getattr(c2, 'BoomWeight', 0.0))
            role    = "Counterweight" if cw_hook == 0 else "Tandem-Partner"
            result_text += (f"<br><br><b>{c2.Label}:</b> {role}<br>"
                            f"Baumgewicht: {cw_boom:.1f}t, "
                            f"Haken: {cw_hook:.1f}t")

        self.result_label.setText(result_text)

    def _calculate_luffing_for_radius(self, radius_mm):
        crane      = self.selected_crane
        boom_len_m = float(crane.BoomLength) / 1000.0
        radius_m   = radius_mm / 1000.0
        if radius_m >= boom_len_m:
            return 0.0
        cos_luff = radius_m / boom_len_m
        return math.degrees(math.acos(max(-1.0, min(1.0, cos_luff))))

    # ── Ausführen ─────────────────────────────────────────────────────────────

    def executeLift(self):
        if not self.selected_crane:
            QtGui.QMessageBox.warning(
                self, "Fehler", "Bitte zuerst einen Kran auswählen!")
            return

        weight = self.weight_input.value()
        slew   = self.slew_input.value()

        # Hauptkran positionieren
        success, msg, actual_radius = \
            self.lift_calculator.execute_lift(weight, slew)

        # Zweiten Kran positionieren falls ausgewählt
        c2 = self.cw_combo.currentData()
        if c2 and c2 is not self.selected_crane:
            cw_hook = self.cw_weight_input.value()
            cw_slew = self.cw_slew_input.value()
            lift_c2 = SingleHookLift(c2)

            if cw_hook > 0:
                # Tandem: zweiter Kran trägt auch Last
                ok2, msg2, _ = lift_c2.execute_lift(cw_hook, cw_slew)
                if not ok2:
                    App.Console.PrintWarning(
                        f"  {c2.Label} Tandem-Positionierung: {msg2}\n")
            else:
                # Counterweight: Boom auf maximale Auslage (leerer Haken)
                r_max = (float(c2.Auto_MaxRadius)
                         if not c2.UseLoadStages
                         else float(c2.Stage3_MaxRadius))
                lift_c2.set_boom_to_radius(r_max)
                c2.SlewAngle = cw_slew
                c2.Document.recompute()
                App.Console.PrintMessage(
                    f"  {c2.Label}: Counterweight @ {cw_slew:.1f}°, "
                    f"Auslage {r_max/1000:.1f}m\n")

        if success:
            self.export_btn.setEnabled(True)
            QtGui.QMessageBox.information(self, "Erfolg", msg)
            # Dialog offen lassen damit Export noch möglich ist
        else:
            QtGui.QMessageBox.critical(self, "Fehler", msg)

    # ── Export → LoadCondition mit kompletter Stabilitätskette ────────────────

    def _export_to_loadcondition(self):
        """Export zu LoadCondition mit automatischer Stabilitätskette."""
        # NEU: Import der erweiterten Funktion mit Stabilitätskette
        try:
            from .CraneSpreadsheetTools import (
                transfer_crane_data_and_calculate,
                get_crane_positions
            )
        except ImportError:
            try:
                from CraneSpreadsheetTools import (
                    transfer_crane_data_and_calculate,
                    get_crane_positions
                )
            except ImportError:
                QtGui.QMessageBox.critical(
                    self, "Import-Fehler",
                    "CraneSpreadsheetTools.py nicht gefunden!")
                return

        if not self.selected_crane:
            QtGui.QMessageBox.warning(self, "Fehler", "Kein Kran ausgewählt!")
            return

        # Kran-Daten sammeln
        c1 = self.selected_crane
        boom_c1, hook_c1 = get_crane_positions(c1)
        hook_kg_c1 = self.weight_input.value() * 1000.0
        boom_kg_c1 = float(getattr(c1, 'BoomWeight', 0.0)) * 1000.0

        crane_data = {
            c1.Label: {
                'boom_kg':  boom_kg_c1,
                'hook_kg':  hook_kg_c1,
                'boom_pos': boom_c1,
                'hook_pos': hook_c1,
            }
        }

        App.Console.PrintMessage(
            f"  {c1.Label}: Boom={boom_kg_c1:.0f}kg "
            f"Haken={hook_kg_c1:.0f}kg\n")

        # Zweiter Kran
        c2 = self.cw_combo.currentData()
        if c2 and c2 is not c1:
            boom_c2, hook_c2 = get_crane_positions(c2)
            hook_kg_c2 = self.cw_weight_input.value() * 1000.0
            boom_kg_c2 = float(getattr(c2, 'BoomWeight', 0.0)) * 1000.0
            role = "Counterweight" if hook_kg_c2 == 0 else "Tandem"

            crane_data[c2.Label] = {
                'boom_kg':  boom_kg_c2,
                'hook_kg':  hook_kg_c2,
                'boom_pos': boom_c2,
                'hook_pos': hook_c2,
            }
            App.Console.PrintMessage(
                f"  {c2.Label}: {role} Boom={boom_kg_c2:.0f}kg "
                f"Haken={hook_kg_c2:.0f}kg\n")

        # KOMPLETTE KETTE ausführen (Schritt 1+2+3)
        # Schritt 1: Kran-Daten schreiben
        # Schritt 2: LoadCondition Recalculation
        # Schritt 3: Hydrostatische Berechnung
        success, msg, hydro = transfer_crane_data_and_calculate(
            crane_data,
            auto_calculate=True,
            show_confirmation=True  # Zeigt Bestätigungsdialog vor Berechnung
        )

        if success:
            # Erfolg wird bereits im transfer_crane_data_and_calculate Dialog angezeigt
            pass
        else:
            QtGui.QMessageBox.critical(self, "Fehler", msg)


# =============================================================================
# HILFSFUNKTIONEN FÜR EXTERNEN ZUGRIFF
# =============================================================================

def create_single_hook_lift(crane_obj, weight_t, slew_angle=None):
    """
    Programmatische Erstellung eines Single Hook Lifts.

    Args:
        crane_obj:   Der Kran (ShipCrane Proxy Objekt)
        weight_t:    Gewicht in Tonnen
        slew_angle:  Optionaler Drehwinkel (None = unverändert)

    Returns:
        (success, message, radius_mm)
    """
    lift = SingleHookLift(crane_obj)
    return lift.execute_lift(weight_t, slew_angle)


__all__ = ['SingleHookLift', 'SingleHookLiftDialog', 'create_single_hook_lift']
