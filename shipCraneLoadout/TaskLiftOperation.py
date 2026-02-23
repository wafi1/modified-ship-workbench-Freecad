# -*- coding: utf-8 -*-
"""
TaskLiftOperation.py - Single Hook Lift Operation for ship cranes
Maximises radius based on load capacity (load stages or automatic mode).
Extended with automatic stability chain.
"""

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtGui, QtCore
import math


class SingleHookLift:
    """
    Calculates and sets the optimal boom position for a given load.
    Can be used as a standalone operation or as basis for tandem lift.
    """

    def __init__(self, crane_obj):
        self.crane = crane_obj
        self.target_weight = 0.0
        self.max_allowed_radius = 0.0
        self.calculated_radius = 0.0
        self.warning_message = ""

    def calculate_optimal_radius(self, weight_t):
        """
        Calculates the maximum possible radius for the given load.
        Returns: (radius_mm, is_limited_by_capacity, warning_msg)
        """
        self.target_weight = weight_t

        if not hasattr(self.crane, "UseLoadStages"):
            return 0, False, "Crane has no load capacity data"

        crane = self.crane
        radius_mm = 0
        is_capacity_limited = True
        warning = ""

        if crane.UseLoadStages:
            # FIX: All Stage properties explicitly cast to float to avoid
            # Base.Quantity arithmetic / format errors downstream.
            stages = [
                (float(crane.Stage1_Weight), float(crane.Stage1_MinRadius), float(crane.Stage1_MaxRadius)),
                (float(crane.Stage2_Weight), float(crane.Stage2_MinRadius), float(crane.Stage2_MaxRadius)),
                (float(crane.Stage3_Weight), float(crane.Stage3_MinRadius), float(crane.Stage3_MaxRadius)),
            ]

            found_stage = None
            for weight, r_min, r_max in stages:
                if weight_t <= weight:
                    radius_mm = r_max          # now a plain Python float
                    found_stage = (weight, r_min, r_max)
                    break

            if found_stage is None:
                max_capacity = max(s[0] for s in stages)
                return 0, False, (f"Load {weight_t:.1f}t exceeds maximum "
                                  f"capacity {max_capacity:.1f}t!")

        else:
            r_min_mm = float(crane.Auto_MinRadius)
            r_max_mm = float(crane.Auto_MaxRadius)
            w_max    = float(crane.Auto_MaxWeight)
            w_min    = float(crane.Auto_MinWeight)

            if weight_t <= 0:
                return 0, False, "Invalid weight!"
            if weight_t > w_max:
                return 0, False, (f"Load {weight_t:.1f}t exceeds maximum "
                                  f"capacity {w_max:.1f}t!")

            if weight_t <= w_min:
                radius_mm = r_max_mm
                is_capacity_limited = False
                warning = f"Radius limited by boom maximum ({r_max_mm/1000:.1f}m)"
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
            warning = (f"Radius limited to configured maximum "
                       f"({absolute_max_mm/1000:.1f}m)")

        self.calculated_radius  = radius_mm
        self.max_allowed_radius = radius_mm
        return radius_mm, is_capacity_limited, warning

    def set_boom_to_radius(self, target_radius_mm):
        """Sets the boom angle to achieve the desired horizontal radius."""
        try:
            crane       = self.crane
            boom_len_mm = float(crane.BoomLength)
            boom_len_m  = boom_len_mm / 1000.0
            target_r_m  = float(target_radius_mm) / 1000.0   # FIX: guard against Quantity

            if target_r_m > boom_len_m:
                App.Console.PrintWarning(
                    f"  Target radius {target_r_m:.2f}m > boom length "
                    f"{boom_len_m:.2f}m – clamped to boom length!\n"
                )
                target_r_m = boom_len_m * 0.999

            cos_luffing = max(-1.0, min(1.0, target_r_m / boom_len_m))
            luffing_deg = math.degrees(math.acos(cos_luffing))

            crane.LuffingAngle = luffing_deg

            App.Console.PrintMessage(
                f"  Boom set to {luffing_deg:.1f}° "
                f"(radius {target_r_m:.2f}m, boom length {boom_len_m:.2f}m)\n"
            )
            return True

        except Exception as e:
            App.Console.PrintError(f"Error during boom positioning: {e}\n")
            return False

    def execute_lift(self, weight_t, target_slew_angle=None):
        """
        Executes the complete lift operation.
        Returns: (success, message, actual_radius_mm)
        """
        radius_mm, is_limited, warning = self.calculate_optimal_radius(weight_t)

        if radius_mm == 0:
            return False, warning, 0

        if target_slew_angle is not None:
            self.crane.SlewAngle = target_slew_angle

        success = self.set_boom_to_radius(radius_mm)

        if not success:
            return False, "Boom positioning failed", 0

        self.crane.Document.recompute()

        radius_m       = float(radius_mm) / 1000.0     # FIX: ensure plain float
        capacity_note  = "load capacity" if is_limited else "boom maximum"
        msg = (f"Lift configured: {weight_t:.1f}t at {radius_m:.2f}m radius "
               f"(limited by: {capacity_note})")
        if warning:
            msg += f"\nNote: {warning}"

        App.Console.PrintMessage(
            f"  Capacity: {weight_t:.1f}t at {radius_m:.2f}m radius\n")
        return True, msg, radius_mm


# =============================================================================
# DIALOG
# =============================================================================

class SingleHookLiftDialog(QtGui.QDialog):
    """
    UI for Single Hook Lift Operation.
    Allows weight input and automatic positioning.
    Supports second crane as counterweight or tandem partner.
    """

    def __init__(self, parent=None):
        super(SingleHookLiftDialog, self).__init__(parent)
        self.setWindowTitle("Single Hook Lift")
        self.setMinimumWidth(440)

        self.selected_crane  = None
        self.lift_calculator = None

        self.setupUI()
        self.findCranes()

    def setupUI(self):
        layout = QtGui.QVBoxLayout()

        # ── Main crane ───────────────────────────────────────────────────────
        crane_group  = QtGui.QGroupBox("Main Crane")
        crane_layout = QtGui.QVBoxLayout()

        self.crane_combo = QtGui.QComboBox()
        self.crane_combo.currentIndexChanged.connect(self.onCraneChanged)
        crane_layout.addWidget(self.crane_combo)

        self.capacity_info = QtGui.QLabel("No crane selected")
        self.capacity_info.setWordWrap(True)
        crane_layout.addWidget(self.capacity_info)

        crane_group.setLayout(crane_layout)
        layout.addWidget(crane_group)

        # ── Second crane ─────────────────────────────────────────────────────
        cw_group  = QtGui.QGroupBox("Second Crane  (Counterweight / Tandem partner)")
        cw_layout = QtGui.QFormLayout()

        self.cw_combo = QtGui.QComboBox()
        cw_layout.addRow("Crane:", self.cw_combo)

        self.cw_slew_input = QtGui.QDoubleSpinBox()
        self.cw_slew_input.setRange(0, 360)
        self.cw_slew_input.setValue(180)
        self.cw_slew_input.setSuffix(" °")
        self.cw_slew_input.setDecimals(1)
        self.cw_slew_input.setToolTip(
            "180° = opposite side (typical for counterweight operation)")
        cw_layout.addRow("Slew angle:", self.cw_slew_input)

        self.cw_weight_input = QtGui.QDoubleSpinBox()
        self.cw_weight_input.setRange(0.0, 1000.0)
        self.cw_weight_input.setValue(0.0)
        self.cw_weight_input.setSuffix(" t")
        self.cw_weight_input.setDecimals(1)
        self.cw_weight_input.setToolTip(
            "0 t = pure counterweight (only boom weight acts)\n"
            "> 0 t = tandem lift (load on hook of second crane)")
        cw_layout.addRow("Hook load  (0 = counterweight):", self.cw_weight_input)

        cw_group.setLayout(cw_layout)
        layout.addWidget(cw_group)

        # ── Load parameters ──────────────────────────────────────────────────
        load_group  = QtGui.QGroupBox("Load Parameters  (Main crane)")
        load_layout = QtGui.QFormLayout()

        self.weight_input = QtGui.QDoubleSpinBox()
        self.weight_input.setRange(0.1, 1000)
        self.weight_input.setValue(5.0)
        self.weight_input.setSuffix(" t")
        self.weight_input.setDecimals(1)
        load_layout.addRow("Weight:", self.weight_input)

        self.slew_input = QtGui.QDoubleSpinBox()
        self.slew_input.setRange(0, 360)
        self.slew_input.setValue(0)
        self.slew_input.setSuffix(" °")
        self.slew_input.setDecimals(1)
        load_layout.addRow("Slew angle:", self.slew_input)

        self.max_radius_check = QtGui.QCheckBox("Maximum radius for weight")
        self.max_radius_check.setChecked(True)
        self.max_radius_check.setToolTip(
            "Boom is automatically positioned at maximum radius for this load")
        load_layout.addRow("", self.max_radius_check)

        self.manual_radius = QtGui.QSpinBox()
        self.manual_radius.setRange(1000, 50000)
        self.manual_radius.setValue(10000)
        self.manual_radius.setSuffix(" mm")
        self.manual_radius.setEnabled(False)
        load_layout.addRow("Manual radius:", self.manual_radius)

        self.max_radius_check.toggled.connect(self.manual_radius.setDisabled)

        load_group.setLayout(load_layout)
        layout.addWidget(load_group)

        # ── Result ───────────────────────────────────────────────────────────
        self.result_group  = QtGui.QGroupBox("Calculation")
        result_layout      = QtGui.QVBoxLayout()

        self.result_label = QtGui.QLabel("Calculation pending...")
        self.result_label.setWordWrap(True)
        result_layout.addWidget(self.result_label)

        self.result_group.setLayout(result_layout)
        layout.addWidget(self.result_group)

        # ── Export ───────────────────────────────────────────────────────────
        self.export_btn = QtGui.QPushButton(
            "📋  Transfer & Stability Calculation")
        self.export_btn.setEnabled(False)
        self.export_btn.setStyleSheet(
            "QPushButton{background:#2d6a4f;color:white;font-weight:bold;"
            "padding:8px;border-radius:4px;font-size:11px;}"
            "QPushButton:hover{background:#1b4332;}"
            "QPushButton:disabled{background:#cccccc;color:#666;}"
        )
        self.export_btn.setToolTip(
            "1. Writes crane data to LoadCondition\n"
            "2. Runs LoadCondition recalculation\n"
            "3. Calculates hydrostatics (ShipSinkAndTrim)\n"
            "Available only after Execute.")
        self.export_btn.clicked.connect(self._export_to_loadcondition)
        layout.addWidget(self.export_btn)

        # ── Buttons ──────────────────────────────────────────────────────────
        button_layout = QtGui.QHBoxLayout()

        self.calc_btn = QtGui.QPushButton("Calculate")
        self.calc_btn.clicked.connect(self.calculateLift)

        self.execute_btn = QtGui.QPushButton("Execute")
        self.execute_btn.setDefault(True)
        self.execute_btn.clicked.connect(self.executeLift)

        cancel_btn = QtGui.QPushButton("Close")
        cancel_btn.clicked.connect(self.reject)

        button_layout.addStretch()
        button_layout.addWidget(self.calc_btn)
        button_layout.addWidget(self.execute_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)

        self.setLayout(layout)

    def findCranes(self):
        doc = App.activeDocument()
        if not doc:
            return

        self.crane_combo.clear()
        self.crane_combo.addItem("-- Select crane --", None)

        self.cw_combo.clear()
        self.cw_combo.addItem("-- No second crane --", None)

        for obj in doc.Objects:
            if getattr(getattr(obj, "Proxy", None), "Type", "") == "ShipCrane":
                mode  = "Stages" if obj.UseLoadStages else "Automatic"
                label = f"{obj.Label}  ({mode})"
                self.crane_combo.addItem(label, obj)
                self.cw_combo.addItem(label, obj)

    def onCraneChanged(self):
        crane = self.crane_combo.currentData()
        if crane is None:
            self.capacity_info.setText("No crane selected")
            self.selected_crane  = None
            return

        self.selected_crane  = crane
        self.lift_calculator = SingleHookLift(crane)

        if crane.UseLoadStages:
            # FIX: Stage_Weight properties are Base.Quantity – must use float()
            # before :.1f formatting, otherwise TypeError at runtime.
            s1w = float(crane.Stage1_Weight)
            s2w = float(crane.Stage2_Weight)
            s3w = float(crane.Stage3_Weight)
            s1r = float(crane.Stage1_MaxRadius) / 1000.0
            s2r = float(crane.Stage2_MaxRadius) / 1000.0
            s3r = float(crane.Stage3_MaxRadius) / 1000.0
            info = (f"<b>Mode:</b> Load stages<br>"
                    f"<b>Stage 1:</b> {s1w:.1f}t up to {s1r:.1f}m<br>"
                    f"<b>Stage 2:</b> {s2w:.1f}t up to {s2r:.1f}m<br>"
                    f"<b>Stage 3:</b> {s3w:.1f}t up to {s3r:.1f}m")
        else:
            r_min_m = float(crane.Auto_MinRadius) / 1000.0
            r_max_m = float(crane.Auto_MaxRadius) / 1000.0
            w_max   = float(crane.Auto_MaxWeight)
            w_min   = float(crane.Auto_MinWeight)
            m1 = w_max * r_min_m
            m2 = w_min * r_max_m
            info = (f"<b>Mode:</b> Automatic (linear interpolation)<br>"
                    f"<b>Point 1:</b> {w_max:.1f}t @ {r_min_m:.1f}m "
                    f"(M={m1:.0f} tm)<br>"
                    f"<b>Point 2:</b> {w_min:.1f}t @ {r_max_m:.1f}m "
                    f"(M={m2:.0f} tm)<br>"
                    f"<b>Boom length:</b> {float(crane.BoomLength)/1000:.1f}m")

        self.capacity_info.setText(info)

    def calculateLift(self):
        if not self.selected_crane:
            QtGui.QMessageBox.warning(
                self, "Error", "Please select a crane first!")
            return

        weight    = self.weight_input.value()
        radius_mm, is_limited, warning = \
            self.lift_calculator.calculate_optimal_radius(weight)

        if radius_mm == 0:
            self.result_label.setText(
                f"<span style='color:red'><b>Error:</b> {warning}</span>")
            return

        radius_m = float(radius_mm) / 1000.0    # FIX: guard float
        luffing  = self._calculate_luffing_for_radius(radius_mm)

        result_text = (f"<b>Max. radius:</b> {radius_m:.2f}m<br>"
                       f"<b>Luffing angle:</b> {luffing:.1f}°<br>")
        if is_limited:
            result_text += \
                "<span style='color:orange'>(Limited by load capacity)</span>"
        else:
            result_text += \
                "<span style='color:green'>(Boom maximum reached)</span>"
        if warning:
            result_text += \
                f"<br><span style='color:orange'>{warning}</span>"

        c2 = self.cw_combo.currentData()
        if c2 and c2 is not self.selected_crane:
            cw_hook = self.cw_weight_input.value()
            cw_boom = float(getattr(c2, 'BoomWeight', 0.0))
            role    = "Counterweight" if cw_hook == 0 else "Tandem partner"
            result_text += (f"<br><br><b>{c2.Label}:</b> {role}<br>"
                            f"Boom weight: {cw_boom:.1f}t, "
                            f"Hook: {cw_hook:.1f}t")

        self.result_label.setText(result_text)

    def _calculate_luffing_for_radius(self, radius_mm):
        crane      = self.selected_crane
        boom_len_m = float(crane.BoomLength) / 1000.0
        radius_m   = float(radius_mm) / 1000.0     # FIX: guard float
        if radius_m >= boom_len_m:
            return 0.0
        cos_luff = radius_m / boom_len_m
        return math.degrees(math.acos(max(-1.0, min(1.0, cos_luff))))

    def executeLift(self):
        if not self.selected_crane:
            QtGui.QMessageBox.warning(
                self, "Error", "Please select a crane first!")
            return

        weight = self.weight_input.value()
        slew   = self.slew_input.value()

        success, msg, actual_radius = \
            self.lift_calculator.execute_lift(weight, slew)

        c2 = self.cw_combo.currentData()
        if c2 and c2 is not self.selected_crane:
            cw_hook = self.cw_weight_input.value()
            cw_slew = self.cw_slew_input.value()
            lift_c2 = SingleHookLift(c2)

            if cw_hook > 0:
                # Tandem: second crane lifts its own share of the load
                ok2, msg2, _ = lift_c2.execute_lift(cw_hook, cw_slew)
                if not ok2:
                    App.Console.PrintWarning(
                        f"  {c2.Label} tandem positioning: {msg2}\n")
            else:
                # Counterweight: extend boom to maximum radius
                # FIX: Both branches already use float() – safe for stages and auto
                if c2.UseLoadStages:
                    r_max = float(c2.Stage3_MaxRadius)
                else:
                    r_max = float(c2.Auto_MaxRadius)

                lift_c2.set_boom_to_radius(r_max)
                c2.SlewAngle = cw_slew
                c2.Document.recompute()
                App.Console.PrintMessage(
                    f"  {c2.Label}: Counterweight @ {cw_slew:.1f}°, "
                    f"radius {r_max/1000:.1f}m\n")

        if success:
            self.export_btn.setEnabled(True)
            QtGui.QMessageBox.information(self, "Success", msg)
        else:
            QtGui.QMessageBox.critical(self, "Error", msg)

    def _export_to_loadcondition(self):
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
                    self, "Import error",
                    "CraneSpreadsheetTools.py not found!")
                return

        if not self.selected_crane:
            QtGui.QMessageBox.warning(self, "Error", "No crane selected!")
            return

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
            f"Hook={hook_kg_c1:.0f}kg\n")

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
                f"Hook={hook_kg_c2:.0f}kg\n")

        success, msg, hydro = transfer_crane_data_and_calculate(
            crane_data,
            auto_calculate=True,
            show_confirmation=True
        )

        if not success:
            QtGui.QMessageBox.critical(self, "Error", msg)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def create_single_hook_lift(crane_obj, weight_t, slew_angle=None):
    """
    Programmatic creation of a single hook lift.

    Args:
        crane_obj:   The crane (ShipCrane proxy object)
        weight_t:    Weight in tonnes
        slew_angle:  Optional slew angle (None = unchanged)

    Returns:
        (success, message, radius_mm)
    """
    lift = SingleHookLift(crane_obj)
    return lift.execute_lift(weight_t, slew_angle)


__all__ = ['SingleHookLift', 'SingleHookLiftDialog', 'create_single_hook_lift']
