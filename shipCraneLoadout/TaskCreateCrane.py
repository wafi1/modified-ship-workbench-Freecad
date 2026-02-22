# -*- coding: utf-8 -*-
"""
TaskCreateCrane.py - Ship crane with UI, coupling and load capacity calculation
"""

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtGui, QtCore
import Part
import math


def to_float(quantity):
    if hasattr(quantity, 'Value'):
        return float(quantity.Value)
    return float(quantity)


class ShipCrane:
    """
    FeaturePython proxy for a ship crane with load capacity calculation.
    """

    def __init__(self, obj):
        self.Type = "ShipCrane"
        obj.Proxy = self
        self._init_properties(obj)

    def _init_properties(self, obj):
        all_props = [
            # --- Motion ---
            ("App::PropertyFloat",     "SlewAngle",         "Motion",       "Slew angle in degrees",                    0.0),
            ("App::PropertyFloat",     "LuffingAngle",      "Motion",       "Luffing angle in degrees",                 15.0),
            # --- Weights ---
            ("App::PropertyFloat",     "BoomWeight",        "Weights",      "Boom self-weight [t]",                     18.0),
            # --- Boom geometry ---
            ("App::PropertyLength",    "BoomPivotHeight",   "Geometry",     "Height of boom pivot",                     2300),
            ("App::PropertyLength",    "BoomLegWidth",      "Geometry",     "Boom leg width",                           500),
            ("App::PropertyLength",    "BoomLegHeight",     "Geometry",     "Boom leg height",                          1400),
            ("App::PropertyLength",    "BoomInnerWidth",    "Geometry",     "Boom inner width",                         2600),
            ("App::PropertyLength",    "BoomLength",        "Geometry",     "Boom length",                              30500),
            ("App::PropertyLength",    "BoomWidthOuterEnd", "Geometry",     "Boom width at outer end",                  2500),
            ("App::PropertyLength",    "BoomCGDistance",    "Geometry",     "Boom CG distance from pivot",              17200),
            ("App::PropertyLength",    "SheaveWidth",       "Geometry",     "Sheave width",                             1800),
            ("App::PropertyLength",    "SheaveDiameter",    "Geometry",     "Sheave diameter",                          1520),
            # --- Tower / base geometry ---
            ("App::PropertyLength",    "BaseDiameter",      "Geometry",     "Base diameter",                            3700),
            ("App::PropertyLength",    "BaseHeight",        "Geometry",     "Base height",                              2300),
            ("App::PropertyLength",    "TowerHeight",       "Geometry",     "Tower height",                             10500),
            ("App::PropertyLength",    "TowerTopDiameter",  "Geometry",     "Tower top diameter",                       2500),
            ("App::PropertyLength",    "TowerFlatWidth",    "Geometry",     "Tower flat width",                         2500),
            ("App::PropertyLength",    "TowerFlatHeight",   "Geometry",     "Tower flat height",                        2300),
            # --- Coupling ---
            ("App::PropertyLink",      "ParentShip",        "Coupling",     "Linked ship",                              None),
            ("App::PropertyBool",      "IsCoupled",         "Coupling",     "Is coupled to ship",                       False),
            ("App::PropertyPlacement", "RelativePlacement", "Coupling",     "Position relative to ship",                None),
            # --- Load capacity mode ---
            ("App::PropertyBool",      "UseLoadStages",     "LoadCapacity", "Load stages (True) or automatic (False)",  True),
            # --- Load stages ---
            ("App::PropertyFloat",     "Stage1_Weight",     "LoadStage1",   "Stage 1: maximum load [t]",                10.0),
            ("App::PropertyLength",    "Stage1_MinRadius",  "LoadStage1",   "Stage 1: minimum radius [mm]",             5000),
            ("App::PropertyLength",    "Stage1_MaxRadius",  "LoadStage1",   "Stage 1: maximum radius [mm]",             8000),
            ("App::PropertyFloat",     "Stage2_Weight",     "LoadStage2",   "Stage 2: medium load [t]",                 6.0),
            ("App::PropertyLength",    "Stage2_MinRadius",  "LoadStage2",   "Stage 2: minimum radius [mm]",             8000),
            ("App::PropertyLength",    "Stage2_MaxRadius",  "LoadStage2",   "Stage 2: maximum radius [mm]",             15000),
            ("App::PropertyFloat",     "Stage3_Weight",     "LoadStage3",   "Stage 3: minimum load [t]",                3.0),
            ("App::PropertyLength",    "Stage3_MinRadius",  "LoadStage3",   "Stage 3: minimum radius [mm]",             15000),
            ("App::PropertyLength",    "Stage3_MaxRadius",  "LoadStage3",   "Stage 3: maximum radius [mm]",             22000),
            # --- Automatic ---
            ("App::PropertyFloat",     "Auto_MaxWeight",    "LoadAuto",     "Automatic: max load at min radius [t]",    10.0),
            ("App::PropertyLength",    "Auto_MinRadius",    "LoadAuto",     "Automatic: radius for max load [mm]",      5000),
            ("App::PropertyFloat",     "Auto_MinWeight",    "LoadAuto",     "Automatic: min load at max radius [t]",    2.0),
            ("App::PropertyLength",    "Auto_MaxRadius",    "LoadAuto",     "Automatic: radius for min load [mm]",      22000),
            # --- Output ---
            ("App::PropertyFloat",     "CurrentMaxLoad",    "LoadOutput",   "Currently allowed maximum load [t]",       0.0),
            ("App::PropertyFloat",     "CurrentLoadMoment", "LoadOutput",   "Current load moment [tm]",                 0.0),
            ("App::PropertyFloat",     "CurrentRadius",     "LoadOutput",   "Current radius [mm]",                      0.0),
            ("App::PropertyBool",      "OverloadWarning",   "LoadOutput",   "Overload warning",                         False),
            # --- Appearance ---
            ("App::PropertyColor",     "CraneColor",        "Appearance",   "Crane colour",                             (1.0, 0.843, 0.0)),
            ("App::PropertyBool",      "ShowAxes",          "Appearance",   "Show axes",                                True),
            # --- Output vectors (world coordinates) ---
            ("App::PropertyVector",    "SheavePosition",    "Output",       "Sheave position (world coordinates mm)",   None),
            ("App::PropertyVector",    "BoomCGPosition",    "Output",       "Boom CG position (world coordinates mm)",  None),
        ]

        added = []
        for prop_type, prop_name, group, tooltip, default in all_props:
            if not hasattr(obj, prop_name):
                obj.addProperty(prop_type, prop_name, group, tooltip)
                if default is not None:
                    setattr(obj, prop_name, default)
                added.append(prop_name)

        if added:
            App.Console.PrintMessage(
                "ShipCrane: Added missing properties: " + str(added) + "\n")

        for prop in ["SheavePosition", "BoomCGPosition", "CurrentMaxLoad",
                     "CurrentLoadMoment", "CurrentRadius", "OverloadWarning"]:
            if hasattr(obj, prop):
                obj.setEditorMode(prop, 1)

    def onDocumentRestored(self, obj):
        self._init_properties(obj)
        obj.touch()

    def execute(self, obj):
        if getattr(self, '_recomputing', False):
            return
        self._recomputing = True
        try:
            self._init_properties(obj)

            if (getattr(obj, 'IsCoupled', False) and
                    getattr(obj, 'ParentShip', None) is not None):
                try:
                    ship = obj.ParentShip
                    obj.Placement = ship.Placement * obj.RelativePlacement
                except Exception as e:
                    App.Console.PrintWarning(
                        f"  Coupling: placement update failed: {e}\n")

            required_props = [
                "TowerHeight", "BaseDiameter", "BaseHeight", "TowerTopDiameter",
                "TowerFlatWidth", "TowerFlatHeight", "BoomPivotHeight", "BoomLegWidth",
                "BoomLegHeight", "BoomInnerWidth", "BoomLength", "BoomWidthOuterEnd",
                "BoomCGDistance", "SheaveWidth", "SheaveDiameter",
                "SlewAngle", "LuffingAngle"
            ]
            missing = [p for p in required_props if not hasattr(obj, p)]
            if missing:
                App.Console.PrintError(
                    "ShipCrane.execute: Missing properties: " + str(missing) + "\n")
                return

            base_dia      = to_float(obj.BaseDiameter)
            base_h        = to_float(obj.BaseHeight)
            tower_h       = to_float(obj.TowerHeight)
            tower_top_dia = to_float(obj.TowerTopDiameter)
            tower_flat_w  = to_float(obj.TowerFlatWidth)
            tower_flat_h  = to_float(obj.TowerFlatHeight)
            boom_pivot_h  = to_float(obj.BoomPivotHeight)
            boom_leg_w    = to_float(obj.BoomLegWidth)
            boom_leg_h    = to_float(obj.BoomLegHeight)
            boom_inner_w  = to_float(obj.BoomInnerWidth)
            boom_len      = to_float(obj.BoomLength)
            boom_end_w    = to_float(obj.BoomWidthOuterEnd)
            sheave_w      = to_float(obj.SheaveWidth)
            sheave_dia    = to_float(obj.SheaveDiameter)

            slew_angle_deg    = float(obj.SlewAngle)
            luffing_angle_deg = float(obj.LuffingAngle)
            slew_angle_rad    = math.radians(slew_angle_deg)
            luffing_angle_rad = math.radians(luffing_angle_deg)

            if not hasattr(self, '_last_debug'):
                self._last_debug = (0, 0)
            current_debug = (round(slew_angle_deg), round(luffing_angle_deg))
            if self._last_debug != current_debug:
                App.Console.PrintMessage(
                    f"Slew: {slew_angle_deg}°, Luffing: {luffing_angle_deg}°\n")
                self._last_debug = current_debug

            shapes = []

            base = Part.makeCylinder(
                base_dia / 2, base_h,
                App.Vector(0, 0, 0), App.Vector(0, 0, 1))
            shapes.append(base)

            tower = self._create_tower(
                base_h, tower_h, base_dia, tower_top_dia, tower_flat_w, tower_flat_h)
            if tower:
                shapes.append(tower)

            boom_shapes = self._create_boom(
                base_h, boom_pivot_h, boom_leg_w, boom_leg_h,
                boom_inner_w, boom_len, boom_end_w, luffing_angle_deg)
            shapes.extend(boom_shapes)

            sheave = self._create_sheave(
                base_h, boom_pivot_h, boom_len,
                sheave_w, sheave_dia, luffing_angle_deg)
            if sheave:
                shapes.append(sheave)

            if hasattr(obj, "ShowAxes") and obj.ShowAxes:
                axes = self._create_axes(
                    base_h, tower_h, boom_pivot_h, boom_inner_w, boom_leg_w)
                shapes.extend(axes)

            if shapes:
                base_shape     = shapes[0]
                rotating_parts = shapes[1:]

                if rotating_parts:
                    rotating_compound = Part.makeCompound(rotating_parts)
                    rotation_center   = App.Vector(0, 0, base_h)
                    if abs(slew_angle_deg) > 0.001:
                        rotating_compound = rotating_compound.rotate(
                            rotation_center, App.Vector(0, 0, 1), slew_angle_deg)
                    obj.Shape = Part.makeCompound([base_shape, rotating_compound])
                else:
                    obj.Shape = Part.makeCompound([base_shape])

                if hasattr(obj, "ViewObject") and hasattr(obj, "CraneColor"):
                    obj.ViewObject.ShapeColor = obj.CraneColor
            else:
                obj.Shape = Part.Shape()

            self._update_positions(
                obj, slew_angle_rad, luffing_angle_rad,
                base_h, boom_pivot_h, boom_len, obj.BoomCGDistance)
            self._update_load_capacity(obj)

        except Exception as e:
            App.Console.PrintError("Error in execute: " + str(e) + "\n")
            import traceback
            traceback.print_exc()
        finally:
            self._recomputing = False

    # ── Geometry ──────────────────────────────────────────────────────────────

    def _create_tower(self, base_h, tower_h, base_dia, top_dia, flat_w, flat_h):
        try:
            tower     = Part.makeCone(
                base_dia / 2, top_dia / 2, tower_h,
                App.Vector(0, 0, base_h), App.Vector(0, 0, 1))
            half_flat = flat_w / 2
            cut_depth = (base_dia - flat_w) / 2 + 100
            left_cut  = Part.makeBox(
                cut_depth, base_dia + 200, flat_h + 100,
                App.Vector(-base_dia / 2 - 50, -(base_dia + 200) / 2, base_h - 50))
            right_cut = Part.makeBox(
                cut_depth, base_dia + 200, flat_h + 100,
                App.Vector(half_flat - 50, -(base_dia + 200) / 2, base_h - 50))
            return tower.cut(left_cut).cut(right_cut)
        except Exception as e:
            App.Console.PrintError("Tower error: " + str(e) + "\n")
            return None

    def _create_boom(self, base_h, pivot_h, leg_w, leg_h,
                     inner_w, boom_len, end_w, luffing_angle_deg):
        shapes = []
        try:
            luffing_rad  = math.radians(luffing_angle_deg)
            pivot_z      = base_h + pivot_h
            end_y        = boom_len * math.cos(luffing_rad)
            end_z        = pivot_z + boom_len * math.sin(luffing_rad)
            y_offset     = 200
            left_x       = -(inner_w / 2 + leg_w / 2)
            right_x      =  (inner_w / 2 + leg_w / 2)
            end_half_w   = end_w / 2
            left_end_x   = -end_half_w + leg_w / 2
            right_end_x  =  end_half_w - leg_w / 2

            for x1, x2 in [(left_x, left_end_x), (right_x, right_end_x)]:
                w2 = leg_w * 0.8
                h2 = leg_h * 0.8
                p1 = App.Vector(x1 - leg_w/2, y_offset, pivot_z)
                p2 = App.Vector(x1 + leg_w/2, y_offset, pivot_z)
                p3 = App.Vector(x1 + leg_w/2, y_offset, pivot_z + leg_h)
                p4 = App.Vector(x1 - leg_w/2, y_offset, pivot_z + leg_h)
                p5 = App.Vector(x2 - w2/2, end_y + y_offset, end_z)
                p6 = App.Vector(x2 + w2/2, end_y + y_offset, end_z)
                p7 = App.Vector(x2 + w2/2, end_y + y_offset, end_z + h2)
                p8 = App.Vector(x2 - w2/2, end_y + y_offset, end_z + h2)
                wire1 = Part.Wire([
                    Part.makeLine(p1, p2), Part.makeLine(p2, p3),
                    Part.makeLine(p3, p4), Part.makeLine(p4, p1)])
                wire2 = Part.Wire([
                    Part.makeLine(p5, p6), Part.makeLine(p6, p7),
                    Part.makeLine(p7, p8), Part.makeLine(p8, p5)])
                shapes.append(Part.makeLoft([wire1, wire2], True))

            cross_pivot_w = abs(right_x - left_x) + leg_w
            shapes.append(Part.makeBox(
                cross_pivot_w, 400, 300,
                App.Vector(left_x - leg_w/2, y_offset - 200, pivot_z - 150)))
            cross_end_w = abs(right_end_x - left_end_x) + leg_w
            shapes.append(Part.makeBox(
                cross_end_w, 400, 300,
                App.Vector(left_end_x - leg_w/2,
                           end_y + y_offset - 200, end_z - 150)))
        except Exception as e:
            App.Console.PrintError("Boom error: " + str(e) + "\n")
        return shapes

    def _create_sheave(self, base_h, pivot_h, boom_len,
                       sheave_w, sheave_dia, luffing_angle_deg):
        try:
            luffing_rad = math.radians(luffing_angle_deg)
            pivot_z     = base_h + pivot_h
            end_y       = boom_len * math.cos(luffing_rad)
            end_z       = pivot_z + boom_len * math.sin(luffing_rad)
            y_offset    = 200
            leg_h       = 1400
            return Part.makeCylinder(
                sheave_dia / 2, sheave_w,
                App.Vector(-sheave_w / 2, end_y + y_offset,
                           end_z + leg_h / 2 - sheave_dia / 2),
                App.Vector(1, 0, 0))
        except:
            return None

    def _create_axes(self, base_h, tower_h, pivot_h, inner_w, leg_w):
        shapes = []
        try:
            shapes.append(Part.makeCylinder(
                50, base_h + tower_h + 2000,
                App.Vector(0, 0, -1000), App.Vector(0, 0, 1)))
            pivot_z = base_h + pivot_h
            total_w = inner_w + leg_w + 1000
            shapes.append(Part.makeCylinder(
                30, total_w,
                App.Vector(-total_w / 2, 0, pivot_z), App.Vector(1, 0, 0)))
        except:
            pass
        return shapes

    # ── Position update ───────────────────────────────────────────────────────

    def _update_positions(self, obj, slew_angle_rad, luffing_angle_rad,
                          base_h, pivot_h, boom_len, cg_dist):
        try:
            base_h_f   = to_float(base_h)
            pivot_h_f  = to_float(pivot_h)
            boom_len_f = to_float(boom_len)
            cg_dist_f  = to_float(cg_dist)
            pivot_z    = base_h_f + pivot_h_f

            cos_s = math.cos(slew_angle_rad)
            sin_s = math.sin(slew_angle_rad)

            crane_world = obj.Placement.Base
            wx = crane_world.x
            wy = crane_world.y
            wz = crane_world.z

            sl_y = boom_len_f * math.cos(luffing_angle_rad)
            sl_z = pivot_z + boom_len_f * math.sin(luffing_angle_rad)

            if hasattr(obj, "SheavePosition"):
                obj.SheavePosition = App.Vector(
                    wx + (-sl_y * sin_s),
                    wy + ( sl_y * cos_s),
                    wz +   sl_z)

            cg_y = cg_dist_f * math.cos(luffing_angle_rad)
            cg_z = pivot_z + cg_dist_f * math.sin(luffing_angle_rad)

            if hasattr(obj, "BoomCGPosition"):
                obj.BoomCGPosition = App.Vector(
                    wx + (-cg_y * sin_s),
                    wy + ( cg_y * cos_s),
                    wz +   cg_z)

            if not hasattr(self, '_last_pos_debug'):
                self._last_pos_debug = None
            new_debug = (round(wx), round(wy))
            if self._last_pos_debug != new_debug:
                App.Console.PrintMessage(
                    f"  Crane foot world: ({wx/1000:.2f}, {wy/1000:.2f}, {wz/1000:.2f}) m\n"
                    f"  Sheave world:     "
                    f"({(wx + (-sl_y*sin_s))/1000:.2f}, "
                    f"{(wy + (sl_y*cos_s))/1000:.2f}, "
                    f"{(wz + sl_z)/1000:.2f}) m\n")
                self._last_pos_debug = new_debug

        except Exception as e:
            App.Console.PrintError(
                "Error in _update_positions: " + str(e) + "\n")

    def _update_load_capacity(self, obj):
        try:
            if not hasattr(obj, "SheavePosition"):
                return
            sheave_pos = obj.SheavePosition

            crane_world = obj.Placement.Base
            dx = sheave_pos.x - crane_world.x
            dy = sheave_pos.y - crane_world.y
            radius_mm = math.sqrt(dx ** 2 + dy ** 2)
            radius_m  = radius_mm / 1000.0

            obj.CurrentRadius = radius_mm
            max_load_t = 0.0

            if obj.UseLoadStages:
                r = radius_mm
                if to_float(obj.Stage1_MinRadius) <= r <= to_float(obj.Stage1_MaxRadius):
                    max_load_t = obj.Stage1_Weight
                elif to_float(obj.Stage2_MinRadius) <= r <= to_float(obj.Stage2_MaxRadius):
                    max_load_t = obj.Stage2_Weight
                elif to_float(obj.Stage3_MinRadius) <= r <= to_float(obj.Stage3_MaxRadius):
                    max_load_t = obj.Stage3_Weight
            else:
                r_min_m = to_float(obj.Auto_MinRadius) / 1000.0
                r_max_m = to_float(obj.Auto_MaxRadius) / 1000.0
                w_max   = obj.Auto_MaxWeight
                w_min   = obj.Auto_MinWeight
                if radius_m <= r_min_m:
                    max_load_t = w_max
                elif radius_m >= r_max_m:
                    max_load_t = w_min
                else:
                    t = (radius_m - r_min_m) / (r_max_m - r_min_m)
                    max_load_t = w_max + t * (w_min - w_max)

            obj.CurrentMaxLoad    = max_load_t
            obj.CurrentLoadMoment = max_load_t * radius_m if max_load_t > 0 else 0

            if not hasattr(self, '_last_load_debug'):
                self._last_load_debug = 0
            current_load = round(max_load_t * 10)
            if self._last_load_debug != current_load:
                mode = "Stages" if obj.UseLoadStages else "Automatic"
                App.Console.PrintMessage(
                    f"  Capacity ({mode}): {max_load_t:.1f}t "
                    f"at {radius_m:.2f}m radius\n")
                self._last_load_debug = current_load

        except Exception as e:
            App.Console.PrintError("Load capacity error: " + str(e) + "\n")

    def check_load(self, obj, actual_load_t):
        max_allowed = obj.CurrentMaxLoad
        is_allowed  = actual_load_t <= max_allowed
        radius_m    = obj.CurrentRadius / 1000.0 if obj.CurrentRadius > 0 else 0
        if is_allowed:
            msg = (f"OK: Load {actual_load_t}t allowed at {radius_m}m"
                   if max_allowed > 0
                   else f"Warning: Radius {radius_m}m outside range")
        else:
            msg = f"OVERLOAD! {actual_load_t}t > max {max_allowed}t"
        obj.OverloadWarning = not is_allowed
        return is_allowed, max_allowed, msg

    def onChanged(self, obj, prop):
        trigger_props = [
            "SlewAngle", "LuffingAngle", "UseLoadStages",
            "Stage1_Weight", "Stage1_MinRadius", "Stage1_MaxRadius",
            "Stage2_Weight", "Stage2_MinRadius", "Stage2_MaxRadius",
            "Stage3_Weight", "Stage3_MinRadius", "Stage3_MaxRadius",
            "Auto_MaxWeight", "Auto_MinRadius", "Auto_MinWeight", "Auto_MaxRadius",
        ]
        if prop in trigger_props:
            if not getattr(self, '_recomputing', False):
                obj.touch()

    def __getstate__(self):
        return self.Type

    def __setstate__(self, state):
        if state:
            self.Type = state


# =============================================================================
# DIALOG
# =============================================================================

class ShipCraneDialog(QtGui.QDialog):
    def __init__(self, parent=None):
        super(ShipCraneDialog, self).__init__(parent)
        self.setWindowTitle("Create Ship Crane")
        self.setMinimumWidth(450)
        self.crane = None
        self.ship  = None
        self.setupUI()
        self.findShips()

    def setupUI(self):
        scroll    = QtGui.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        container = QtGui.QWidget()
        layout    = QtGui.QVBoxLayout(container)

        # ── Name ─────────────────────────────────────────────────────────────
        name_group  = QtGui.QGroupBox("Name")
        name_layout = QtGui.QHBoxLayout()
        name_layout.addWidget(QtGui.QLabel("Crane name:"))
        self.name_input = QtGui.QLineEdit("ShipCrane")
        name_layout.addWidget(self.name_input)
        name_group.setLayout(name_layout)
        layout.addWidget(name_group)

        # ── Coupling ─────────────────────────────────────────────────────────
        ship_group  = QtGui.QGroupBox("Coupling to ship")
        ship_layout = QtGui.QVBoxLayout()
        self.ship_combo = QtGui.QComboBox()
        self.ship_combo.addItem("-- No ship --")
        ship_layout.addWidget(self.ship_combo)
        pos_note = QtGui.QLabel(
            "ℹ️  Create the crane first, then move it to the\n"
            "    desired position on the ship.\n"
            "    Then call couple_crane_to_ship().")
        pos_note.setStyleSheet("color: #666; font-size: 10px;")
        ship_layout.addWidget(pos_note)
        ship_group.setLayout(ship_layout)
        layout.addWidget(ship_group)

        # ── Motion ───────────────────────────────────────────────────────────
        motion_group  = QtGui.QGroupBox("Motion")
        motion_layout = QtGui.QFormLayout()
        self.slew_input = QtGui.QDoubleSpinBox()
        self.slew_input.setRange(0, 360); self.slew_input.setValue(0)
        self.slew_input.setSuffix(" °")
        motion_layout.addRow("Slew angle:", self.slew_input)
        self.luffing_input = QtGui.QDoubleSpinBox()
        self.luffing_input.setRange(0, 90); self.luffing_input.setValue(15)
        self.luffing_input.setSuffix(" °")
        motion_layout.addRow("Luffing angle:", self.luffing_input)
        motion_group.setLayout(motion_layout)
        layout.addWidget(motion_group)

        # ── Weights ──────────────────────────────────────────────────────────
        weights_group  = QtGui.QGroupBox("Weights")
        weights_layout = QtGui.QFormLayout()
        self.boom_weight_input = QtGui.QDoubleSpinBox()
        self.boom_weight_input.setRange(0.0, 500.0); self.boom_weight_input.setValue(18.0)
        self.boom_weight_input.setSuffix(" t"); self.boom_weight_input.setDecimals(2)
        weights_layout.addRow("Boom self-weight:", self.boom_weight_input)
        weights_group.setLayout(weights_layout)
        layout.addWidget(weights_group)

        # ── Load capacity ─────────────────────────────────────────────────────
        load_group  = QtGui.QGroupBox("Load Capacity")
        load_layout = QtGui.QVBoxLayout()
        self.load_mode_combo = QtGui.QComboBox()
        self.load_mode_combo.addItem("Load stages (3 stages)", "stages")
        self.load_mode_combo.addItem("Automatic (moment)",     "auto")
        load_layout.addWidget(self.load_mode_combo)
        self.load_stack = QtGui.QStackedWidget()

        stages_widget = QtGui.QWidget()
        stages_layout = QtGui.QVBoxLayout()
        for stage_num, (w_def, r_min_def, r_max_def) in enumerate(
                [(10.0, 5000, 8000), (6.0, 8000, 15000), (3.0, 15000, 22000)], 1):
            sg  = QtGui.QGroupBox(f"Stage {stage_num}")
            sfl = QtGui.QFormLayout()
            w_spin = QtGui.QDoubleSpinBox()
            w_spin.setRange(0.1, 1000); w_spin.setValue(w_def); w_spin.setSuffix(" t")
            sfl.addRow("Max. load:", w_spin)
            r_min_spin = QtGui.QSpinBox()
            r_min_spin.setRange(1000, 100000); r_min_spin.setValue(r_min_def)
            r_min_spin.setSuffix(" mm"); sfl.addRow("Min. radius:", r_min_spin)
            r_max_spin = QtGui.QSpinBox()
            r_max_spin.setRange(1000, 100000); r_max_spin.setValue(r_max_def)
            r_max_spin.setSuffix(" mm"); sfl.addRow("Max. radius:", r_max_spin)
            sg.setLayout(sfl); stages_layout.addWidget(sg)
            setattr(self, f"s{stage_num}_weight", w_spin)
            setattr(self, f"s{stage_num}_min_r",  r_min_spin)
            setattr(self, f"s{stage_num}_max_r",  r_max_spin)
        stages_widget.setLayout(stages_layout)
        self.load_stack.addWidget(stages_widget)

        auto_widget = QtGui.QWidget()
        auto_layout = QtGui.QVBoxLayout()
        auto_form   = QtGui.QFormLayout()
        self.auto_max_w = QtGui.QDoubleSpinBox()
        self.auto_max_w.setRange(0.1, 1000); self.auto_max_w.setValue(10.0)
        self.auto_max_w.setSuffix(" t"); auto_form.addRow("Max. load:", self.auto_max_w)
        self.auto_min_r = QtGui.QSpinBox()
        self.auto_min_r.setRange(1000, 100000); self.auto_min_r.setValue(5000)
        self.auto_min_r.setSuffix(" mm"); auto_form.addRow("Min. radius:", self.auto_min_r)
        self.auto_min_w = QtGui.QDoubleSpinBox()
        self.auto_min_w.setRange(0.1, 1000); self.auto_min_w.setValue(2.0)
        self.auto_min_w.setSuffix(" t"); auto_form.addRow("Min. load:", self.auto_min_w)
        self.auto_max_r = QtGui.QSpinBox()
        self.auto_max_r.setRange(1000, 100000); self.auto_max_r.setValue(22000)
        self.auto_max_r.setSuffix(" mm"); auto_form.addRow("Max. radius:", self.auto_max_r)
        auto_layout.addLayout(auto_form); auto_layout.addStretch()
        auto_widget.setLayout(auto_layout)
        self.load_stack.addWidget(auto_widget)

        load_layout.addWidget(self.load_stack)
        self.load_mode_combo.currentIndexChanged.connect(self.load_stack.setCurrentIndex)
        load_group.setLayout(load_layout)
        layout.addWidget(load_group)

        # ── Buttons ───────────────────────────────────────────────────────────
        button_layout = QtGui.QHBoxLayout()
        self.create_btn = QtGui.QPushButton("Create crane")
        self.create_btn.setDefault(True)
        self.create_btn.clicked.connect(self.createCrane)
        cancel_btn = QtGui.QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addStretch()
        button_layout.addWidget(self.create_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)

        scroll.setWidget(container)
        outer = QtGui.QVBoxLayout(self)
        outer.addWidget(scroll)
        self.setLayout(outer)
        self.resize(480, 600)

    def findShips(self):
        doc = App.activeDocument()
        if not doc:
            return
        for obj in doc.Objects:
            is_ship = False
            if "ship" in obj.Name.lower():
                is_ship = True
            if hasattr(obj, "Proxy") and obj.Proxy:
                if "ship" in obj.Proxy.__class__.__name__.lower():
                    is_ship = True
            if is_ship:
                self.ship_combo.addItem(obj.Label + " (" + obj.Name + ")", obj)

    def createCrane(self):
        doc = App.activeDocument()
        if not doc:
            doc = App.newDocument()

        name      = self.name_input.text().strip() or "ShipCrane"
        base_name = name
        counter   = 1
        while doc.getObject(name):
            name = base_name + "_" + str(counter)
            counter += 1

        self.crane = doc.addObject("Part::FeaturePython", name)
        ShipCrane(self.crane)

        self.crane.SlewAngle    = self.slew_input.value()
        self.crane.LuffingAngle = self.luffing_input.value()
        self.crane.BoomWeight   = self.boom_weight_input.value()

        is_stages = self.load_mode_combo.currentIndex() == 0
        self.crane.UseLoadStages = is_stages
        if is_stages:
            self.crane.Stage1_Weight    = self.s1_weight.value()
            self.crane.Stage1_MinRadius = self.s1_min_r.value()
            self.crane.Stage1_MaxRadius = self.s1_max_r.value()
            self.crane.Stage2_Weight    = self.s2_weight.value()
            self.crane.Stage2_MinRadius = self.s2_min_r.value()
            self.crane.Stage2_MaxRadius = self.s2_max_r.value()
            self.crane.Stage3_Weight    = self.s3_weight.value()
            self.crane.Stage3_MinRadius = self.s3_min_r.value()
            self.crane.Stage3_MaxRadius = self.s3_max_r.value()
        else:
            self.crane.Auto_MaxWeight = self.auto_max_w.value()
            self.crane.Auto_MinRadius = self.auto_min_r.value()
            self.crane.Auto_MinWeight = self.auto_min_w.value()
            self.crane.Auto_MaxRadius = self.auto_max_r.value()

        if hasattr(self.crane, "ViewObject"):
            self.crane.ViewObject.Proxy      = 0
            self.crane.ViewObject.ShapeColor = (1.0, 0.843, 0.0)
            self.crane.ViewObject.LineColor  = (0.0, 0.0, 0.0)
            self.crane.ViewObject.LineWidth  = 2.0
            self.crane.ViewObject.Visibility = True

        ship_index = self.ship_combo.currentIndex()
        if ship_index > 0:
            self.ship = self.ship_combo.itemData(ship_index)
            couple_crane_to_ship(self.crane, self.ship)

        doc.recompute()

        mode_str = "Load stages" if is_stages else "Automatic"
        App.Console.PrintMessage(
            f"Crane '{self.crane.Name}' created ({mode_str})\n"
            f"  → Move to desired position, then call couple_crane_to_ship().\n")
        self.accept()


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def create_ship_crane_simple(name="ShipCrane"):
    doc = App.activeDocument()
    if doc is None:
        doc = App.newDocument("ShipCrane")
    crane = doc.addObject("Part::FeaturePython", name)
    ShipCrane(crane)
    if hasattr(crane, "ViewObject"):
        crane.ViewObject.Proxy      = 0
        crane.ViewObject.ShapeColor = (1.0, 0.843, 0.0)
        crane.ViewObject.Visibility = True
    doc.recompute()
    App.Console.PrintMessage(f"Crane '{crane.Name}' created\n")
    return crane


def couple_crane_to_ship(crane_obj, ship_obj):
    """
    Couples a crane to a ship.
    CALL THIS after the crane has been moved to its final position!
    """
    try:
        if not crane_obj or not ship_obj:
            return False

        try:
            crane_obj.setExpression("Placement", None)
        except Exception:
            pass

        crane_placement = crane_obj.Placement.copy()
        if hasattr(ship_obj, "Placement"):
            rel_placement = ship_obj.Placement.inverse() * crane_placement
        else:
            rel_placement = crane_placement

        crane_obj.RelativePlacement = rel_placement
        crane_obj.ParentShip        = ship_obj
        crane_obj.IsCoupled         = True

        App.Console.PrintMessage(
            f"  {crane_obj.Name} coupled to {ship_obj.Name}\n"
            f"  RelativePlacement: {rel_placement.Base}\n")

        crane_obj.Document.recompute()
        return True

    except Exception as e:
        App.Console.PrintError(f"Coupling error: {e}\n")
        return False


def decouple_crane(crane_obj):
    """
    Decouples a crane from the ship.
    The current world position is preserved.
    """
    try:
        try:
            crane_obj.setExpression("Placement", None)
        except Exception:
            pass

        world_placement      = crane_obj.Placement.copy()
        crane_obj.IsCoupled  = False
        crane_obj.ParentShip = None
        crane_obj.Placement  = world_placement

        App.Console.PrintMessage(
            f"  {crane_obj.Name} decoupled – "
            f"position frozen: {world_placement.Base}\n")

        crane_obj.Document.recompute()
        return True

    except Exception as e:
        App.Console.PrintError(f"Decoupling error: {e}\n")
        return False
