# -*- coding: utf-8 -*-
"""
MonopileSwing.py  –  Schwingsimulation für Langlast (Monopile, Träger, …)
=========================================================================
"""

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtGui, QtCore
import Part, math
import sys
import os

# SICHERSTELLEN dass das Verzeichnis im Pfad ist
_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

# DIREKTE Imports - keine relativen Imports mehr
from TaskLiftOperation import SingleHookLift
from TandemLift import TandemLiftCalculator, TandemGeometrySolver
from CraneSpreadsheetTools import find_loadcondition, write_crane_to_loadcondition, get_crane_positions

# ── Farben ──────────────────────────────────────────────────────────────────
COLOR_OK   = (0.20, 0.78, 0.35)
COLOR_WARN = (1.00, 0.75, 0.10)
COLOR_FAIL = (0.88, 0.20, 0.22)
COLOR_RIG  = (0.10, 0.55, 0.90)
COLOR_TIP  = (1.00, 0.55, 0.00)

QC_OK   = QtGui.QColor("#d4edda")
QC_WARN = QtGui.QColor("#fff3cd")
QC_FAIL = QtGui.QColor("#f8d7da")
QC_NONE = QtGui.QColor("#e9ecef")

HULL_CL_MIN  =  500.0
TOWER_CL_MIN = 1000.0
BOOM_CL_MIN  = 1000.0
DECK_CL_MIN  =  200.0


# ── Geometrie-Helpers ────────────────────────────────────────────────────────

def _boom_tip_xy(crane_pos, radius_mm, slew_deg):
    a = math.radians(slew_deg)
    return (crane_pos[0] - radius_mm * math.sin(a),
            crane_pos[1] + radius_mm * math.cos(a))

def _dist2(a, b):
    return math.sqrt((a[0]-b[0])**2 + (a[1]-b[1])**2)

def _seg_pt_dist2(sa, sb, pt):
    dx, dy = sb[0]-sa[0], sb[1]-sa[1]
    denom  = dx*dx + dy*dy + 1e-12
    t = max(0., min(1., ((pt[0]-sa[0])*dx + (pt[1]-sa[1])*dy) / denom))
    cx, cy = sa[0]+t*dx, sa[1]+t*dy
    return math.sqrt((pt[0]-cx)**2 + (pt[1]-cy)**2)

def _boom_tip_z(crane_obj):
    cz  = float(crane_obj.Placement.Base.z)
    piv = float(crane_obj.BaseHeight) + float(crane_obj.BoomPivotHeight)
    return cz + piv + float(crane_obj.BoomLength) * math.sin(
        math.radians(float(crane_obj.LuffingAngle)))


# ── Lastgeometrie ────────────────────────────────────────────────────────────

class LoadGeometry:
    """
    Quader mit definierten Liftpunkten und COG.

    Koordinaten entlang der Längsachse (von Heckkante aus):
        0 ── lp1_from_aft ── LP1 ── lp_distance ── LP2 ── rest ── length
    COG liegt bei lp1_from_aft + cog_from_lp1 ab Heckkante.
    """

    def __init__(self, length_mm, width_mm, height_mm,
                 lp1_from_aft_mm, lp_distance_mm, cog_from_lp1_mm,
                 rigging_length_mm=8000.0):
        self.length_mm         = length_mm
        self.width_mm          = width_mm
        self.height_mm         = height_mm
        self.lp1_from_aft_mm   = lp1_from_aft_mm
        self.lp_distance_mm    = lp_distance_mm
        self.cog_from_lp1_mm   = cog_from_lp1_mm
        self.rigging_length_mm = rigging_length_mm
        self.lp2_from_aft_mm   = lp1_from_aft_mm + lp_distance_mm
        self.cog_from_aft_mm   = lp1_from_aft_mm + cog_from_lp1_mm

    def _frame(self, lp1_xy, lp2_xy):
        dx = lp2_xy[0] - lp1_xy[0]
        dy = lp2_xy[1] - lp1_xy[1]
        d  = math.sqrt(dx*dx + dy*dy) or 1.
        u  = (dx/d, dy/d)
        v  = (-u[1], u[0])
        aft = (lp1_xy[0] - u[0]*self.lp1_from_aft_mm,
               lp1_xy[1] - u[1]*self.lp1_from_aft_mm)
        cx = aft[0] + u[0]*self.length_mm/2.
        cy = aft[1] + u[1]*self.length_mm/2.
        return (cx, cy), u, v, aft

    def corners_3d(self, lp1_xy, lp2_xy, bot_z):
        (cx, cy), u, v, _ = self._frame(lp1_xy, lp2_xy)
        hl, hw, hh = self.length_mm/2., self.width_mm/2., self.height_mm/2.
        cz = bot_z + hh
        pts = []
        for sl in (+1, -1):
            for sv in (+1, -1):
                for sz in (+1, -1):
                    pts.append((cx + sl*hl*u[0] + sv*hw*v[0],
                                cy + sl*hl*u[1] + sv*hw*v[1],
                                cz + sz*hh))
        return pts

    def footprint_2d(self, lp1_xy, lp2_xy):
        (cx, cy), u, v, _ = self._frame(lp1_xy, lp2_xy)
        hl, hw = self.length_mm/2., self.width_mm/2.
        return [(cx + sl*hl*u[0] + sv*hw*v[0],
                 cy + sl*hl*u[1] + sv*hw*v[1])
                for sl, sv in [(+1,+1),(+1,-1),(-1,-1),(-1,+1)]]

    def cog_xy(self, lp1_xy, lp2_xy):
        _, u, _, aft = self._frame(lp1_xy, lp2_xy)
        return (aft[0] + u[0]*self.cog_from_aft_mm,
                aft[1] + u[1]*self.cog_from_aft_mm)

    def obb_shape(self, lp1_xy, lp2_xy, bot_z):
        (cx, cy), u, _, _ = self._frame(lp1_xy, lp2_xy)
        angle_deg = math.degrees(math.atan2(u[0], u[1]))
        box = Part.makeBox(
            self.length_mm, self.width_mm, self.height_mm,
            App.Vector(-self.length_mm/2., -self.width_mm/2., 0.)
        )
        box.rotate(App.Vector(0, 0, 0), App.Vector(0, 0, 1), -angle_deg)
        box.translate(App.Vector(cx, cy, bot_z))
        return box


class ShipGeometry:
    def __init__(self, length_mm, width_mm, freeboard_mm,
                 cx=0., cy=0., deck_z=0.):
        self.hl = length_mm/2.;  self.hw = width_mm/2.
        self.fb = freeboard_mm
        self.cx = cx;  self.cy = cy;  self.dz = deck_z

    def hull_cl_2d(self, px, py):
        dx = max(self.cx-self.hl - px, 0., px - (self.cx+self.hl))
        dy = max(self.cy-self.hw - py, 0., py - (self.cy+self.hw))
        if dx == 0. and dy == 0.:
            return -min(px-(self.cx-self.hl), (self.cx+self.hl)-px,
                        py-(self.cy-self.hw), (self.cy+self.hw)-py)
        return math.sqrt(dx*dx + dy*dy)

    def min_cl_corners(self, pts2d):
        return min(self.hull_cl_2d(p[0], p[1]) for p in pts2d)


# ── Einzelschritt ────────────────────────────────────────────────────────────

class SwingStep:
    OK    = "OK"
    WARN  = "WARNUNG"
    FAIL  = "KOLLISION"
    NOSOL = "KEINE LÖSUNG"

    def __init__(self, idx, t):
        self.idx    = idx
        self.t      = t
        self.status = self.OK
        self.msgs   = []
        self.slew_1 = self.slew_2 = None
        self.r1     = self.r2     = None
        self.tip1_xy = self.tip2_xy = None
        self.lp1_xy  = self.lp2_xy  = None
        self.load_bot_z = None
        self.corners = [];  self.fp = [];  self.cog_xy = None
        self.cl      = {}

    def fail(self, m):
        self.status = self.FAIL
        self.msgs.append(f"✗ {m}")

    def warn(self, m):
        if self.status == self.OK:
            self.status = self.WARN
        self.msgs.append(f"⚠ {m}")

    def ok(self, m):
        self.msgs.append(f"✓ {m}")

    def qcolor(self):
        return {self.OK:QC_OK, self.WARN:QC_WARN,
                self.FAIL:QC_FAIL, self.NOSOL:QC_NONE}.get(self.status, QC_NONE)

    def color3d(self):
        return {self.OK:COLOR_OK, self.WARN:COLOR_WARN,
                self.FAIL:COLOR_FAIL, self.NOSOL:(0.5,0.5,0.5)}.get(
                    self.status, COLOR_OK)

    def summary_lines(self):
        lines = [f"Schritt {self.idx+1}  ({self.t*100:.0f}%)  ── {self.status}"]
        if self.slew_1 is not None:
            lines += [
                f"  Slew 1 = {self.slew_1:.1f}°    Slew 2 = {self.slew_2:.1f}°",
                f"  Auslage 1 = {self.r1/1000:.2f}m   Auslage 2 = {self.r2/1000:.2f}m",
                f"  Baumspitze 1: ({self.tip1_xy[0]/1000:.2f}m, {self.tip1_xy[1]/1000:.2f}m)",
                f"  Baumspitze 2: ({self.tip2_xy[0]/1000:.2f}m, {self.tip2_xy[1]/1000:.2f}m)",
                f"  COG Last:     ({self.cog_xy[0]/1000:.2f}m, {self.cog_xy[1]/1000:.2f}m)",
                f"  Unterkante:   z = {self.load_bot_z/1000:.2f}m",
            ]
        lines += ["", "  Meldungen:"] + [f"    {m}" for m in self.msgs]
        if self.cl:
            lines.append("  Abstände:")
            for k, v in self.cl.items():
                sym = "✓" if v is None or v >= 0 else "✗"
                val = f"{v/1000:+.3f}m" if v is not None else "n/a"
                lines.append(f"    {sym} {k:22s}: {val}")
        return lines


# ── Simulator ────────────────────────────────────────────────────────────────

class MonopileSwingSimulator:

    def __init__(self, c1, c2, load: LoadGeometry, ship: ShipGeometry, n=10):
        self.c1   = c1;  self.c2   = c2
        self.load = load;  self.ship = ship;  self.n = n
        self.p1   = (float(c1.Placement.Base.x), float(c1.Placement.Base.y))
        self.p2   = (float(c2.Placement.Base.x), float(c2.Placement.Base.y))
        self.r1 = self.r2 = self.L1 = self.L2 = 0.
        self.steps = []
        # Krangewichte (werden von Dialog gesetzt)
        self.boom_weight_c1 = 0.0
        self.boom_weight_c2 = 0.0
        self.hook_weight_c1 = 0.0
        self.hook_weight_c2 = 0.0

    # ── Radien ──────────────────────────────────────────────────────────────

    def compute_radii(self, total_t, cog_to_lp1_m):
        calc      = TandemLiftCalculator()
        l1, l2, w = calc.calculate_from_lift_points(
            total_t, cog_to_lp1_m, self.load.lp_distance_mm / 1000.)
        r1,_,m1   = SingleHookLift(self.c1).calculate_optimal_radius(l1)
        r2,_,m2   = SingleHookLift(self.c2).calculate_optimal_radius(l2)
        errs = []
        if r1 == 0: errs.append(f"Kran 1 kann {l1:.1f}t nicht tragen: {m1}")
        if r2 == 0: errs.append(f"Kran 2 kann {l2:.1f}t nicht tragen: {m2}")
        for wi in w: errs.append(f"⚠ {wi}")
        self.r1, self.r2, self.L1, self.L2 = r1, r2, l1, l2
        return r1, r2, l1, l2, errs

    # ── Slew-2 aus Constraint ────────────────────────────────────────────────

    def _slew2_for_slew1(self, s1_deg, r1, r2, D):
        a1 = math.radians(s1_deg)
        T1 = (self.p1[0] - r1*math.sin(a1), self.p1[1] + r1*math.cos(a1))
        dx, dy = T1[0]-self.p2[0], T1[1]-self.p2[1]
        A =  2*r2*dx;  B = -2*r2*dy;  C = D*D - dx*dx - dy*dy - r2*r2
        R = math.sqrt(A*A + B*B)
        if R < 1e-6 or abs(C/R) > 1.:
            return None
        ph   = math.atan2(B, A)
        base = math.asin(C/R)
        cands = []
        for a2r in (base - ph, math.pi - base - ph):
            a2d = math.degrees(a2r) % 360
            T2  = (self.p2[0] - r2*math.sin(a2r), self.p2[1] + r2*math.cos(a2r))
            if abs(_dist2(T1, T2) - D) < D*0.002:
                cands.append(a2d)
        if not cands:
            return None
        return min(cands, key=lambda a: abs(((a-180)+180) % 360 - 180))

    # ── Kollisionsprüfung ────────────────────────────────────────────────────

    def _check(self, step: SwingStep):
        c   = step.corners
        fp  = step.fp
        bot = step.load_bot_z

        hcl = self.ship.min_cl_corners(fp)
        step.cl["Rumpf (horiz.)"] = hcl
        if   hcl < -HULL_CL_MIN:  step.fail(f"Kollision Rumpf ({hcl/1000:.2f}m Überschneidung)")
        elif hcl <  HULL_CL_MIN:  step.warn(f"Rumpf-Abstand gering: {hcl/1000:.3f}m")
        else:                      step.ok  (f"Rumpf OK: {hcl/1000:.2f}m")

        dcl = bot - self.ship.dz
        step.cl["Deck"] = dcl
        if   dcl < 0:              step.fail(f"Unter Deck! ({dcl/1000:.2f}m)")
        elif dcl < DECK_CL_MIN:    step.warn(f"Deck-Abstand gering: {dcl/1000:.3f}m")
        else:                      step.ok  (f"Deck OK: {dcl/1000:.2f}m")

        hull_top = self.ship.dz + self.ship.fb
        vcl = bot - hull_top
        step.cl["Reeling/Oberkante"] = vcl
        if vcl < 0 and hcl < 0:
            step.fail(f"Vertikale Rumpfkollision: Überschneidung {-vcl/1000:.2f}m")

        for i, (crane, p_xy) in enumerate([(self.c1, self.p1), (self.c2, self.p2)], 1):
            t_r  = float(crane.BaseDiameter) / 2.
            t_z0 = float(crane.Placement.Base.z)
            t_z1 = t_z0 + float(crane.BaseHeight) + float(crane.TowerHeight) + float(crane.BoomPivotHeight)
            tcl  = float('inf')
            for (px, py, pz) in c:
                if t_z0 <= pz <= t_z1:
                    tcl = min(tcl, _dist2((px,py), p_xy) - t_r)
            tcl = tcl if tcl < float('inf') else None
            step.cl[f"Kran-{i}-Turm"] = tcl
            if tcl is not None:
                if   tcl < 0:              step.fail(f"Kollision Kran-{i}-Turm ({tcl/1000:.2f}m)")
                elif tcl < TOWER_CL_MIN:   step.warn(f"Turm-{i}-Abstand gering: {tcl/1000:.3f}m")

        for i, (crane, p_xy, s_deg, r) in enumerate([
            (self.c1, self.p1, step.slew_1, step.r1),
            (self.c2, self.p2, step.slew_2, step.r2)
        ], 1):
            tip_xy = _boom_tip_xy(p_xy, r, s_deg)
            cz     = float(crane.Placement.Base.z)
            piv_z  = cz + float(crane.BaseHeight) + float(crane.BoomPivotHeight)
            tip_z  = _boom_tip_z(crane)
            bcl = float('inf')
            for (px, py, pz) in c:
                if piv_z <= pz <= tip_z + 1500:
                    bcl = min(bcl, _seg_pt_dist2(p_xy, tip_xy, (px, py)) - 500.)
            bcl = bcl if bcl < float('inf') else None
            step.cl[f"Baum {i}"] = bcl
            if bcl is not None:
                if   bcl < 0:              step.fail(f"Kollision Baum {i} ({bcl/1000:.2f}m)")
                elif bcl < BOOM_CL_MIN:    step.warn(f"Baum-{i}-Abstand gering: {bcl/1000:.3f}m")

    # ── Hauptsimulation ──────────────────────────────────────────────────────

    def simulate(self, sea_dir=0., land_dir=180.):
        self.steps = []
        if self.r1 == 0 or self.r2 == 0:
            s = SwingStep(0, 0.)
            s.status = s.NOSOL
            s.msgs.append("compute_radii() zuerst aufrufen!")
            self.steps.append(s)
            return self.steps

        r1, r2, D = self.r1, self.r2, self.load.lp_distance_mm
        solver    = TandemGeometrySolver(self.p1, self.p2)
        sol_sea   = solver.solve(r1, r2, D, sea_dir)
        sol_land  = solver.solve(r1, r2, D, land_dir)

        if sol_sea is None or sol_land is None:
            s = SwingStep(0, 0.)
            s.status = s.NOSOL
            s.msgs.append(
                f"Keine Start/Endkonfiguration!\n"
                f"  r1={r1/1000:.1f}m  r2={r2/1000:.1f}m  D={D/1000:.1f}m\n"
                f"  Kranabstand: {_dist2(self.p1,self.p2)/1000:.1f}m"
            )
            self.steps.append(s)
            return self.steps

        s1_start = sol_sea[0]
        s1_end   = sol_land[0]
        d_s1     = ((s1_end - s1_start + 360) % 360)
        if d_s1 > 180:
            d_s1 -= 360

        tz1 = _boom_tip_z(self.c1);  tz2 = _boom_tip_z(self.c2)
        lp_z     = min(tz1, tz2) - self.load.rigging_length_mm
        load_bot = lp_z - self.load.height_mm

        App.Console.PrintMessage(
            f"  Swing: r1={r1/1000:.2f}m r2={r2/1000:.2f}m D={D/1000:.2f}m "
            f"LP-Z={lp_z/1000:.2f}m Boden={load_bot/1000:.2f}m\n"
        )

        for i in range(self.n + 1):
            t    = i / self.n
            s1   = (s1_start + t * d_s1) % 360
            step = SwingStep(i, t)

            s2 = self._slew2_for_slew1(s1, r1, r2, D)
            if s2 is None:
                step.status = step.NOSOL
                step.msgs.append(f"Keine Slew-2-Lösung für Slew1={s1:.1f}°")
                self.steps.append(step)
                continue

            T1 = _boom_tip_xy(self.p1, r1, s1)
            T2 = _boom_tip_xy(self.p2, r2, s2)

            step.slew_1      = s1;      step.slew_2      = s2
            step.r1          = r1;      step.r2          = r2
            step.tip1_xy     = T1;      step.tip2_xy     = T2
            step.lp1_xy      = T1;      step.lp2_xy      = T2
            step.load_bot_z  = load_bot
            step.corners     = self.load.corners_3d(T1, T2, load_bot)
            step.fp          = self.load.footprint_2d(T1, T2)
            step.cog_xy      = self.load.cog_xy(T1, T2)

            self._check(step)
            self.steps.append(step)

            App.Console.PrintMessage(
                f"  [{i+1}/{self.n+1}]  S1={s1:.1f}°  S2={s2:.1f}°  → {step.status}\n"
            )

        return self.steps

    def overall_status(self):
        if not self.steps: return "–"
        if any(s.status in (SwingStep.FAIL, SwingStep.NOSOL) for s in self.steps):
            return SwingStep.FAIL
        if any(s.status == SwingStep.WARN for s in self.steps):
            return SwingStep.WARN
        return SwingStep.OK


# ── 3-D-Visualisierung ───────────────────────────────────────────────────────

class SwingVisualizer:

    NAMES = ["SwingLoad", "SwingRig1", "SwingRig2", "SwingTip1", "SwingTip2"]

    def __init__(self, sim: MonopileSwingSimulator):
        self.sim = sim
        self._objs = {}

    def _obj(self, name):
        doc = App.activeDocument()
        o   = doc.getObject(name)
        if o is None:
            o = doc.addObject("Part::Feature", name)
            if hasattr(o, "ViewObject"):
                o.ViewObject.Proxy = 0
        self._objs[name] = o
        return o

    def show_step(self, step: SwingStep):
        doc = App.activeDocument()
        if doc is None:
            return

        lo = self._obj("SwingLoad")
        if step.slew_1 is not None:
            try:
                lo.Shape = self.sim.load.obb_shape(
                    step.lp1_xy, step.lp2_xy, step.load_bot_z)
                lo.ViewObject.ShapeColor   = step.color3d()
                lo.ViewObject.Transparency = 30
            except Exception as e:
                App.Console.PrintError(f"SwingLoad shape: {e}\n")
        else:
            lo.Shape = Part.Shape()

        for name, crane, tip_xy in [
            ("SwingRig1", self.sim.c1, step.tip1_xy),
            ("SwingRig2", self.sim.c2, step.tip2_xy),
        ]:
            ro = self._obj(name)
            if tip_xy and step.slew_1 is not None:
                try:
                    tz  = _boom_tip_z(crane)
                    lpz = step.load_bot_z + self.sim.load.height_mm
                    ro.Shape = Part.makeLine(
                        App.Vector(tip_xy[0], tip_xy[1], tz),
                        App.Vector(tip_xy[0], tip_xy[1], lpz)
                    )
                    ro.ViewObject.ShapeColor = COLOR_RIG
                    ro.ViewObject.LineWidth  = 3.
                except Exception as e:
                    App.Console.PrintError(f"{name}: {e}\n")
            else:
                ro.Shape = Part.Shape()

        for name, crane, tip_xy in [
            ("SwingTip1", self.sim.c1, step.tip1_xy),
            ("SwingTip2", self.sim.c2, step.tip2_xy),
        ]:
            to = self._obj(name)
            if tip_xy and step.slew_1 is not None:
                try:
                    tz = _boom_tip_z(crane)
                    to.Shape = Part.makeSphere(
                        400., App.Vector(tip_xy[0], tip_xy[1], tz))
                    to.ViewObject.ShapeColor = COLOR_TIP
                except Exception as e:
                    App.Console.PrintError(f"{name}: {e}\n")
            else:
                to.Shape = Part.Shape()

        if step.slew_1 is not None:
            self.sim.c1.SlewAngle = step.slew_1
            self.sim.c2.SlewAngle = step.slew_2

        doc.recompute()
        Gui.updateGui()

    def cleanup(self):
        doc = App.activeDocument()
        if not doc: return
        for name in self.NAMES:
            o = doc.getObject(name)
            if o:
                doc.removeObject(o.Name)
        doc.recompute()


# ── Schematik-Widget ─────────────────────────────────────────────────────────

class LoadSchematicWidget(QtGui.QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(400, 140)
        self.setMaximumHeight(150)
        self._length  = 40000.
        self._lp1_aft = 8000.
        self._lp_dist = 20000.
        self._cog_lp1 = 10000.
        self._lp2_aft = self._lp1_aft + self._lp_dist
        self._cog_aft = self._lp1_aft + self._cog_lp1

    def update_values(self, length, lp1_aft, lp_dist, cog_lp1):
        self._length  = max(length, 1.)
        self._lp1_aft = lp1_aft
        self._lp_dist = lp_dist
        self._cog_lp1 = cog_lp1
        self._lp2_aft = lp1_aft + lp_dist
        self._cog_aft = lp1_aft + cog_lp1
        self.update()

    def paintEvent(self, event):
        qp = QtGui.QPainter(self)
        qp.setRenderHint(QtGui.QPainter.Antialiasing)
        W, H   = self.width(), self.height()
        M      = 30
        bar_h  = 24
        y_mid  = H // 2
        y_top  = y_mid - bar_h // 2
        y_bot  = y_mid + bar_h // 2

        def xp(v):
            return M + int((v / self._length) * (W - 2*M))

        qp.fillRect(0, 0, W, H, QtGui.QColor("#1e2329"))

        qp.setBrush(QtGui.QColor("#3d5278"))
        qp.setPen(QtGui.QPen(QtGui.QColor("#7fa8d0"), 1.5))
        qp.drawRect(M, y_top, W - 2*M, bar_h)

        qp.setPen(QtGui.QPen(QtGui.QColor("#4a5568"), 1, QtCore.Qt.DashLine))
        qp.drawLine(xp(self._lp1_aft), y_top - 25, xp(self._lp1_aft), y_bot + 30)
        qp.drawLine(xp(self._lp2_aft), y_top - 25, xp(self._lp2_aft), y_bot + 30)
        qp.drawLine(xp(self._cog_aft), y_top - 25, xp(self._cog_aft), y_bot + 30)

        qp.setPen(QtGui.QPen(QtGui.QColor("#8899aa")))
        fnt = qp.font()
        fnt.setPointSize(9)
        fnt.setBold(True)
        qp.setFont(fnt)
        qp.drawText(5, y_mid - 5, "← HECK")
        fm = qp.fontMetrics()
        qp.drawText(W - fm.width("BUG →") - 5, y_mid - 5, "BUG →")

        x1 = xp(self._lp1_aft)
        qp.setPen(QtGui.QPen(QtGui.QColor("#4fc3f7"), 2.5))
        qp.drawLine(x1, y_top - 8, x1, y_bot + 8)

        x2 = xp(self._lp2_aft)
        qp.setPen(QtGui.QPen(QtGui.QColor("#ff9800"), 2.5))
        qp.drawLine(x2, y_top - 8, x2, y_bot + 8)

        xc = xp(self._cog_aft)
        qp.setPen(QtGui.QPen(QtGui.QColor("#ffb74d"), 2))
        qp.setBrush(QtGui.QColor("#ffb74d"))
        qp.drawEllipse(xc - 6, y_bot + 6, 12, 12)

        fnt_small = qp.font()
        fnt_small.setPointSize(8)
        fnt_small.setBold(False)
        qp.setFont(fnt_small)

        qp.setPen(QtGui.QColor("#4fc3f7"))
        qp.drawText(x1 - 15, y_top - 12, "LP1")
        qp.setPen(QtGui.QPen(QtGui.QColor("#8899aa"), 1, QtCore.Qt.DashLine))
        qp.drawLine(M, y_bot + 20, x1, y_bot + 20)
        qp.setPen(QtGui.QColor("#a0b0c0"))
        qp.drawText((M + x1)//2 - 20, y_bot + 35, f"L1 = {self._lp1_aft/1000:.1f}m")

        qp.setPen(QtGui.QColor("#ff9800"))
        qp.drawText(x2 - 15, y_top - 12, "LP2")
        qp.setPen(QtGui.QPen(QtGui.QColor("#8899aa"), 1, QtCore.Qt.DashLine))
        qp.drawLine(x1, y_bot + 20, x2, y_bot + 20)
        qp.setPen(QtGui.QColor("#a0b0c0"))
        qp.drawText((x1 + x2)//2 - 20, y_bot + 35, f"L3 = {self._lp_dist/1000:.1f}m")

        qp.setPen(QtGui.QColor("#ffb74d"))
        qp.drawText(xc - 15, y_bot + 30, "COG")
        if self._cog_aft > self._lp1_aft:
            cog_from_lp1 = self._cog_aft - self._lp1_aft
            qp.setPen(QtGui.QPen(QtGui.QColor("#8899aa"), 1, QtCore.Qt.DashLine))
            qp.drawLine(x1, y_bot + 45, xc, y_bot + 45)
            qp.setPen(QtGui.QColor("#a0b0c0"))
            qp.drawText((x1 + xc)//2 - 20, y_bot + 60,
                        f"L2 = {cog_from_lp1/1000:.1f}m")
        else:
            cog_from_lp1 = self._lp1_aft - self._cog_aft
            qp.setPen(QtGui.QPen(QtGui.QColor("#8899aa"), 1, QtCore.Qt.DashLine))
            qp.drawLine(xc, y_bot + 45, x1, y_bot + 45)
            qp.setPen(QtGui.QColor("#a0b0c0"))
            qp.drawText((xc + x1)//2 - 20, y_bot + 60,
                        f"L2 = -{cog_from_lp1/1000:.1f}m")

        overhang = self._length - self._lp2_aft
        if overhang > 0:
            qp.setPen(QtGui.QPen(QtGui.QColor("#8899aa"), 1, QtCore.Qt.DashLine))
            qp.drawLine(x2, y_top - 25, W - M, y_top - 25)
            qp.setPen(QtGui.QColor("#a0b0c0"))
            qp.drawText((x2 + W - M)//2 - 25, y_top - 35,
                        f"Überhang = {overhang/1000:.1f}m")

        qp.setPen(QtGui.QPen(QtGui.QColor("#ffffff"), 1))
        qp.drawLine(M, y_top - 45, W - M, y_top - 45)
        qp.setPen(QtGui.QColor("#ffffff"))
        qp.drawText((M + W - M)//2 - 30, y_top - 50,
                    f"L gesamt = {self._length/1000:.1f}m")

        qp.end()


# ── Hauptdialog ───────────────────────────────────────────────────────────────

class SwingSimulationDialog(QtGui.QDialog):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Monopile / Langlast  –  Schwingsimulation")
        self.setMinimumWidth(700)
        self.setMinimumHeight(800)
        self.simulator  = None
        self.visualizer = None
        self._timer     = QtCore.QTimer(self)
        self._timer.timeout.connect(self._auto_advance)
        self._play_idx  = 0

        # Krangewicht-Eingaben (werden dynamisch befüllt)
        self.crane_boom_inputs = {}   # {crane_obj: QDoubleSpinBox}
        self.crane_hook_inputs = {}   # {crane_obj: QDoubleSpinBox}

        self.setupUI()
        self.findCranes()

    # ── UI ───────────────────────────────────────────────────────────────────

    def setupUI(self):
        root = QtGui.QVBoxLayout(self)
        root.setSpacing(4)

        self.tabs = QtGui.QTabWidget()
        root.addWidget(self.tabs, 1)

        # ═══════════════════════════ TAB 1: Eingabe ══════════════════════════
        t1  = QtGui.QWidget()
        t1l = QtGui.QVBoxLayout(t1)
        self.tabs.addTab(t1, "Eingabe")

        # Kräne
        cg = QtGui.QGroupBox("Kräne")
        cl = QtGui.QFormLayout(cg)
        self.cb_c1 = QtGui.QComboBox()
        self.cb_c2 = QtGui.QComboBox()
        cl.addRow("Kran 1  (LP1 / Heckseite):", self.cb_c1)
        cl.addRow("Kran 2  (LP2 / Bugseite):",  self.cb_c2)
        t1l.addWidget(cg)

        # Schematik
        schema_group  = QtGui.QGroupBox("Lastgeometrie - Übersicht")
        schema_layout = QtGui.QVBoxLayout(schema_group)
        self.schematic = LoadSchematicWidget()
        schema_layout.addWidget(self.schematic)
        legend = QtGui.QLabel(
            "L1 = Abstand Heck → LP1 | L2 = Abstand LP1 → COG "
            "(+ in Richtung LP2) | L3 = Abstand LP1 → LP2 | "
            "Überhang = LP2 → Bug"
        )
        legend.setWordWrap(True)
        legend.setStyleSheet("color: #8899aa; font-size: 8pt; padding: 2px;")
        schema_layout.addWidget(legend)
        t1l.addWidget(schema_group)

        # Zwei Spalten
        cols = QtGui.QHBoxLayout()

        # Linke Spalte: Lastgeometrie
        lgb = QtGui.QGroupBox("Lastgeometrie (Quader)")
        lgl = QtGui.QFormLayout(lgb)

        def mm(lo, hi, val, tooltip=""):
            w = QtGui.QDoubleSpinBox()
            w.setRange(lo, hi)
            w.setValue(val)
            w.setSuffix(" mm")
            w.setDecimals(0)
            w.setSingleStep(500)
            if tooltip:
                w.setToolTip(tooltip)
            return w

        self.e_len  = mm(500,   300000, 40000, "Gesamtlänge der Last")
        self.e_wid  = mm(100,    30000,  3500, "Breite der Last")
        self.e_hgt  = mm(100,    20000,  3000, "Höhe der Last")
        self.e_lp1a = mm(0,     200000,  8000, "L1: Abstand von Heckkante zu LP1")
        self.e_lpd  = mm(100,   200000, 20000, "L3: Abstand zwischen LP1 und LP2")
        self.e_clp1 = mm(-50000,100000, 10000,
                         "L2: Abstand von LP1 zu COG (+ in Richtung LP2)")
        self.e_rig  = mm(1000,   50000,  8000, "Länge der Anschlagmittel")

        for e in (self.e_len, self.e_lp1a, self.e_lpd, self.e_clp1):
            e.valueChanged.connect(self._upd_schema)

        lgl.addRow("Länge (x):",              self.e_len)
        lgl.addRow("Breite (y):",             self.e_wid)
        lgl.addRow("Höhe (z):",               self.e_hgt)
        lgl.addRow("L1 (Heck → LP1):",        self.e_lp1a)
        lgl.addRow("L3 (LP1 → LP2):",         self.e_lpd)
        lgl.addRow("L2 (LP1 → COG):",         self.e_clp1)
        lgl.addRow("Slinglänge:",              self.e_rig)
        cols.addWidget(lgb)

        # Rechte Spalte
        rg = QtGui.QGroupBox("Last / Schiff / Simulation")
        rl = QtGui.QFormLayout(rg)

        def ds(lo, hi, val, sfx, dec=1, tooltip=""):
            w = QtGui.QDoubleSpinBox()
            w.setRange(lo, hi)
            w.setValue(val)
            w.setSuffix(sfx)
            w.setDecimals(dec)
            if tooltip:
                w.setToolTip(tooltip)
            return w

        self.e_wt    = ds(0.1, 5000,  200,    " t", 1, "Gesamtgewicht der Last")
        self.e_shipL = mm(10000, 600000, 120000, "Schiffslänge")
        self.e_shipW = mm(1000,  100000,  22000, "Schiffsbreite")
        self.e_shipF = mm(500,    30000,  15000, "Freibord (Höhe bis Reeling)")
        self.e_seaD  = ds(0, 359.9,   0,  " °", 1,
                          "Schwenkwinkel in Seerichtung (Start)")
        self.e_lanD  = ds(0, 359.9, 180,  " °", 1,
                          "Schwenkwinkel in Landrichtung (Ziel)")
        self.e_nst   = QtGui.QSpinBox()
        self.e_nst.setRange(3, 50)
        self.e_nst.setValue(10)
        self.e_nst.setToolTip("Anzahl der Simulationsschritte")

        rl.addRow("Gesamtgewicht:",       self.e_wt)
        rl.addRow("Schiffslänge:",        self.e_shipL)
        rl.addRow("Schiffsbreite:",       self.e_shipW)
        rl.addRow("Freibord (Reeling):",  self.e_shipF)
        rl.addRow("See-Richtung:",        self.e_seaD)
        rl.addRow("Land-Richtung:",       self.e_lanD)
        rl.addRow("Schritte:",            self.e_nst)
        cols.addWidget(rg)
        t1l.addLayout(cols)

        # ── Krangewichte (dynamisch) ─────────────────────────────────────────
        self.crane_weights_group  = QtGui.QGroupBox("Krangewichte")
        self.crane_weights_layout = QtGui.QFormLayout()
        self.crane_weights_group.setLayout(self.crane_weights_layout)
        self.crane_weights_group.setVisible(False)
        t1l.addWidget(self.crane_weights_group)

        # Start-Button
        self.btn_sim = QtGui.QPushButton("▶  Simulation berechnen")
        self.btn_sim.setMinimumHeight(42)
        self.btn_sim.setStyleSheet(
            "QPushButton{background:#2563eb;color:white;font-weight:bold;"
            "font-size:14px;border-radius:5px;padding:8px;}"
            "QPushButton:hover{background:#1d4ed8;}"
            "QPushButton:pressed{background:#1e40af;}"
        )
        self.btn_sim.clicked.connect(self.runSimulation)
        t1l.addWidget(self.btn_sim)

        # ══════════════════════════ TAB 2: Ergebnisse ════════════════════════
        t2  = QtGui.QWidget()
        t2l = QtGui.QVBoxLayout(t2)
        self.tabs.addTab(t2, "Ergebnisse")

        self.lbl_overall = QtGui.QLabel("Noch keine Simulation durchgeführt")
        self.lbl_overall.setAlignment(QtCore.Qt.AlignCenter)
        self.lbl_overall.setFixedHeight(40)
        self.lbl_overall.setStyleSheet(
            "font-weight:bold;font-size:13px;border-radius:5px;"
            "padding:4px;background:#e9ecef;color:#555;"
        )
        t2l.addWidget(self.lbl_overall)

        # Navigation
        nav = QtGui.QHBoxLayout()
        self.btn_prev = QtGui.QPushButton("◀◀")
        self.btn_prev.setFixedWidth(40)
        self.btn_prev.clicked.connect(self._prev)
        self.slider = QtGui.QSlider(QtCore.Qt.Horizontal)
        self.slider.setMinimum(0)
        self.slider.setMaximum(0)
        self.slider.valueChanged.connect(self._on_slider)
        self.lbl_step = QtGui.QLabel("–/–")
        self.lbl_step.setFixedWidth(60)
        self.lbl_step.setAlignment(QtCore.Qt.AlignCenter)
        self.btn_next = QtGui.QPushButton("▶▶")
        self.btn_next.setFixedWidth(40)
        self.btn_next.clicked.connect(self._next)
        self.btn_play = QtGui.QPushButton("▶ Play")
        self.btn_play.setCheckable(True)
        self.btn_play.setFixedWidth(80)
        self.btn_play.toggled.connect(self._toggle_play)
        nav.addWidget(self.btn_prev)
        nav.addWidget(self.slider, 1)
        nav.addWidget(self.lbl_step)
        nav.addWidget(self.btn_next)
        nav.addWidget(self.btn_play)
        t2l.addLayout(nav)

        # Liste / Detail
        spl = QtGui.QSplitter(QtCore.Qt.Horizontal)
        self.step_list = QtGui.QListWidget()
        self.step_list.setMaximumWidth(200)
        self.step_list.currentRowChanged.connect(self._on_list)
        spl.addWidget(self.step_list)
        self.detail = QtGui.QTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setFont(QtGui.QFont("Courier", 9))
        spl.addWidget(self.detail)
        spl.setStretchFactor(0, 0)
        spl.setStretchFactor(1, 1)
        t2l.addWidget(spl, 1)

        # Export-Button
        self.btn_export = QtGui.QPushButton(
            "📋  Aktuellen Schritt → LoadCondition schreiben")
        self.btn_export.setEnabled(False)
        self.btn_export.setStyleSheet(
            "QPushButton{background:#2d6a4f;color:white;font-weight:bold;"
            "padding:6px;border-radius:4px;}"
            "QPushButton:hover{background:#1b4332;}"
            "QPushButton:disabled{background:#cccccc;color:#666;}"
        )
        self.btn_export.setToolTip(
            "Schreibt Baumgewicht + Hakenlasten beider Kräne\n"
            "mit aktuellen Positionen in das LoadCondition-Spreadsheet.\n"
            "Wähle zuerst den kritischsten Schritt im Slider.")
        self.btn_export.clicked.connect(self._export_to_loadcondition)
        t2l.addWidget(self.btn_export)

        # Untere Buttons
        bot = QtGui.QHBoxLayout()
        self.btn_clean = QtGui.QPushButton("3D-Objekte entfernen")
        self.btn_clean.clicked.connect(self._cleanup)
        close_btn = QtGui.QPushButton("Schließen")
        close_btn.clicked.connect(self.accept)
        bot.addWidget(self.btn_clean)
        bot.addStretch()
        bot.addWidget(close_btn)
        root.addLayout(bot)

        self._upd_schema()

    # ── Hilfsmethoden ────────────────────────────────────────────────────────

    def _upd_schema(self):
        self.schematic.update_values(
            self.e_len.value(),
            self.e_lp1a.value(),
            self.e_lpd.value(),
            self.e_clp1.value()
        )

    def findCranes(self):
        doc = App.activeDocument()
        if not doc:
            return

        cranes = [o for o in doc.Objects
                  if getattr(getattr(o, "Proxy", None), "Type", "") == "ShipCrane"]

        for cb in (self.cb_c1, self.cb_c2):
            cb.clear()
            cb.addItem("── Bitte Kran wählen ──", None)
            for c in cranes:
                pos = c.Placement.Base
                cb.addItem(
                    f"{c.Label}  [{pos.x/1000:.1f}m, {pos.y/1000:.1f}m]",
                    c
                )

        if len(cranes) >= 2:
            self.cb_c1.setCurrentIndex(1)
            self.cb_c2.setCurrentIndex(2)

        self._rebuild_crane_weight_inputs(cranes)

    def _rebuild_crane_weight_inputs(self, cranes):
        """Baut Gewichts-Eingabezeilen dynamisch für jeden Kran."""
        while self.crane_weights_layout.count():
            item = self.crane_weights_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.crane_boom_inputs.clear()
        self.crane_hook_inputs.clear()

        if not cranes:
            self.crane_weights_group.setVisible(False)
            return

        self.crane_weights_group.setVisible(True)

        for i, crane in enumerate(cranes, 1):
            if i > 1:
                sep = QtGui.QFrame()
                sep.setFrameShape(QtGui.QFrame.HLine)
                sep.setStyleSheet("color: #cccccc;")
                self.crane_weights_layout.addRow(sep)

            lbl_crane = QtGui.QLabel(f"── {crane.Label} ──")
            lbl_crane.setStyleSheet("font-weight: bold; color: #336699;")
            self.crane_weights_layout.addRow(lbl_crane)

            # Baumgewicht – aus Property vorbelegen
            boom_default = float(crane.BoomWeight) \
                if hasattr(crane, "BoomWeight") else 0.0
            boom_spin = QtGui.QDoubleSpinBox()
            boom_spin.setRange(0.0, 500.0)
            boom_spin.setValue(boom_default)
            boom_spin.setSuffix(" t")
            boom_spin.setDecimals(2)
            boom_spin.setToolTip(
                f"Eigengewicht Kranbaum {crane.Label}\n"
                f"(wichtig für Single-Hook-Lift mit Gegengewicht)")
            self.crane_weights_layout.addRow(
                f"Kranbaum {crane.Label}:", boom_spin)
            self.crane_boom_inputs[crane] = boom_spin

            # Last am Haken
            hook_spin = QtGui.QDoubleSpinBox()
            hook_spin.setRange(0.0, 5000.0)
            hook_spin.setValue(0.0)
            hook_spin.setSuffix(" t")
            hook_spin.setDecimals(2)
            hook_spin.setToolTip(f"Nutzlast am Haken {crane.Label}")
            self.crane_weights_layout.addRow(
                f"Last Haken {crane.Label}:", hook_spin)
            self.crane_hook_inputs[crane] = hook_spin

    # ── Simulation ───────────────────────────────────────────────────────────

    def runSimulation(self):
        c1 = self.cb_c1.currentData()
        c2 = self.cb_c2.currentData()

        if not c1 or not c2 or c1 is c2:
            QtGui.QMessageBox.warning(
                self, "Fehler",
                "Bitte zwei verschiedene Kräne auswählen!")
            return

        # Krangewichte auslesen
        boom_weight_c1 = (self.crane_boom_inputs[c1].value()
                          if c1 in self.crane_boom_inputs
                          else float(getattr(c1, 'BoomWeight', 0.0)))
        boom_weight_c2 = (self.crane_boom_inputs[c2].value()
                          if c2 in self.crane_boom_inputs
                          else float(getattr(c2, 'BoomWeight', 0.0)))
        hook_weight_c1 = (self.crane_hook_inputs[c1].value()
                          if c1 in self.crane_hook_inputs else 0.0)
        hook_weight_c2 = (self.crane_hook_inputs[c2].value()
                          if c2 in self.crane_hook_inputs else 0.0)

        App.Console.PrintMessage(
            f"Krangewichte:\n"
            f"  {c1.Label}: Baum={boom_weight_c1:.2f}t, "
            f"Haken={hook_weight_c1:.2f}t\n"
            f"  {c2.Label}: Baum={boom_weight_c2:.2f}t, "
            f"Haken={hook_weight_c2:.2f}t\n"
        )

        load = LoadGeometry(
            self.e_len.value(),  self.e_wid.value(),   self.e_hgt.value(),
            self.e_lp1a.value(), self.e_lpd.value(),   self.e_clp1.value(),
            self.e_rig.value()
        )
        ship = ShipGeometry(
            self.e_shipL.value(), self.e_shipW.value(), self.e_shipF.value()
        )
        sim = MonopileSwingSimulator(
            c1, c2, load, ship, self.e_nst.value()
        )

        # Gewichte im Simulator speichern
        sim.boom_weight_c1 = boom_weight_c1
        sim.boom_weight_c2 = boom_weight_c2
        sim.hook_weight_c1 = hook_weight_c1
        sim.hook_weight_c2 = hook_weight_c2

        r1, r2, l1, l2, errs = sim.compute_radii(
            self.e_wt.value(),
            self.e_clp1.value() / 1000.
        )

        if r1 == 0 or r2 == 0:
            QtGui.QMessageBox.critical(
                self, "Kapazitätsfehler", "\n".join(errs))
            return

        steps = sim.simulate(self.e_seaD.value(), self.e_lanD.value())

        self.simulator = sim
        if self.visualizer:
            self.visualizer.cleanup()
        self.visualizer = SwingVisualizer(sim)

        # Schritt-Liste
        self.step_list.clear()
        for step in steps:
            item = QtGui.QListWidgetItem(
                f"  {step.idx+1:2d}  {step.t*100:3.0f}%  {step.status}"
            )
            item.setBackground(step.qcolor())
            self.step_list.addItem(item)

        self.slider.setMaximum(max(0, len(steps) - 1))
        self.slider.setValue(0)

        # Gesamtstatus-Banner
        os = sim.overall_status()
        style_map = {
            SwingStep.OK:    ("background:#d4edda;color:#155724;",
                              "✓  Durchschwingen möglich – keine Kollisionen"),
            SwingStep.WARN:  ("background:#fff3cd;color:#856404;",
                              "⚠  Möglich mit Einschränkungen – Warnungen prüfen"),
            SwingStep.FAIL:  ("background:#f8d7da;color:#721c24;",
                              "✗  Kollision! Durchschwingen NICHT möglich"),
            SwingStep.NOSOL: ("background:#e9ecef;color:#555;",
                              "–  Keine Lösung gefunden"),
        }
        sty, text = style_map.get(os, ("", os))
        ok_n = sum(1 for s in steps if s.status == SwingStep.OK)
        w_n  = sum(1 for s in steps if s.status == SwingStep.WARN)
        f_n  = sum(1 for s in steps if s.status in
                   (SwingStep.FAIL, SwingStep.NOSOL))
        self.lbl_overall.setText(
            f"{text}   (✓{ok_n}  ⚠{w_n}  ✗{f_n})")
        self.lbl_overall.setStyleSheet(
            f"font-weight:bold;font-size:12px;border-radius:5px;"
            f"padding:4px;{sty}"
        )

        self.btn_export.setEnabled(True)
        self.tabs.setCurrentIndex(1)
        if steps:
            self.step_list.setCurrentRow(0)

    # ── Navigation ──────────────────────────────────────────────────────────

    def _on_slider(self, val):
        n = len(self.simulator.steps) if self.simulator else 0
        self.lbl_step.setText(f"{val+1}/{n}" if n else "–/–")
        self.step_list.blockSignals(True)
        self.step_list.setCurrentRow(val)
        self.step_list.blockSignals(False)
        self._show(val)

    def _on_list(self, row):
        if row < 0:
            return
        self.slider.blockSignals(True)
        self.slider.setValue(row)
        self.slider.blockSignals(False)
        self._show(row)

    def _show(self, idx):
        if not self.simulator or idx >= len(self.simulator.steps):
            return
        step = self.simulator.steps[idx]
        self.detail.setText("\n".join(step.summary_lines()))
        if self.visualizer:
            self.visualizer.show_step(step)

    def _prev(self):
        self.slider.setValue(max(0, self.slider.value() - 1))

    def _next(self):
        self.slider.setValue(min(self.slider.maximum(), self.slider.value() + 1))

    def _toggle_play(self, on):
        if on:
            self._play_idx = self.slider.value()
            self.btn_play.setText("⏹ Stop")
            self._timer.start(900)
        else:
            self._timer.stop()
            self.btn_play.setText("▶ Play")

    def _auto_advance(self):
        self._play_idx += 1
        if self._play_idx > self.slider.maximum():
            self._play_idx = 0
        self.slider.setValue(self._play_idx)

    def _cleanup(self):
        if self.visualizer:
            self.visualizer.cleanup()
        self.visualizer = None

    def closeEvent(self, event):
        self._timer.stop()
        super().closeEvent(event)

    # ── Export → LoadCondition ────────────────────────────────────────────────

    def _export_to_loadcondition(self):
        # Importe sind bereits am Anfang der Datei geladen
        if 'find_loadcondition' not in globals():
            QtGui.QMessageBox.critical(
                self, "Import-Fehler",
                "CraneSpreadsheetTools nicht verfügbar!")
            return

        if not self.simulator:
            return

        idx  = self.slider.value()
        step = self.simulator.steps[idx]

        if step.slew_1 is None:
            QtGui.QMessageBox.warning(
                self, "Kein Schritt",
                "Dieser Schritt hat keine gültige Kranposition.")
            return

        doc = App.activeDocument()
        lc  = find_loadcondition(doc)
        if not lc:
            QtGui.QMessageBox.critical(
                self, "Fehler",
                "Kein LoadCondition-Spreadsheet gefunden!\n"
                "Bitte zuerst Load Condition erstellen.")
            return

        c1 = self.simulator.c1
        c2 = self.simulator.c2

        boom_c1, hook_c1 = get_crane_positions(c1)
        boom_c2, hook_c2 = get_crane_positions(c2)

        boom_kg_c1 = (self.crane_boom_inputs[c1].value()
                      if c1 in self.crane_boom_inputs
                      else float(getattr(c1, 'BoomWeight', 0.0))) * 1000.0
        boom_kg_c2 = (self.crane_boom_inputs[c2].value()
                      if c2 in self.crane_boom_inputs
                      else float(getattr(c2, 'BoomWeight', 0.0))) * 1000.0
        hook_kg_c1 = (self.crane_hook_inputs[c1].value()
                      if c1 in self.crane_hook_inputs else 0.0) * 1000.0
        hook_kg_c2 = (self.crane_hook_inputs[c2].value()
                      if c2 in self.crane_hook_inputs else 0.0) * 1000.0

        crane_data = {
            c1.Label: {
                'boom_kg':  boom_kg_c1,
                'hook_kg':  hook_kg_c1,
                'boom_pos': boom_c1,
                'hook_pos': hook_c1,
            },
            c2.Label: {
                'boom_kg':  boom_kg_c2,
                'hook_kg':  hook_kg_c2,
                'boom_pos': boom_c2,
                'hook_pos': hook_c2,
            },
        }

        App.Console.PrintMessage(
            f"LoadCondition Export – Schritt {idx+1}:\n"
            f"  {c1.Label}: Boom={boom_kg_c1:.0f}kg "
            f"@ ({boom_c1[0]:.2f},{boom_c1[1]:.2f},{boom_c1[2]:.2f})m  "
            f"Haken={hook_kg_c1:.0f}kg "
            f"@ ({hook_c1[0]:.2f},{hook_c1[1]:.2f},{hook_c1[2]:.2f})m\n"
            f"  {c2.Label}: Boom={boom_kg_c2:.0f}kg "
            f"@ ({boom_c2[0]:.2f},{boom_c2[1]:.2f},{boom_c2[2]:.2f})m  "
            f"Haken={hook_kg_c2:.0f}kg "
            f"@ ({hook_c2[0]:.2f},{hook_c2[1]:.2f},{hook_c2[2]:.2f})m\n"
        )

        if write_crane_to_loadcondition(lc, crane_data):
            doc.recompute()
            QtGui.QMessageBox.information(
                self, "Gespeichert",
                f"Schritt {idx+1} wurde in LoadCondition geschrieben.\n\n"
                f"Bitte Stabilitätsrechnung neu starten.")
        else:
            QtGui.QMessageBox.warning(
                self, "Nicht gefunden",
                "CRANES-Sektion nicht im Spreadsheet gefunden.\n"
                "Bitte LoadCondition neu erstellen.")


# ── Öffentliche API ───────────────────────────────────────────────────────────

def simulate_monopile_swing(crane_1, crane_2,
                             length_mm, width_mm, height_mm,
                             lp1_from_aft_mm, lp_distance_mm, cog_from_lp1_mm,
                             total_weight_t,
                             ship_length_mm, ship_width_mm, ship_freeboard_mm,
                             rigging_mm=8000, sea_dir=0., land_dir=180., n=10):
    """Programmatischer Aufruf ohne Dialog."""
    load = LoadGeometry(length_mm, width_mm, height_mm,
                        lp1_from_aft_mm, lp_distance_mm,
                        cog_from_lp1_mm, rigging_mm)
    ship = ShipGeometry(ship_length_mm, ship_width_mm, ship_freeboard_mm)
    sim  = MonopileSwingSimulator(crane_1, crane_2, load, ship, n)
    sim.compute_radii(total_weight_t, cog_from_lp1_mm / 1000.)
    return sim.simulate(sea_dir, land_dir)


__all__ = [
    "LoadGeometry", "ShipGeometry", "SwingStep",
    "MonopileSwingSimulator", "SwingVisualizer",
    "SwingSimulationDialog", "simulate_monopile_swing",
]
