# -*- coding: utf-8 -*-
"""
TandemLift.py - Tandem Lift Operation + Interactive Swing Simulation
"""

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtGui, QtCore
import math
import copy

try:
    from .TaskLiftOperation import SingleHookLift
except ImportError:
    from TaskLiftOperation import SingleHookLift

try:
    from .CraneSpreadsheetTools import (
        find_loadcondition,
        get_crane_positions,
        transfer_crane_data_and_calculate
    )
except ImportError:
    from CraneSpreadsheetTools import (
        find_loadcondition,
        get_crane_positions,
        transfer_crane_data_and_calculate
    )


# =============================================================================
# LOAD DISTRIBUTION
# =============================================================================

class TandemLiftCalculator:
    """
    Calculates load distribution on two cranes for tandem operation.

    Physics (moment equilibrium):
        F1 + F2 = W
        F1 * d1 = F2 * d2
        → F1 = W * d2 / (d1 + d2)
        → F2 = W * d1 / (d1 + d2)

    d1 = distance COG to lift point 1
    d2 = distance COG to lift point 2
    """

    def __init__(self):
        self.total_weight   = 0.0
        self.load_1         = 0.0
        self.load_2         = 0.0
        self.distance_1     = 0.0
        self.distance_2     = 0.0
        self.total_distance = 0.0
        self.cog_outside    = False
        self.warnings       = []

    def calculate_load_distribution(self, total_weight_t, distance_1_m, distance_2_m):
        self.total_weight   = total_weight_t
        self.distance_1     = abs(distance_1_m)
        self.distance_2     = abs(distance_2_m)
        self.total_distance = self.distance_1 + self.distance_2
        self.warnings       = []
        self.cog_outside    = False

        if self.total_distance < 0.001:
            self.warnings.append("Distance between lift points too small!")
            return 0, 0, self.warnings

        self.load_1 = total_weight_t * self.distance_2 / self.total_distance
        self.load_2 = total_weight_t * self.distance_1 / self.total_distance

        if self.load_1 > total_weight_t * 0.90:
            self.warnings.append(
                f"Crane 1 carries {self.load_1/total_weight_t*100:.0f}% – very unequal distribution!"
            )
        if self.load_2 > total_weight_t * 0.90:
            self.warnings.append(
                f"Crane 2 carries {self.load_2/total_weight_t*100:.0f}% – very unequal distribution!"
            )

        return self.load_1, self.load_2, self.warnings

    def calculate_from_lift_points(self, total_weight_t, cog_to_l1_m, l1_to_l2_m):
        self.warnings    = []
        self.cog_outside = False

        if cog_to_l1_m < 0:
            d1 = 0.0
            d2 = l1_to_l2_m + abs(cog_to_l1_m)
            self.cog_outside = True
            self.warnings.append(
                "COG is AHEAD of lift point 1 – Crane 1 must be pulled outward! "
                "Securing required."
            )
        elif cog_to_l1_m > l1_to_l2_m:
            d1 = l1_to_l2_m + (cog_to_l1_m - l1_to_l2_m)
            d2 = 0.0
            self.cog_outside = True
            self.warnings.append(
                "COG is BEHIND lift point 2 – Crane 2 must be pulled outward! "
                "Securing required."
            )
        else:
            d1 = cog_to_l1_m
            d2 = l1_to_l2_m - cog_to_l1_m

        return self.calculate_load_distribution(total_weight_t, d1, d2)

    def get_summary(self):
        if self.total_distance < 0.001:
            return "Calculation not possible."

        pct1 = self.load_1 / self.total_weight * 100 if self.total_weight > 0 else 0
        pct2 = self.load_2 / self.total_weight * 100 if self.total_weight > 0 else 0

        lines = [
            f"Total weight:   {self.total_weight:.1f} t",
            f"Distance L1-L2: {self.total_distance:.2f} m",
            f"  COG to L1:    {self.distance_1:.2f} m  ({self.distance_1/self.total_distance*100:.0f}%)",
            f"  COG to L2:    {self.distance_2:.2f} m  ({self.distance_2/self.total_distance*100:.0f}%)",
            "",
            f"Crane 1 (L1):  {self.load_1:.2f} t  ({pct1:.1f}%)",
            f"Crane 2 (L2):  {self.load_2:.2f} t  ({pct2:.1f}%)",
        ]
        if self.warnings:
            lines += ["", "Warnings:"] + [f"  ⚠  {w}" for w in self.warnings]
        return "\n".join(lines)


# =============================================================================
# GEOMETRY SOLVER
# =============================================================================

class TandemGeometrySolver:
    """
    Calculates slew angles for both cranes so that:
      1. the boom tip distance matches the lift point distance,
      2. both booms point as far as possible toward land.
    """

    def __init__(self, crane_1_pos, crane_2_pos):
        self.p1 = crane_1_pos
        self.p2 = crane_2_pos

    def tip_position(self, crane_pos, radius_mm, slew_deg):
        a = math.radians(slew_deg)
        x = crane_pos[0] - radius_mm * math.sin(a)
        y = crane_pos[1] + radius_mm * math.cos(a)
        return (x, y)

    def solve(self, radius_1_mm, radius_2_mm, required_distance_mm, land_direction_deg=180.0):
        r1 = radius_1_mm
        r2 = radius_2_mm
        D  = required_distance_mm

        land_rad = math.radians(land_direction_deg)
        land_vec = (-math.sin(land_rad), math.cos(land_rad))

        best_score = -1e18
        best = None

        STEP_DEG = 0.5
        steps = int(360 / STEP_DEG)

        for i in range(steps):
            a1_deg = i * STEP_DEG
            T1 = self.tip_position(self.p1, r1, a1_deg)

            dx = T1[0] - self.p2[0]
            dy = T1[1] - self.p2[1]

            A = 2 * r2 * dx
            B = -2 * r2 * dy
            C = D*D - dx*dx - dy*dy - r2*r2

            R = math.sqrt(A*A + B*B)
            if R < 1e-6:
                continue

            ratio = C / R
            if abs(ratio) > 1.0:
                continue

            phi = math.atan2(B, A)
            base_angle = math.asin(ratio)

            for a2_rad in (base_angle - phi, math.pi - base_angle - phi):
                a2_deg = math.degrees(a2_rad) % 360

                T2 = self.tip_position(self.p2, r2, a2_deg)

                dist = math.sqrt((T1[0]-T2[0])**2 + (T1[1]-T2[1])**2)
                if abs(dist - D) > D * 0.001:
                    continue

                dir1 = (T1[0]-self.p1[0], T1[1]-self.p1[1])
                dir2 = (T2[0]-self.p2[0], T2[1]-self.p2[1])
                len1 = math.sqrt(dir1[0]**2+dir1[1]**2) or 1
                len2 = math.sqrt(dir2[0]**2+dir2[1]**2) or 1
                score = (dir1[0]*land_vec[0]+dir1[1]*land_vec[1])/len1 + \
                        (dir2[0]*land_vec[0]+dir2[1]*land_vec[1])/len2

                if score > best_score:
                    best_score = score
                    best = (a1_deg, a2_deg, dist, score)

        return best

    def geometry_report(self, slew_1, slew_2, r1, r2, required_dist):
        T1 = self.tip_position(self.p1, r1, slew_1)
        T2 = self.tip_position(self.p2, r2, slew_2)
        dist = math.sqrt((T1[0]-T2[0])**2 + (T1[1]-T2[1])**2)

        lines = [
            f"Crane 1: Position ({self.p1[0]/1000:.1f}m, {self.p1[1]/1000:.1f}m)  "
            f"Slew {slew_1:.1f}°  Radius {r1/1000:.2f}m",
            f"  Boom tip: ({T1[0]/1000:.2f}m, {T1[1]/1000:.2f}m)",
            f"Crane 2: Position ({self.p2[0]/1000:.1f}m, {self.p2[1]/1000:.1f}m)  "
            f"Slew {slew_2:.1f}°  Radius {r2/1000:.2f}m",
            f"  Boom tip: ({T2[0]/1000:.2f}m, {T2[1]/1000:.2f}m)",
            f"Boom tip distance: {dist/1000:.3f}m  (required: {required_dist/1000:.3f}m)",
        ]
        return "\n".join(lines)


# =============================================================================
# OPERATION
# =============================================================================

class TandemLiftOperation:
    """Executes a complete tandem lift operation with two cranes."""

    def __init__(self, crane_1_obj, crane_2_obj):
        self.crane_1    = crane_1_obj
        self.crane_2    = crane_2_obj
        self.calculator = TandemLiftCalculator()
        self.lift_1     = SingleHookLift(crane_1_obj)
        self.lift_2     = SingleHookLift(crane_2_obj)

        self.results = {
            'success':  False,
            'load_1':   0.0,
            'load_2':   0.0,
            'radius_1': 0.0,
            'radius_2': 0.0,
            'slew_1':   None,
            'slew_2':   None,
            'messages': []
        }

    def _get_crane_xy(self, crane_obj):
        pos = crane_obj.Placement.Base
        return (float(pos.x), float(pos.y))

    def execute(self, total_weight_t, cog_to_l1_m, l1_to_l2_m,
                land_direction_deg=180.0, slew_1=None, slew_2=None):
        self.results['messages'] = []
        msgs = self.results['messages']

        load_1, load_2, warnings = self.calculator.calculate_from_lift_points(
            total_weight_t, cog_to_l1_m, l1_to_l2_m
        )
        self.results['load_1'] = load_1
        self.results['load_2'] = load_2
        for w in warnings:
            msgs.append(f"WARNING: {w}")

        r1_mm, ok1, wmsg1 = self.lift_1.calculate_optimal_radius(load_1)
        r2_mm, ok2, wmsg2 = self.lift_2.calculate_optimal_radius(load_2)

        if r1_mm == 0:
            msgs.append(f"Crane 1 cannot carry {load_1:.1f}t: {wmsg1}")
            return self.results
        if r2_mm == 0:
            msgs.append(f"Crane 2 cannot carry {load_2:.1f}t: {wmsg2}")
            return self.results

        self.results['radius_1'] = r1_mm
        self.results['radius_2'] = r2_mm
        msgs.append(f"Crane 1: {load_1:.2f}t → radius {r1_mm/1000:.2f}m")
        msgs.append(f"Crane 2: {load_2:.2f}t → radius {r2_mm/1000:.2f}m")

        if slew_1 is not None and slew_2 is not None:
            computed_slew_1 = slew_1
            computed_slew_2 = slew_2
            msgs.append("Slew angles: manually specified")
        else:
            p1 = self._get_crane_xy(self.crane_1)
            p2 = self._get_crane_xy(self.crane_2)
            D_mm = l1_to_l2_m * 1000.0

            solver = TandemGeometrySolver(p1, p2)
            solution = solver.solve(r1_mm, r2_mm, D_mm, land_direction_deg)

            if solution is None:
                msgs.append(
                    "Geometry solver: no solution found!\n"
                    f"  r1={r1_mm/1000:.1f}m  r2={r2_mm/1000:.1f}m  D={l1_to_l2_m:.1f}m"
                )
                return self.results

            computed_slew_1, computed_slew_2, actual_dist, score = solution
            self.results['slew_1'] = computed_slew_1
            self.results['slew_2'] = computed_slew_2
            report = solver.geometry_report(computed_slew_1, computed_slew_2, r1_mm, r2_mm, D_mm)
            msgs.append(report)

        success_1, msg_1, _ = self.lift_1.execute_lift(load_1, computed_slew_1)
        success_2, msg_2, _ = self.lift_2.execute_lift(load_2, computed_slew_2)

        if not success_1:
            msgs.append(f"Crane 1 positioning failed: {msg_1}")
            return self.results
        if not success_2:
            msgs.append(f"Crane 2 positioning failed: {msg_2}")
            return self.results

        self.results['success'] = True
        msgs.append("✓ Tandem lift successfully configured")
        return self.results

    def transfer_to_loadcondition(self, doc=None, auto_calculate=True,
                                   show_confirmation=True):
        if doc is None:
            doc = App.activeDocument()
            if doc is None:
                return False, "No active document!", None

        crane_data = {}

        if self.results['radius_1'] > 0 and self.crane_1:
            boom_1, hook_1 = get_crane_positions(self.crane_1)
            label_1 = self.crane_1.Label
            boom_kg_1 = float(getattr(self.crane_1, 'BoomWeight', 0.0)) * 1000.0

            crane_data[label_1] = {
                'boom_kg':  boom_kg_1,
                'hook_kg':  self.results['load_1'] * 1000.0,
                'boom_pos': boom_1,
                'hook_pos': hook_1,
            }
            App.Console.PrintMessage(
                f"  {label_1}: Boom={boom_kg_1:.0f}kg "
                f"Hook={self.results['load_1']*1000:.0f}kg\n")

        if self.results['radius_2'] > 0 and self.crane_2:
            boom_2, hook_2 = get_crane_positions(self.crane_2)
            label_2 = self.crane_2.Label
            boom_kg_2 = float(getattr(self.crane_2, 'BoomWeight', 0.0)) * 1000.0

            crane_data[label_2] = {
                'boom_kg':  boom_kg_2,
                'hook_kg':  self.results['load_2'] * 1000.0,
                'boom_pos': boom_2,
                'hook_pos': hook_2,
            }
            App.Console.PrintMessage(
                f"  {label_2}: Boom={boom_kg_2:.0f}kg "
                f"Hook={self.results['load_2']*1000:.0f}kg\n")

        if not crane_data:
            return False, "No valid crane data available (radii = 0)!", None

        success, msg, hydro = transfer_crane_data_and_calculate(
            crane_data,
            doc=doc,
            auto_calculate=auto_calculate,
            show_confirmation=show_confirmation
        )

        return success, msg, hydro


# =============================================================================
# 3D VISUALISATION
# =============================================================================

class LoadVisual:
    """Creates and manages the 3D visualisation of the load."""

    def __init__(self, doc, load_geom, name="SwingLoad"):
        self.doc = doc
        self.load_geom = load_geom
        self.name = name
        self.shape = None
        self.corners_obj = None
        self.cog_obj = None
        self.sling_lines = []

    def create(self, lp1_xy, lp2_xy, bottom_z):
        if self.name in [obj.Name for obj in self.doc.Objects]:
            self.doc.removeObject(self.name)

        (cx, cy, cz), u, v = self.load_geom.get_world_transform(lp1_xy, lp2_xy, bottom_z)

        box = self.doc.addObject("Part::Box", self.name)
        box.Length = self.load_geom.length_mm
        box.Width = self.load_geom.width_mm
        box.Height = self.load_geom.height_mm

        v = (-u[1], u[0])
        base_x = cx - self.load_geom.length_mm/2 * u[0] - self.load_geom.width_mm/2 * v[0]
        base_y = cy - self.load_geom.length_mm/2 * u[1] - self.load_geom.width_mm/2 * v[1]
        angle = math.degrees(math.atan2(u[1], u[0]))
        box.Placement.Base = App.Vector(base_x, base_y, bottom_z)
        box.Placement.Rotation = App.Rotation(App.Vector(0, 0, 1), angle)
        box.ViewObject.ShapeColor = (0.8, 0.6, 0.4)
        box.ViewObject.Transparency = 30
        self.shape = box

        cog_xy = self.load_geom.get_cog_xy(lp1_xy, lp2_xy)
        self.cog_obj = self.doc.addObject("Part::Sphere", self.name + "_COG")
        self.cog_obj.Radius = 500
        self.cog_obj.Placement.Base = App.Vector(cog_xy[0], cog_xy[1], cz)
        self.cog_obj.ViewObject.ShapeColor = (1.0, 0.0, 0.0)

        self._create_lift_point(lp1_xy, bottom_z + self.load_geom.height_mm, "LP1", (0, 1, 0))
        self._create_lift_point(lp2_xy, bottom_z + self.load_geom.height_mm, "LP2", (0, 0, 1))
        self._create_sling_line(lp1_xy, bottom_z + self.load_geom.height_mm, "Sling1")
        self._create_sling_line(lp2_xy, bottom_z + self.load_geom.height_mm, "Sling2")

        self.doc.recompute()
        return box

    def _create_lift_point(self, xy, z, suffix, color):
        obj = self.doc.addObject("Part::Sphere", f"{self.name}_{suffix}")
        obj.Radius = 300
        obj.Placement.Base = App.Vector(xy[0], xy[1], z)
        obj.ViewObject.ShapeColor = color
        return obj

    def _create_sling_line(self, lp_xy, lp_z, suffix):
        line = self.doc.addObject("Part::Line", f"{self.name}_{suffix}")
        line.X1, line.Y1, line.Z1 = lp_xy[0], lp_xy[1], lp_z
        line.X2, line.Y2, line.Z2 = lp_xy[0], lp_xy[1], lp_z + 1000
        line.ViewObject.LineColor = (0.5, 0.5, 0.5)
        line.ViewObject.LineWidth = 3
        self.sling_lines.append(line)
        return line

    def update(self, lp1_xy, lp2_xy, bottom_z, tip1_xy, tip2_xy, tip_z):
        if not self.shape:
            return

        (cx, cy, cz), u, v = self.load_geom.get_world_transform(lp1_xy, lp2_xy, bottom_z)

        v = (-u[1], u[0])
        base_x = cx - self.load_geom.length_mm/2 * u[0] - self.load_geom.width_mm/2 * v[0]
        base_y = cy - self.load_geom.length_mm/2 * u[1] - self.load_geom.width_mm/2 * v[1]
        angle = math.degrees(math.atan2(u[1], u[0]))
        self.shape.Placement.Base = App.Vector(base_x, base_y, bottom_z)
        self.shape.Placement.Rotation = App.Rotation(App.Vector(0, 0, 1), angle)

        cog_xy = self.load_geom.get_cog_xy(lp1_xy, lp2_xy)
        self.cog_obj.Placement.Base = App.Vector(cog_xy[0], cog_xy[1], cz)

        lp_z = bottom_z + self.load_geom.height_mm - self.load_geom.lp_height_from_top_mm
        for suffix, xy in [("LP1", lp1_xy), ("LP2", lp2_xy)]:
            obj = self.doc.getObject(f"{self.name}_{suffix}")
            if obj:
                obj.Placement.Base = App.Vector(xy[0], xy[1], lp_z)

        for i, (lp_xy, tip_xy) in enumerate([(lp1_xy, tip1_xy), (lp2_xy, tip2_xy)]):
            if i < len(self.sling_lines):
                line = self.sling_lines[i]
                line.X1, line.Y1, line.Z1 = lp_xy[0], lp_xy[1], lp_z
                line.X2, line.Y2, line.Z2 = tip_xy[0], tip_xy[1], tip_z

        self.doc.recompute()

    def set_collision_state(self, has_collision):
        if not self.shape:
            return
        if has_collision:
            self.shape.ViewObject.ShapeColor = (1.0, 0.2, 0.2)
            self.shape.ViewObject.Transparency = 0
        else:
            self.shape.ViewObject.ShapeColor = (0.8, 0.6, 0.4)
            self.shape.ViewObject.Transparency = 30

    def remove(self):
        names = [self.name, self.name + "_COG", self.name + "_LP1",
                 self.name + "_LP2", self.name + "_Sling1", self.name + "_Sling2"]
        for name in names:
            obj = self.doc.getObject(name)
            if obj:
                self.doc.removeObject(obj.Name)
        self.doc.recompute()


class SwingCirclesVisual:
    """Draws the slew circles of the cranes at a given height."""

    def __init__(self, doc, crane_obj, name_suffix):
        self.doc = doc
        self.crane = crane_obj
        self.name = f"SwingCircle_{crane_obj.Name}_{name_suffix}"
        self.circle = None

    def create(self, height_mm, radius_mm=None):
        if radius_mm is None:
            radius_mm = float(self.crane.BoomLength)

        cx = float(self.crane.Placement.Base.x)
        cy = float(self.crane.Placement.Base.y)

        circle = self.doc.addObject("Part::Polygon", self.name)
        points = []
        for i in range(65):
            angle = 2 * math.pi * i / 64
            x = cx - radius_mm * math.sin(angle)
            y = cy + radius_mm * math.cos(angle)
            points.append(App.Vector(x, y, height_mm))

        circle.Nodes = points
        circle.ViewObject.LineColor = (0.0, 0.8, 0.0)
        circle.ViewObject.LineWidth = 2
        circle.ViewObject.PointSize = 0
        self.circle = circle
        self.doc.recompute()
        return circle

    def update_height(self, height_mm):
        if not self.circle:
            return
        nodes = [App.Vector(p.x, p.y, height_mm) for p in self.circle.Nodes]
        self.circle.Nodes = nodes
        self.doc.recompute()

    def remove(self):
        obj = self.doc.getObject(self.name)
        if obj:
            self.doc.removeObject(obj.Name)


# =============================================================================
# INTERACTIVE SIMULATION
# =============================================================================

class SwingStep:
    """State of a single simulation step."""
    STATUS_OK   = "OK"
    STATUS_WARN = "WARN"
    STATUS_FAIL = "FAIL"

    def __init__(self, idx, t):
        self.idx = idx
        self.t = t
        self.status = self.STATUS_OK
        self.messages = []
        self.slew_1 = 0.0
        self.slew_2 = 0.0
        self.radius_1_mm = 0.0
        self.radius_2_mm = 0.0
        self.tip_1_xy = (0, 0)
        self.tip_2_xy = (0, 0)
        self.lp_1_xy = (0, 0)
        self.lp_2_xy = (0, 0)
        self.load_bottom_z = 0.0
        self.tip_z = 0.0
        self.load_corners = []
        self.load_footprint = []
        self.load_cog_xy = (0, 0)
        self.clearance_ship_hull = None
        self.clearance_deck = None

    def set_ok(self, msg):
        self.status = self.STATUS_OK
        self.messages.append(msg)

    def set_warn(self, msg):
        if self.status == self.STATUS_OK:
            self.status = self.STATUS_WARN
        self.messages.append(msg)

    def set_fail(self, msg):
        self.status = self.STATUS_FAIL
        self.messages.append(msg)


class InteractiveSwingSimulator:
    """Step-by-step simulator with visual feedback."""

    def __init__(self, crane_1_obj, crane_2_obj, load_geom, ship_geom):
        self.crane_1 = crane_1_obj
        self.crane_2 = crane_2_obj
        self.load_geom = load_geom
        self.ship_geom = ship_geom

        self.doc = App.activeDocument()
        self.load_vis = None
        self.circle_1 = None
        self.circle_2 = None

        self.steps = []
        self.current_step_idx = 0
        self.r1_mm = 0
        self.r2_mm = 0

        self.list_angle_deg = 0.0
        self.lp1_offset_mm = 0
        self.lp2_offset_mm = 0

    def setup_visualization(self):
        self.load_vis = LoadVisual(self.doc, self.load_geom)
        self.circle_1 = SwingCirclesVisual(self.doc, self.crane_1, "C1")
        self.circle_2 = SwingCirclesVisual(self.doc, self.crane_2, "C2")
        self._visuals_created = False

    def compute_radii(self, total_weight_t, cog_to_lp1_m):
        calc = TandemLiftCalculator()
        load_1, load_2, warnings = calc.calculate_from_lift_points(
            total_weight_t, cog_to_lp1_m,
            self.load_geom.lp_distance_mm / 1000.0
        )

        self.load_1_t = load_1
        self.load_2_t = load_2
        self.dist_warnings = warnings

        lift1 = SingleHookLift(self.crane_1)
        lift2 = SingleHookLift(self.crane_2)

        self.r1_mm, ok1, self.r1_warn = lift1.calculate_optimal_radius(load_1)
        self.r2_mm, ok2, self.r2_warn = lift2.calculate_optimal_radius(load_2)

        self.r1_min_mm = self._get_min_radius(self.crane_1)
        self.r2_min_mm = self._get_min_radius(self.crane_2)

        self.r1_mm = max(self.r1_mm, self.r1_min_mm)
        self.r2_mm = max(self.r2_mm, self.r2_min_mm)

        return self.r1_mm > 0 and self.r2_mm > 0

    def _get_min_radius(self, crane_obj):
        try:
            if crane_obj.UseLoadStages:
                return min(
                    float(crane_obj.Stage1_MinRadius),
                    float(crane_obj.Stage2_MinRadius),
                    float(crane_obj.Stage3_MinRadius),
                )
            else:
                return float(crane_obj.Auto_MinRadius)
        except Exception:
            return float(crane_obj.BoomLength) * 0.20

    def _crane_axes(self):
        p1 = (float(self.crane_1.Placement.Base.x),
              float(self.crane_1.Placement.Base.y))
        p2 = (float(self.crane_2.Placement.Base.x),
              float(self.crane_2.Placement.Base.y))
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        d = math.sqrt(dx*dx + dy*dy) or 1.0
        u_long = (dx/d, dy/d)
        crane_mid = ((p1[0]+p2[0])/2, (p1[1]+p2[1])/2)
        to_x = crane_mid[0] - self.ship_geom.cx
        to_y = crane_mid[1] - self.ship_geom.cy
        ll = math.sqrt(to_x**2 + to_y**2) or 1.0
        v_land = (to_x/ll, to_y/ll)
        return p1, p2, u_long, v_land

    def _slew_for_lp(self, crane_pos, lp_xy):
        dx = crane_pos[0] - lp_xy[0]
        dy = lp_xy[1] - crane_pos[1]
        slew = math.degrees(math.atan2(dx, dy)) % 360
        dist = math.sqrt((crane_pos[0]-lp_xy[0])**2 +
                         (crane_pos[1]-lp_xy[1])**2)
        return slew, dist

    def _calculate_heights(self):
        deck_z = self.ship_geom.deck_z
        load_bottom_z = deck_z + 1000.0
        lp_offset_from_top = self.load_geom.lp_height_from_top_mm
        lp_z = load_bottom_z + self.load_geom.height_mm - lp_offset_from_top

        def boom_tip_z(crane_obj):
            cz = float(crane_obj.Placement.Base.z)
            bh = float(crane_obj.BaseHeight)
            ph = float(crane_obj.BoomPivotHeight)
            bl = float(crane_obj.BoomLength)
            luff = float(crane_obj.LuffingAngle)
            return cz + bh + ph + bl * math.sin(math.radians(luff))

        tip_z = max(boom_tip_z(self.crane_1), boom_tip_z(self.crane_2))

        App.Console.PrintMessage(
            f"  Deck: {deck_z/1000:.2f}m  "
            f"Load bottom: {load_bottom_z/1000:.2f}m  "
            f"LP height: {lp_z/1000:.2f}m\n"
        )

        return lp_z, load_bottom_z, tip_z

    def find_valid_for_angle(self, theta_deg, n_angles=720):
        p1, p2, u_long, v_land = self._crane_axes()
        D_mm = self.load_geom.lp_distance_mm

        theta_rad = math.radians(theta_deg)
        cos_t = math.cos(theta_rad)
        sin_t = math.sin(theta_rad)
        ux, uy = u_long
        dir_x = cos_t * ux - sin_t * uy
        dir_y = sin_t * ux + cos_t * uy

        candidates = []
        for i in range(n_angles):
            phi = 2 * math.pi * i / 64
            for frac in (0.0, 0.33, 0.67, 1.0):
                r1 = self.r1_min_mm + frac * (self.r1_mm - self.r1_min_mm)
                lp1 = (p1[0] + r1 * math.cos(phi),
                       p1[1] + r1 * math.sin(phi))
                lp2 = (lp1[0] + D_mm * dir_x,
                       lp1[1] + D_mm * dir_y)
                r2 = math.sqrt((p2[0]-lp2[0])**2 + (p2[1]-lp2[1])**2)
                if self.r2_min_mm <= r2 <= self.r2_mm * 1.01:
                    mid_x = (lp1[0] + lp2[0]) / 2
                    mid_y = (lp1[1] + lp2[1]) / 2
                    land_score = mid_x*v_land[0] + mid_y*v_land[1]
                    candidates.append((lp1, lp2, r1, r2, land_score))

        return candidates

    def generate_steps(self, sea_dir_deg, land_dir_deg, n_steps):
        self.steps = []
        p1, p2, u_long, v_land = self._crane_axes()

        lp_z, load_bottom_z, tip_z = self._calculate_heights()

        half = n_steps // 2
        rest = n_steps - half

        def steps_for_rotation(sign):
            phase1 = []
            phase2 = []

            for k in range(half):
                t = k / max(half - 1, 1)
                theta = sign * t * 90.0
                cands = self.find_valid_for_angle(theta)
                if not cands:
                    return None
                best = max(cands, key=lambda c: c[4])
                phase1.append((theta,) + best)

            for k in range(rest):
                t = k / max(rest - 1, 1)
                theta = sign * (1.0 - t) * 90.0
                cands = self.find_valid_for_angle(theta)
                if not cands:
                    return None
                best = min(cands, key=lambda c: c[4])
                phase2.append((theta,) + best)

            return phase1 + phase2

        seq = steps_for_rotation(+1)
        self.swing_direction = +1
        self.swing_mode = 'LP1-first'
        if seq is None:
            seq = steps_for_rotation(-1)
            self.swing_direction = -1
            self.swing_mode = 'LP2-first'
        if seq is None:
            self.swing_mode = 'no_solution'
            return self.steps

        for i, entry in enumerate(seq):
            theta, lp1, lp2, r1, r2, land_score = entry
            step = SwingStep(i, i / max(len(seq)-1, 1))

            step.lp_1_xy = lp1
            step.lp_2_xy = lp2
            step.load_bottom_z = load_bottom_z
            step.tip_z = tip_z
            step.radius_1_mm = r1
            step.radius_2_mm = r2
            step.tip_1_xy = lp1
            step.tip_2_xy = lp2

            slew_1, _ = self._slew_for_lp(p1, lp1)
            slew_2, _ = self._slew_for_lp(p2, lp2)
            step.slew_1 = slew_1
            step.slew_2 = slew_2

            step.load_corners  = self.load_geom.get_corners_3d(lp1, lp2, load_bottom_z)
            step.load_footprint = self.load_geom.get_footprint_2d(lp1, lp2, load_bottom_z)
            step.load_cog_xy   = self.load_geom.get_cog_xy(lp1, lp2)

            phase_name = "Phase1-SwingOut" if i < half else "Phase2-SwingIn"
            step.messages.append(f"{phase_name}  θ={theta:.1f}°")

            hull_cl = self.ship_geom.clearance_corners_2d(step.load_footprint)
            deck_cl = self.ship_geom.z_clearance_below(load_bottom_z)
            step.clearance_ship_hull = hull_cl
            step.clearance_deck      = deck_cl

            if hull_cl < 0:
                step.set_fail(f"Hull collision ({-hull_cl/1000:.2f}m)")
            elif deck_cl < 0:
                step.set_fail(f"Deck collision ({-deck_cl/1000:.2f}m)")
            elif hull_cl < 1000:
                step.set_warn(f"Hull clearance critical: {hull_cl/1000:.2f}m")
            elif hull_cl < 3000:
                step.set_warn(f"Hull clearance low: {hull_cl/1000:.2f}m")
            else:
                step.set_ok(f"Hull {hull_cl/1000:.2f}m  Deck {deck_cl/1000:.2f}m")

            self.steps.append(step)

        return self.steps

    def show_step(self, step_idx):
        if step_idx < 0 or step_idx >= len(self.steps):
            return False

        step = self.steps[step_idx]
        height = step.load_bottom_z + self.load_geom.height_mm / 2

        if not getattr(self, '_visuals_created', False):
            if self.load_vis:
                self.load_vis.create(step.lp_1_xy, step.lp_2_xy, step.load_bottom_z)
            if self.circle_1:
                self.circle_1.create(height, self.r1_mm)
            if self.circle_2:
                self.circle_2.create(height, self.r2_mm)
            self._visuals_created = True

        if self.load_vis:
            self.load_vis.update(
                step.lp_1_xy, step.lp_2_xy, step.load_bottom_z,
                step.tip_1_xy, step.tip_2_xy, step.tip_z
            )
            has_collision = step.status in [SwingStep.STATUS_FAIL, SwingStep.STATUS_WARN]
            self.load_vis.set_collision_state(has_collision)

        if self.circle_1 and self.circle_2:
            self.circle_1.update_height(height)
            self.circle_2.update_height(height)

        self.crane_1.SlewAngle = step.slew_1
        self.crane_2.SlewAngle = step.slew_2

        def safe_luffing(crane_obj, radius_mm, min_r_mm):
            boom_len = float(crane_obj.BoomLength)
            r = max(radius_mm, min_r_mm)
            r = min(r, boom_len * 0.999)
            cos_luff = r / boom_len
            luff_deg = math.degrees(math.acos(max(-1.0, min(1.0, cos_luff))))
            crane_obj.LuffingAngle = max(0.0, min(85.0, luff_deg))

        safe_luffing(self.crane_1, step.radius_1_mm or self.r1_mm,
                     getattr(self, 'r1_min_mm', 0))
        safe_luffing(self.crane_2, step.radius_2_mm or self.r2_mm,
                     getattr(self, 'r2_min_mm', 0))

        self.doc.recompute()
        return True

    def apply_list_angle(self, angle_deg):
        self.list_angle_deg = angle_deg

    def cleanup(self):
        if self.load_vis:
            self.load_vis.remove()
        if self.circle_1:
            self.circle_1.remove()
        if self.circle_2:
            self.circle_2.remove()


# =============================================================================
# DIALOG
# =============================================================================

class InteractiveSwingDialog(QtGui.QDialog):

    def __init__(self, parent=None):
        super(InteractiveSwingDialog, self).__init__(parent)
        self.setWindowTitle("Swing Simulation")
        self.setFixedWidth(380)
        self.setWindowFlags(
            QtCore.Qt.Tool |
            QtCore.Qt.WindowStaysOnTopHint |
            QtCore.Qt.WindowCloseButtonHint
        )
        screen = QtGui.QApplication.desktop().availableGeometry()
        self.move(screen.left() + 10, screen.top() + 60)

        self.simulator = None
        self.current_step_idx = 0
        self.setupUI()
        self.findCranes()

    def setupUI(self):
        scroll = QtGui.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)

        container = QtGui.QWidget()
        layout = QtGui.QVBoxLayout(container)
        layout.setSpacing(6)
        layout.setContentsMargins(6, 6, 6, 6)

        # ---- Setup ----
        setup_group = QtGui.QGroupBox("Setup")
        setup_layout = QtGui.QFormLayout()

        self.crane_1_combo = QtGui.QComboBox()
        self.crane_2_combo = QtGui.QComboBox()
        setup_layout.addRow("Crane 1 (Aft):", self.crane_1_combo)
        setup_layout.addRow("Crane 2 (Fwd):", self.crane_2_combo)

        def dspin(lo, hi, val, sfx, dec=0):
            w = QtGui.QDoubleSpinBox()
            w.setRange(lo, hi)
            w.setValue(val)
            w.setSuffix(sfx)
            w.setDecimals(dec)
            return w

        self.e_length  = dspin(1000, 200000, 40000, " mm")
        self.e_width   = dspin(100,   20000,  3000, " mm")
        self.e_height  = dspin(100,   20000,  3000, " mm")
        self.e_weight  = dspin(0.1,   5000,    200, " t", 1)
        self.e_lp_dist = dspin(100,  100000, 20000, " mm")
        self.e_cog_lp1 = dspin(0,    99000,  10000, " mm")
        self.e_lp1_end = dspin(0,    50000,   2000, " mm")

        setup_layout.addRow("Load length:",      self.e_length)
        setup_layout.addRow("Load width:",       self.e_width)
        setup_layout.addRow("Load height:",      self.e_height)
        setup_layout.addRow("Weight:",           self.e_weight)
        setup_layout.addRow("Distance LP1→LP2:", self.e_lp_dist)
        setup_layout.addRow("COG to LP1:",       self.e_cog_lp1)
        setup_layout.addRow("LP1 from end:",     self.e_lp1_end)

        self.e_deck_z = dspin(-50000, 50000, 0, " mm")
        self.e_deck_z.setToolTip(
            "Z coordinate of deck (0 = datum, positive = above datum)")
        setup_layout.addRow("Deck height (Z):", self.e_deck_z)

        self.lbl_dist_preview = QtGui.QLabel("")
        self.lbl_dist_preview.setStyleSheet(
            "color: #333; font-size: 10px; padding: 2px;")
        setup_layout.addRow("", self.lbl_dist_preview)
        self.e_lp_dist.valueChanged.connect(self._update_dist_preview)
        self.e_cog_lp1.valueChanged.connect(self._update_dist_preview)
        self.e_weight.valueChanged.connect(self._update_dist_preview)

        self.e_sea_dir  = dspin(0, 359.9,   0, " °", 1)
        self.e_land_dir = dspin(0, 359.9, 180, " °", 1)
        self.e_steps    = QtGui.QSpinBox()
        self.e_steps.setRange(5, 50)
        self.e_steps.setValue(15)

        setup_layout.addRow("Sea direction:",    self.e_sea_dir)
        setup_layout.addRow("Land direction:",   self.e_land_dir)
        setup_layout.addRow("Number of steps:",  self.e_steps)

        self.init_btn = QtGui.QPushButton("Initialize simulation")
        self.init_btn.setStyleSheet(
            "background-color: #4CAF50; color: white; font-weight: bold;")
        self.init_btn.clicked.connect(self.initializeSimulation)
        setup_layout.addRow("", self.init_btn)

        setup_group.setLayout(setup_layout)
        layout.addWidget(setup_group)

        # ---- Step control ----
        control_group = QtGui.QGroupBox("Step-by-Step Control")

        self.btn_prev = QtGui.QPushButton("◀ Previous")
        self.btn_prev.setEnabled(False)
        self.btn_prev.clicked.connect(self.prevStep)

        self.lbl_step = QtGui.QLabel("Step: - / -")
        self.lbl_step.setAlignment(QtCore.Qt.AlignCenter)
        self.lbl_step.setStyleSheet("font-size: 14px; font-weight: bold;")

        self.btn_next = QtGui.QPushButton("Next ▶")
        self.btn_next.setEnabled(False)
        self.btn_next.setStyleSheet("background-color: #2196F3; color: white;")
        self.btn_next.clicked.connect(self.nextStep)

        ctrl_row = QtGui.QHBoxLayout()
        ctrl_row.addWidget(self.btn_prev)
        ctrl_row.addWidget(self.lbl_step, 1)
        ctrl_row.addWidget(self.btn_next)

        self.lbl_status = QtGui.QLabel("Status: Not initialised")
        self.lbl_status.setAlignment(QtCore.Qt.AlignCenter)
        self.lbl_status.setStyleSheet("padding: 5px; border-radius: 3px;")

        ctrl_vbox = QtGui.QVBoxLayout()
        ctrl_vbox.addLayout(ctrl_row)
        ctrl_vbox.addWidget(self.lbl_status)
        control_group.setLayout(ctrl_vbox)
        layout.addWidget(control_group)

        # ---- What-if ----
        whatif_group = QtGui.QGroupBox("What-If Adjustments")
        whatif_layout = QtGui.QFormLayout()

        self.e_list_angle = dspin(-5, 5, 0, " °", 1)
        self.e_list_angle.setToolTip("List angle: positive = port side higher")

        self.btn_apply_list = QtGui.QPushButton("Apply list")
        self.btn_apply_list.setEnabled(False)
        self.btn_apply_list.clicked.connect(self.applyListAngle)

        list_row = QtGui.QHBoxLayout()
        list_row.addWidget(self.e_list_angle)
        list_row.addWidget(self.btn_apply_list)
        whatif_layout.addRow("List angle:", list_row)

        self.e_lp1_shift = dspin(-5000, 5000, 0, " mm")
        self.e_lp2_shift = dspin(-5000, 5000, 0, " mm")
        whatif_layout.addRow("LP1 shift:", self.e_lp1_shift)
        whatif_layout.addRow("LP2 shift:", self.e_lp2_shift)

        self.btn_test_lp = QtGui.QPushButton("Test alternative LP")
        self.btn_test_lp.setEnabled(False)
        self.btn_test_lp.clicked.connect(self.testAlternativeLP)
        whatif_layout.addRow("", self.btn_test_lp)

        whatif_group.setLayout(whatif_layout)
        layout.addWidget(whatif_group)

        # ---- LoadCondition export ----
        transfer_group = QtGui.QGroupBox("LoadCondition Export + Stability")
        transfer_layout = QtGui.QVBoxLayout()

        self.btn_transfer_lc = QtGui.QPushButton("📊 Transfer & Stability Calculation")
        self.btn_transfer_lc.setStyleSheet(
            "QPushButton{background:#2d6a4f;color:white;font-weight:bold;"
            "padding:8px;border-radius:4px;font-size:11px;}"
            "QPushButton:hover{background:#1b4332;}"
            "QPushButton:disabled{background:#cccccc;color:#666;}"
        )
        self.btn_transfer_lc.setEnabled(False)
        self.btn_transfer_lc.setToolTip(
            "1. Writes crane data to LoadCondition\n"
            "2. Runs LoadCondition recalculation\n"
            "3. Calculates hydrostatics (ShipSinkAndTrim)\n"
            "Shows all results in a dialog.")
        self.btn_transfer_lc.clicked.connect(self.transferToLoadCondition)
        transfer_layout.addWidget(self.btn_transfer_lc)

        self.lbl_transfer_status = QtGui.QLabel("Not yet transferred")
        self.lbl_transfer_status.setAlignment(QtCore.Qt.AlignCenter)
        self.lbl_transfer_status.setStyleSheet("color: #666; font-size: 10px;")
        transfer_layout.addWidget(self.lbl_transfer_status)

        transfer_group.setLayout(transfer_layout)
        layout.addWidget(transfer_group)

        # ---- Collision info ----
        info_group = QtGui.QGroupBox("Collision Info")
        info_layout = QtGui.QVBoxLayout()
        self.info_text = QtGui.QTextEdit()
        self.info_text.setReadOnly(True)
        self.info_text.setMaximumHeight(150)
        self.info_text.setFont(QtGui.QFont("Courier", 9))
        info_layout.addWidget(self.info_text)
        info_group.setLayout(info_layout)
        layout.addWidget(info_group)

        # ---- Persistent buttons ----
        btn_layout = QtGui.QHBoxLayout()
        self.btn_cleanup = QtGui.QPushButton("Clear visualisation")
        self.btn_cleanup.clicked.connect(self.cleanup)
        self.btn_close = QtGui.QPushButton("Close")
        self.btn_close.clicked.connect(self.close)
        btn_layout.addWidget(self.btn_cleanup)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_close)

        layout.addStretch()
        scroll.setWidget(container)

        outer = QtGui.QVBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)
        outer.addWidget(scroll)
        outer.addLayout(btn_layout)
        self.setLayout(outer)

        self.setMinimumWidth(360)
        self.resize(380, 720)

    def findCranes(self):
        doc = App.activeDocument()
        if not doc:
            return
        cranes = [o for o in doc.Objects
                  if hasattr(o, "Proxy") and
                  getattr(o.Proxy, "Type", "") == "ShipCrane"]

        for combo in (self.crane_1_combo, self.crane_2_combo):
            combo.clear()
            combo.addItem("── select ──", None)
            for c in cranes:
                pos = c.Placement.Base
                combo.addItem(
                    f"{c.Label}  [{pos.x/1000:.1f}m, {pos.y/1000:.1f}m]",
                    c
                )
        if len(cranes) >= 2:
            self.crane_1_combo.setCurrentIndex(1)
            self.crane_2_combo.setCurrentIndex(2)

    def _update_dist_preview(self):
        try:
            d = self.e_lp_dist.value()
            c = self.e_cog_lp1.value()
            w = self.e_weight.value()
            if d < 1:
                return
            d2 = d - c
            if d2 <= 0 or c < 0:
                self.lbl_dist_preview.setText("⚠ COG outside LP range")
                return
            f1 = w * d2 / d
            f2 = w * c / d
            self.lbl_dist_preview.setText(f"→ Crane 1: {f1:.1f} t   Crane 2: {f2:.1f} t")
        except Exception:
            pass

    def initializeSimulation(self):
        c1 = self.crane_1_combo.currentData()
        c2 = self.crane_2_combo.currentData()

        if not c1 or not c2 or c1 is c2:
            QtGui.QMessageBox.warning(self, "Error", "Please select two different cranes!")
            return

        cog_lp1_mm = self.e_cog_lp1.value()
        lp_dist_mm = self.e_lp_dist.value()

        if cog_lp1_mm >= lp_dist_mm:
            QtGui.QMessageBox.warning(self, "Input error",
                f"COG to LP1 ({cog_lp1_mm:.0f} mm) must be less than "
                f"LP1 to LP2 ({lp_dist_mm:.0f} mm)!")
            return

        class LocalLoadGeometry:
            def __init__(self, length_mm, width_mm, height_mm,
                         lp1_from_aft_mm, lp_distance_mm, cog_from_lp1_mm,
                         rigging_length_mm=8000.0):
                self.length_mm = length_mm
                self.width_mm = width_mm
                self.height_mm = height_mm
                self.lp1_from_aft_mm = lp1_from_aft_mm
                self.lp_distance_mm = lp_distance_mm
                self.cog_from_lp1_mm = cog_from_lp1_mm
                self.rigging_length_mm = rigging_length_mm
                self.lp_height_from_top_mm = 0

            def get_world_transform(self, lp1_xy, lp2_xy, bot_z):
                dx = lp2_xy[0] - lp1_xy[0]
                dy = lp2_xy[1] - lp1_xy[1]
                d = math.sqrt(dx*dx + dy*dy) or 1.
                u = (dx/d, dy/d)
                v = (-u[1], u[0])
                aft = (lp1_xy[0] - u[0]*self.lp1_from_aft_mm,
                       lp1_xy[1] - u[1]*self.lp1_from_aft_mm)
                cx = aft[0] + u[0]*self.length_mm/2.
                cy = aft[1] + u[1]*self.length_mm/2.
                cz = bot_z + self.height_mm/2.
                return (cx, cy, cz), u, v

            def get_cog_xy(self, lp1_xy, lp2_xy):
                dx = lp2_xy[0] - lp1_xy[0]
                dy = lp2_xy[1] - lp1_xy[1]
                d = math.sqrt(dx*dx + dy*dy) or 1.
                u = (dx/d, dy/d)
                aft = (lp1_xy[0] - u[0]*self.lp1_from_aft_mm,
                       lp1_xy[1] - u[1]*self.lp1_from_aft_mm)
                return (aft[0] + u[0]*self.cog_from_lp1_mm,
                        aft[1] + u[1]*self.cog_from_lp1_mm)

            def get_corners_3d(self, lp1_xy, lp2_xy, bot_z):
                (cx, cy, cz), u, v = self.get_world_transform(lp1_xy, lp2_xy, bot_z)
                hl, hw, hh = self.length_mm/2., self.width_mm/2., self.height_mm/2.
                pts = []
                for sl in (+1, -1):
                    for sv in (+1, -1):
                        for sz in (+1, -1):
                            pts.append((cx + sl*hl*u[0] + sv*hw*v[0],
                                        cy + sl*hl*u[1] + sv*hw*v[1],
                                        cz + sz*hh))
                return pts

            def get_footprint_2d(self, lp1_xy, lp2_xy, bot_z):
                (cx, cy, cz), u, v = self.get_world_transform(lp1_xy, lp2_xy, bot_z)
                hl, hw = self.length_mm/2., self.width_mm/2.
                return [(cx + sl*hl*u[0] + sv*hw*v[0],
                         cy + sl*hl*u[1] + sv*hw*v[1])
                        for sl, sv in [(+1,+1),(+1,-1),(-1,-1),(-1,+1)]]

        class LocalShipGeometry:
            def __init__(self, length_mm, width_mm, freeboard_mm,
                         cx=0., cy=0., deck_z=0.):
                self.hl = length_mm/2.
                self.hw = width_mm/2.
                self.fb = freeboard_mm
                self.cx = cx
                self.cy = cy
                self.deck_z = deck_z

            def clearance_corners_2d(self, pts2d):
                min_cl = float('inf')
                for px, py in pts2d:
                    dx = max(self.cx-self.hl - px, 0., px - (self.cx+self.hl))
                    dy = max(self.cy-self.hw - py, 0., py - (self.cy+self.hw))
                    if dx == 0. and dy == 0.:
                        cl = -min(px-(self.cx-self.hl), (self.cx+self.hl)-px,
                                  py-(self.cy-self.hw), (self.cy+self.hw)-py)
                    else:
                        cl = math.sqrt(dx*dx + dy*dy)
                    min_cl = min(min_cl, cl)
                return min_cl

            def z_clearance_below(self, z):
                return z - self.deck_z

        load = LocalLoadGeometry(
            length_mm=self.e_length.value(),
            width_mm=self.e_width.value(),
            height_mm=self.e_height.value(),
            lp1_from_aft_mm=self.e_lp1_end.value(),
            lp_distance_mm=lp_dist_mm,
            cog_from_lp1_mm=cog_lp1_mm,
            rigging_length_mm=8000,
        )

        ship = LocalShipGeometry(
            length_mm=120000,
            width_mm=22000,
            freeboard_mm=15000,
            deck_z=self.e_deck_z.value(),
        )

        self.simulator = InteractiveSwingSimulator(c1, c2, load, ship)

        ok = self.simulator.compute_radii(
            self.e_weight.value(),
            cog_lp1_mm / 1000.0
        )

        if not ok:
            QtGui.QMessageBox.critical(self, "Error", "Capacity limit exceeded!")
            return

        self.simulator.setup_visualization()
        self.simulator.steps = self._generate_dummy_steps(c1, c2)

        if len(self.simulator.steps) == 0:
            QtGui.QMessageBox.warning(self, "Error",
                "No solution found!\n"
                "Check whether radii (r1, r2) and LP distance are geometrically reachable.")
            return

        mode = getattr(self.simulator, 'swing_mode', '?')
        r1 = self.simulator.r1_mm / 1000
        r2 = self.simulator.r2_mm / 1000
        f1 = getattr(self.simulator, 'load_1_t', 0)
        f2 = getattr(self.simulator, 'load_2_t', 0)
        mode_tx = {
            'LP1-first':   'LP1 (lighter crane) swung out first',
            'LP2-first':   'LP2 (heavier crane) swung out first',
            'no_solution': '⚠ No solution found!',
        }.get(mode, mode)
        summary = [
            "═══ Load distribution ═══",
            f"Crane 1:  {f1:.1f} t   →   radius {r1:.2f} m",
            f"Crane 2:  {f2:.1f} t   →   radius {r2:.2f} m",
            "",
            "═══ Lift mode ═══",
            mode_tx,
            "",
            f"Total steps: {len(self.simulator.steps)}",
        ]
        for w in getattr(self.simulator, 'dist_warnings', []):
            summary.append(f"⚠ {w}")
        self.info_text.setText("\n".join(summary))

        self.current_step_idx = 0
        self.showCurrentStep()

        self.btn_next.setEnabled(True)
        self.btn_prev.setEnabled(True)
        self.btn_apply_list.setEnabled(True)
        self.btn_test_lp.setEnabled(True)
        self.btn_transfer_lc.setEnabled(True)
        self.lbl_transfer_status.setText("Ready to transfer")
        self.lbl_transfer_status.setStyleSheet("color: #2196F3;")

    def _generate_dummy_steps(self, c1, c2):
        if not self.simulator:
            return []
        return self.simulator.generate_steps(
            sea_dir_deg=self.e_sea_dir.value(),
            land_dir_deg=self.e_land_dir.value(),
            n_steps=self.e_steps.value()
        )

    def showCurrentStep(self):
        if not self.simulator or not self.simulator.steps:
            return

        step = self.simulator.steps[self.current_step_idx]
        self.simulator.show_step(self.current_step_idx)

        self.lbl_step.setText(
            f"Step: {self.current_step_idx + 1} / {len(self.simulator.steps)}"
        )

        colors = {
            SwingStep.STATUS_OK:   ("#c8f7c5", "Clear"),
            SwingStep.STATUS_WARN: ("#fff3cd", "Warning: low clearances"),
            SwingStep.STATUS_FAIL: ("#f8d7da", "COLLISION!"),
        }
        bg, text = colors.get(step.status, ("#e2e3e5", "Unknown"))
        self.lbl_status.setStyleSheet(f"background-color: {bg}; padding: 5px;")
        self.lbl_status.setText(f"Status: {text}")

        f1   = getattr(self.simulator, 'load_1_t', 0)
        f2   = getattr(self.simulator, 'load_2_t', 0)
        mode = getattr(self.simulator, 'swing_mode', '')
        r1   = (step.radius_1_mm or 0) / 1000
        r2   = (step.radius_2_mm or 0) / 1000
        info = [
            f"Step {self.current_step_idx + 1} / {len(self.simulator.steps)}"
            f"   [{mode}]",
            "",
            "Load distribution:",
            f"  Crane 1:  {f1:.1f} t   Slew {step.slew_1:.1f}°   r = {r1:.2f} m",
            f"  Crane 2:  {f2:.1f} t   Slew {step.slew_2:.1f}°   r = {r2:.2f} m",
            "",
        ]
        if step.clearance_ship_hull is not None:
            info.append(f"Hull clearance:  {step.clearance_ship_hull/1000:.2f} m")
        if step.clearance_deck is not None:
            info.append(f"Deck clearance:  {step.clearance_deck/1000:.2f} m")
        for msg in step.messages:
            info.append(msg)
        self.info_text.setText("\n".join(info))

        self.btn_prev.setEnabled(self.current_step_idx > 0)
        self.btn_next.setEnabled(self.current_step_idx < len(self.simulator.steps) - 1)

    def nextStep(self):
        if self.simulator and self.current_step_idx < len(self.simulator.steps) - 1:
            self.current_step_idx += 1
            self.showCurrentStep()

    def prevStep(self):
        if self.simulator and self.current_step_idx > 0:
            self.current_step_idx -= 1
            self.showCurrentStep()

    def applyListAngle(self):
        angle = self.e_list_angle.value()
        if self.simulator:
            self.simulator.apply_list_angle(angle)
            self.simulator.steps = self._generate_dummy_steps(
                self.simulator.crane_1, self.simulator.crane_2
            )
            self.current_step_idx = 0
            self.showCurrentStep()

    def testAlternativeLP(self):
        pass

    def transferToLoadCondition(self):
        if not self.simulator:
            QtGui.QMessageBox.warning(self, "Error",
                "Simulation not initialised!")
            return

        c1 = self.crane_1_combo.currentData()
        c2 = self.crane_2_combo.currentData()

        if not c1 or not c2:
            QtGui.QMessageBox.warning(self, "Error", "Cranes not found!")
            return

        op = TandemLiftOperation(c1, c2)
        op.results['load_1']   = getattr(self.simulator, 'load_1_t', 0)
        op.results['load_2']   = getattr(self.simulator, 'load_2_t', 0)
        op.results['radius_1'] = self.simulator.r1_mm
        op.results['radius_2'] = self.simulator.r2_mm

        success, msg, hydro = op.transfer_to_loadcondition(
            auto_calculate=True,
            show_confirmation=True
        )

        if success:
            self.lbl_transfer_status.setText("✓ Transferred & calculated")
            self.lbl_transfer_status.setStyleSheet("color: #4CAF50; font-weight: bold;")
        else:
            self.lbl_transfer_status.setText("✗ Error")
            self.lbl_transfer_status.setStyleSheet("color: #f44336; font-weight: bold;")
            QtGui.QMessageBox.critical(self, "Error", msg)

    def cleanup(self):
        if self.simulator:
            self.simulator.cleanup()
            self.simulator = None
        self.lbl_step.setText("Step: - / -")
        self.lbl_status.setText("Status: Not initialised")
        self.lbl_status.setStyleSheet("padding: 5px;")
        self.btn_next.setEnabled(False)
        self.btn_prev.setEnabled(False)
        self.btn_transfer_lc.setEnabled(False)
        self.lbl_transfer_status.setText("Not yet transferred")
        self.lbl_transfer_status.setStyleSheet("color: #666; font-size: 10px;")

    def closeEvent(self, event):
        self.cleanup()
        event.accept()


# =============================================================================
# EXTERNAL ACCESS
# =============================================================================

def show_tandem_lift_dialog():
    """Show the interactive swing dialog."""
    dialog = InteractiveSwingDialog(Gui.getMainWindow())
    dialog.exec_()


def create_tandem_lift(crane_1, crane_2, total_weight_t,
                       cog_to_l1_m, l1_to_l2_m,
                       land_direction_deg=180.0,
                       slew_1=None, slew_2=None):
    """Programmatic tandem lift operation."""
    op = TandemLiftOperation(crane_1, crane_2)
    return op.execute(total_weight_t, cog_to_l1_m, l1_to_l2_m,
                      land_direction_deg, slew_1, slew_2)


__all__ = [
    'TandemLiftCalculator',
    'TandemGeometrySolver',
    'TandemLiftOperation',
    'InteractiveSwingDialog',
    'show_tandem_lift_dialog',
    'create_tandem_lift',
]
