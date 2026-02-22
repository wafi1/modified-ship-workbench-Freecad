# -*- coding: utf-8 -*-
"""
InteractiveSwing.py - Interaktive Schwingsimulation mit 3D-Visualisierung
Schritt-für-Schritt Steuerung mit manueller Bestätigung, Kollisionsanzeige 
und "Was-wäre-wenn" Funktionen (Schlagseite, alternative Liftpunkte).
"""

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtGui, QtCore
import math
import copy

try:
    from .TaskLiftOperation import SingleHookLift
    from .TandemLift import TandemLiftCalculator, TandemGeometrySolver
    from .MonopileSwing import LoadGeometry, ShipGeometry, SwingStep
except ImportError:
    from TaskLiftOperation import SingleHookLift
    from TandemLift import TandemLiftCalculator, TandemGeometrySolver
    from MonopileSwing import LoadGeometry, ShipGeometry, SwingStep


# ---------------------------------------------------------------------------
# 3D VISUALISIERUNG
# ---------------------------------------------------------------------------

class LoadVisual:
    """Erstellt und verwaltet die 3D-Visualisierung der Last."""
    
    def __init__(self, doc, load_geom, name="SwingLoad"):
        self.doc = doc
        self.load_geom = load_geom
        self.name = name
        self.shape = None
        self.corners_obj = None
        self.cog_obj = None
        self.sling_lines = []
        
    def create(self, lp1_xy, lp2_xy, bottom_z):
        """Erstellt die Last-Geometrie als Quader."""
        # Altes Objekt löschen falls vorhanden
        if self.name in [obj.Name for obj in self.doc.Objects]:
            self.doc.removeObject(self.name)
            
        corners = self.load_geom.get_corners_3d(lp1_xy, lp2_xy, bottom_z)
        
        # Erstelle Quader aus den 8 Ecken
        # Vereinfacht: Box mit Länge/Breite/Höhe, positioniert am COG
        (cx, cy, cz), u, v = self.load_geom.get_world_transform(lp1_xy, lp2_xy, bottom_z)
        
        # Box erstellen
        box = self.doc.addObject("Part::Box", self.name)
        box.Length = self.load_geom.length_mm
        box.Width = self.load_geom.width_mm  
        box.Height = self.load_geom.height_mm
        
        # Position: COG ist Zentrum
        box.Placement.Base = App.Vector(
            cx - self.load_geom.length_mm/2 * u[0],
            cy - self.load_geom.length_mm/2 * u[1], 
            bottom_z
        )
        
        # Rotation ausrichten nach u-Vektor (Längsrichtung)
        angle = math.degrees(math.atan2(u[0], u[1]))  # Winkel zur Y-Achse
        box.Placement.Rotation = App.Rotation(App.Vector(0, 0, 1), -angle)
        
        box.ViewObject.ShapeColor = (0.8, 0.6, 0.4)  # Holzfarben/Braun
        box.ViewObject.Transparency = 30
        
        self.shape = box
        
        # COG-Marker
        cog_xy = self.load_geom.get_cog_xy(lp1_xy, lp2_xy)
        self.cog_obj = self.doc.addObject("Part::Sphere", self.name + "_COG")
        self.cog_obj.Radius = 500  # 0.5m
        self.cog_obj.Placement.Base = App.Vector(cog_xy[0], cog_xy[1], cz)
        self.cog_obj.ViewObject.ShapeColor = (1.0, 0.0, 0.0)  # Rot
        
        # Liftpunkte-Marker
        self._create_lift_point(lp1_xy, bottom_z + self.load_geom.height_mm, "LP1", (0, 1, 0))
        self._create_lift_point(lp2_xy, bottom_z + self.load_geom.height_mm, "LP2", (0, 0, 1))
        
        # Sling-Linien (Seile)
        self._create_sling_line(lp1_xy, bottom_z + self.load_geom.height_mm, "Sling1")
        self._create_sling_line(lp2_xy, bottom_z + self.load_geom.height_mm, "Sling2")
        
        self.doc.recompute()
        return box
        
    def _create_lift_point(self, xy, z, suffix, color):
        """Erstellt Marker für Liftpunkte."""
        obj = self.doc.addObject("Part::Sphere", f"{self.name}_{suffix}")
        obj.Radius = 300  # 0.3m
        obj.Placement.Base = App.Vector(xy[0], xy[1], z)
        obj.ViewObject.ShapeColor = color
        return obj
        
    def _create_sling_line(self, lp_xy, lp_z, suffix):
        """Erstellt Linie für Sling (wird später aktualisiert)."""
        line = self.doc.addObject("Part::Line", f"{self.name}_{suffix}")
        line.X1, line.Y1, line.Z1 = lp_xy[0], lp_xy[1], lp_z
        line.X2, line.Y2, line.Z2 = lp_xy[0], lp_xy[1], lp_z + 1000  # Platzhalter
        line.ViewObject.LineColor = (0.5, 0.5, 0.5)
        line.ViewObject.LineWidth = 3
        self.sling_lines.append(line)
        return line
        
    def update(self, lp1_xy, lp2_xy, bottom_z, tip1_xy, tip2_xy, tip_z):
        """Aktualisiert Position und Sling-Linien."""
        if not self.shape:
            return
            
        (cx, cy, cz), u, v = self.load_geom.get_world_transform(lp1_xy, lp2_xy, bottom_z)
        
        # Box positionieren
        self.shape.Placement.Base = App.Vector(
            cx - self.load_geom.length_mm/2 * u[0],
            cy - self.load_geom.length_mm/2 * u[1],
            bottom_z
        )
        angle = math.degrees(math.atan2(u[0], u[1]))
        self.shape.Placement.Rotation = App.Rotation(App.Vector(0, 0, 1), -angle)
        
        # COG aktualisieren
        cog_xy = self.load_geom.get_cog_xy(lp1_xy, lp2_xy)
        self.cog_obj.Placement.Base = App.Vector(cog_xy[0], cog_xy[1], cz)
        
        # Liftpunkte aktualisieren
        lp_z = bottom_z + self.load_geom.height_mm - self.load_geom.lp_height_from_top_mm
        for suffix, xy in [("LP1", lp1_xy), ("LP2", lp2_xy)]:
            obj = self.doc.getObject(f"{self.name}_{suffix}")
            if obj:
                obj.Placement.Base = App.Vector(xy[0], xy[1], lp_z)
                
        # Sling-Linien aktualisieren: Liftpunkt → Kran-Baumspitze
        for i, (lp_xy, tip_xy, suffix) in enumerate([
            (lp1_xy, tip1_xy, "Sling1"),
            (lp2_xy, tip2_xy, "Sling2")
        ]):
            line = self.sling_lines[i]
            line.X1, line.Y1, line.Z1 = lp_xy[0], lp_xy[1], lp_z
            line.X2, line.Y2, line.Z2 = tip_xy[0], tip_xy[1], tip_z
            
        self.doc.recompute()
        
    def set_collision_state(self, has_collision):
        """Färbt die Last je nach Kollisionsstatus."""
        if not self.shape:
            return
        if has_collision:
            self.shape.ViewObject.ShapeColor = (1.0, 0.2, 0.2)  # Rot
            self.shape.ViewObject.Transparency = 0
        else:
            self.shape.ViewObject.ShapeColor = (0.8, 0.6, 0.4)  # Normal
            self.shape.ViewObject.Transparency = 30
            
    def remove(self):
        """Löscht alle Visualisierungsobjekte."""
        names = [self.name, self.name + "_COG", self.name + "_LP1", 
                self.name + "_LP2", self.name + "_Sling1", self.name + "_Sling2"]
        for name in names:
            obj = self.doc.getObject(name)
            if obj:
                self.doc.removeObject(obj.Name)
        self.doc.recompute()


class SwingCirclesVisual:
    """Zeichnet die Drehkreise der Kräne in einer bestimmten Höhe."""
    
    def __init__(self, doc, crane_obj, name_suffix):
        self.doc = doc
        self.crane = crane_obj
        self.name = f"SwingCircle_{crane_obj.Name}_{name_suffix}"
        self.circle = None
        
    def create(self, height_mm, radius_mm=None):
        """Erstellt Kreis in Höhe z=height_mm."""
        if radius_mm is None:
            # Radius aus aktueller Auslage oder Boom-Länge
            radius_mm = float(self.crane.BoomLength)
            
        # Position des Krans
        cx = float(self.crane.Placement.Base.x)
        cy = float(self.crane.Placement.Base.y)
        
        # Kreis als Polygon mit 64 Segmenten
        circle = self.doc.addObject("Part::Polygon", self.name)
        points = []
        for i in range(65):
            angle = 2 * math.pi * i / 64
            x = cx - radius_mm * math.sin(angle)
            y = cy + radius_mm * math.cos(angle)
            points.append(App.Vector(x, y, height_mm))
            
        circle.Nodes = points
        circle.ViewObject.LineColor = (0.0, 0.8, 0.0)  # Grün
        circle.ViewObject.LineWidth = 2
        circle.ViewObject.PointSize = 0
        
        self.circle = circle
        self.doc.recompute()
        return circle
        
    def update_height(self, height_mm):
        """Aktualisiert die Höhe des Kreises."""
        if not self.circle:
            return
        nodes = []
        for p in self.circle.Nodes:
            nodes.append(App.Vector(p.x, p.y, height_mm))
        self.circle.Nodes = nodes
        self.doc.recompute()
        
    def remove(self):
        obj = self.doc.getObject(self.name)
        if obj:
            self.doc.removeObject(obj.Name)


# ---------------------------------------------------------------------------
# INTERAKTIVE SIMULATION
# ---------------------------------------------------------------------------

class InteractiveSwingSimulator:
    """Schritt-für-Schritt Simulator mit visuellem Feedback."""
    
    def __init__(self, crane_1_obj, crane_2_obj, load_geom, ship_geom):
        self.crane_1 = crane_1_obj
        self.crane_2 = crane_2_obj
        self.load_geom = load_geom
        self.ship_geom = ship_geom
        
        self.doc = App.activeDocument()
        self.load_vis = None
        self.circle_1 = None
        self.circle_2 = None
        
        # Simulation State
        self.steps = []
        self.current_step_idx = 0
        self.r1_mm = 0
        self.r2_mm = 0
        
        # Modifikationen (Was-wäre-wenn)
        self.list_angle_deg = 0.0  # Schlagseite
        self.lp1_offset_mm = 0     # Alternative Liftpunkt-Positionen
        self.lp2_offset_mm = 0
        
    def setup_visualization(self):
        """Erstellt die 3D-Visualisierung."""
        self.load_vis = LoadVisual(self.doc, self.load_geom)
        self.circle_1 = SwingCirclesVisual(self.doc, self.crane_1, "C1")
        self.circle_2 = SwingCirclesVisual(self.doc, self.crane_2, "C2")
        
    def compute_radii(self, total_weight_t, cog_to_lp1_m):
        """Berechnet Auslagen wie in MonopileSwing."""
        calc = TandemLiftCalculator()
        load_1, load_2, warnings = calc.calculate_from_lift_points(
            total_weight_t, cog_to_lp1_m,
            self.load_geom.lp_distance_mm / 1000.0
        )
        
        lift1 = SingleHookLift(self.crane_1)
        lift2 = SingleHookLift(self.crane_2)
        
        self.r1_mm, ok1, _ = lift1.calculate_optimal_radius(load_1)
        self.r2_mm, ok2, _ = lift2.calculate_optimal_radius(load_2)
        
        return self.r1_mm > 0 and self.r2_mm > 0
        
    def generate_steps(self, sea_dir_deg, land_dir_deg, n_steps):
        """Generiert die Schrittsequenz (ähnlich MonopileSwing.simulate)."""
        # Hier würde die Logik aus MonopileSwing übernommen werden
        # aber nur die Geometrie-Berechnung, nicht die automatische Ausführung
        pass
        
    def show_step(self, step_idx):
        """Zeigt einen bestimmten Schritt an."""
        if step_idx < 0 or step_idx >= len(self.steps):
            return False
            
        step = self.steps[step_idx]
        
        # Visualisierung aktualisieren
        if self.load_vis:
            self.load_vis.update(
                step.lp_1_xy, step.lp_2_xy, step.load_bottom_z,
                step.tip_1_xy, step.tip_2_xy, step.tip_z
            )
            has_collision = step.status in [SwingStep.STATUS_FAIL, SwingStep.STATUS_WARN]
            self.load_vis.set_collision_state(has_collision)
            
        # Drehkreise aktualisieren (in Höhe der Last)
        if self.circle_1 and self.circle_2:
            height = step.load_bottom_z + self.load_geom.height_mm / 2
            self.circle_1.update_height(height)
            self.circle_2.update_height(height)
            
        # Kräne positionieren
        self.crane_1.SlewAngle = step.slew_1
        self.crane_2.SlewAngle = step.slew_2
        
        self.doc.recompute()
        return True
        
    def apply_list_angle(self, angle_deg):
        """Simuliert Schlagseite durch Rotation des Schiffskoordinatensystems."""
        self.list_angle_deg = angle_deg
        # TODO: Alle Y-Koordinaten um cos(angle) skalieren, Z um sin(angle) verschieben
        pass
        
    def cleanup(self):
        """Entfernt alle Visualisierungsobjekte."""
        if self.load_vis:
            self.load_vis.remove()
        if self.circle_1:
            self.circle_1.remove()
        if self.circle_2:
            self.circle_2.remove()


# ---------------------------------------------------------------------------
# DIALOG
# ---------------------------------------------------------------------------

class InteractiveSwingDialog(QtGui.QDialog):
    
    def __init__(self, parent=None):
        super(InteractiveSwingDialog, self).__init__(parent)
        self.setWindowTitle("Interaktive Schwingsimulation")
        self.setMinimumWidth(700)
        self.setMinimumHeight(800)
        
        self.simulator = None
        self.setupUI()
        self.findCranes()
        
    def setupUI(self):
        layout = QtGui.QVBoxLayout()
        
        # ---- Setup-Panel (oben, einklappbar) ----
        setup_group = QtGui.QGroupBox("Setup")
        setup_layout = QtGui.QFormLayout()
        
        # Kräne
        self.crane_1_combo = QtGui.QComboBox()
        self.crane_2_combo = QtGui.QComboBox()
        setup_layout.addRow("Kran 1 (Heck):", self.crane_1_combo)
        setup_layout.addRow("Kran 2 (Bug):", self.crane_2_combo)
        
        # Last-Parameter (vereinfacht)
        def dspin(lo, hi, val, sfx, dec=0):
            w = QtGui.QDoubleSpinBox()
            w.setRange(lo, hi)
            w.setValue(val)
            w.setSuffix(sfx)
            w.setDecimals(dec)
            return w
            
        self.e_length = dspin(1000, 200000, 40000, " mm")
        self.e_width = dspin(100, 20000, 3000, " mm")
        self.e_height = dspin(100, 20000, 3000, " mm")
        self.e_lp_dist = dspin(100, 100000, 20000, " mm")
        self.e_weight = dspin(0.1, 5000, 200, " t", 1)
        
        setup_layout.addRow("Last Länge:", self.e_length)
        setup_layout.addRow("Last Breite:", self.e_width)
        setup_layout.addRow("Last Höhe:", self.e_height)
        setup_layout.addRow("Abstand LP1→LP2:", self.e_lp_dist)
        setup_layout.addRow("Gewicht:", self.e_weight)
        
        # Richtungen
        self.e_sea_dir = dspin(0, 359.9, 0, " °", 1)
        self.e_land_dir = dspin(0, 359.9, 180, " °", 1)
        self.e_steps = QtGui.QSpinBox()
        self.e_steps.setRange(5, 50)
        self.e_steps.setValue(15)
        
        setup_layout.addRow("See-Richtung:", self.e_sea_dir)
        setup_layout.addRow("Land-Richtung:", self.e_land_dir)
        setup_layout.addRow("Anzahl Schritte:", self.e_steps)
        
        # Init-Button
        self.init_btn = QtGui.QPushButton("Simulation initialisieren")
        self.init_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
        self.init_btn.clicked.connect(self.initializeSimulation)
        setup_layout.addRow("", self.init_btn)
        
        setup_group.setLayout(setup_layout)
        layout.addWidget(setup_group)
        
        # ---- Steuerung (Mitte) ----
        control_group = QtGui.QGroupBox("Schritt-für-Schritt Steuerung")
        control_layout = QtGui.QHBoxLayout()
        
        self.btn_prev = QtGui.QPushButton("◀ Vorheriger")
        self.btn_prev.setEnabled(False)
        self.btn_prev.clicked.connect(self.prevStep)
        
        self.lbl_step = QtGui.QLabel("Schritt: - / -")
        self.lbl_step.setAlignment(QtCore.Qt.AlignCenter)
        self.lbl_step.setStyleSheet("font-size: 14px; font-weight: bold;")
        
        self.btn_next = QtGui.QPushButton("Nächster ▶")
        self.btn_next.setEnabled(False)
        self.btn_next.setStyleSheet("background-color: #2196F3; color: white;")
        self.btn_next.clicked.connect(self.nextStep)
        
        control_layout.addWidget(self.btn_prev)
        control_layout.addWidget(self.lbl_step, 1)
        control_layout.addWidget(self.btn_next)
        
        # Status-Label
        self.lbl_status = QtGui.QLabel("Status: Nicht initialisiert")
        self.lbl_status.setAlignment(QtCore.Qt.AlignCenter)
        self.lbl_status.setStyleSheet("padding: 5px; border-radius: 3px;")
        
        control_vbox = QtGui.QVBoxLayout()
        control_vbox.addLayout(control_layout)
        control_vbox.addWidget(self.lbl_status)
        control_group.setLayout(control_vbox)
        layout.addWidget(control_group)
        
        # ---- Was-wäre-wenn Panel ----
        whatif_group = QtGui.QGroupBox("Was-wäre-wenn Anpassungen")
        whatif_layout = QtGui.QFormLayout()
        
        self.e_list_angle = dspin(-5, 5, 0, " °", 1)
        self.e_list_angle.setToolTip("Schlagseite positiv = Backbord höher")
        self.e_list_angle.valueChanged.connect(self.onListAngleChanged)
        
        self.btn_apply_list = QtGui.QPushButton("Schlagseite anwenden")
        self.btn_apply_list.setEnabled(False)
        self.btn_apply_list.clicked.connect(self.applyListAngle)
        
        list_row = QtGui.QHBoxLayout()
        list_row.addWidget(self.e_list_angle)
        list_row.addWidget(self.btn_apply_list)
        whatif_layout.addRow("Schlagseite:", list_row)
        
        # Alternative Liftpunkte
        self.e_lp1_shift = dspin(-5000, 5000, 0, " mm")
        self.e_lp2_shift = dspin(-5000, 5000, 0, " mm")
        whatif_layout.addRow("LP1 Verschiebung:", self.e_lp1_shift)
        whatif_layout.addRow("LP2 Verschiebung:", self.e_lp2_shift)
        
        self.btn_test_lp = QtGui.QPushButton("Alternative LP testen")
        self.btn_test_lp.setEnabled(False)
        self.btn_test_lp.clicked.connect(self.testAlternativeLP)
        whatif_layout.addRow("", self.btn_test_lp)
        
        whatif_group.setLayout(whatif_layout)
        layout.addWidget(whatif_group)
        
        # ---- Info-Panel ----
        info_group = QtGui.QGroupBox("Kollisions-Info")
        info_layout = QtGui.QVBoxLayout()
        
        self.info_text = QtGui.QTextEdit()
        self.info_text.setReadOnly(True)
        self.info_text.setMaximumHeight(150)
        self.info_text.setFont(QtGui.QFont("Courier", 9))
        info_layout.addWidget(self.info_text)
        
        info_group.setLayout(info_layout)
        layout.addWidget(info_group)
        
        # ---- Buttons ----
        btn_layout = QtGui.QHBoxLayout()
        self.btn_close = QtGui.QPushButton("Schließen")
        self.btn_close.clicked.connect(self.close)
        
        self.btn_cleanup = QtGui.QPushButton("Visualisierung löschen")
        self.btn_cleanup.clicked.connect(self.cleanup)
        
        btn_layout.addWidget(self.btn_cleanup)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_close)
        layout.addLayout(btn_layout)
        
        self.setLayout(layout)
        
    def findCranes(self):
        doc = App.activeDocument()
        if not doc:
            return
        cranes = [o for o in doc.Objects
                  if hasattr(o, "Proxy") and
                  getattr(o.Proxy, "Type", "") == "ShipCrane"]
        
        for combo in (self.crane_1_combo, self.crane_2_combo):
            combo.clear()
            combo.addItem("── wählen ──", None)
            for c in cranes:
                pos = c.Placement.Base
                combo.addItem(
                    f"{c.Label}  [{pos.x/1000:.1f}m, {pos.y/1000:.1f}m]",
                    c
                )
        if len(cranes) >= 2:
            self.crane_1_combo.setCurrentIndex(1)
            self.crane_2_combo.setCurrentIndex(2)
            
    def initializeSimulation(self):
        """Startet die Simulation."""
        c1 = self.crane_1_combo.currentData()
        c2 = self.crane_2_combo.currentData()
        
        if not c1 or not c2 or c1 is c2:
            QtGui.QMessageBox.warning(self, "Fehler", "Bitte zwei verschiedene Kräne wählen!")
            return
            
        # Last-Geometrie erstellen
        load = LoadGeometry(
            length_mm=self.e_length.value(),
            width_mm=self.e_width.value(),
            height_mm=self.e_height.value(),
            lp1_from_aft_mm=1000,  # Platzhalter, wird berechnet
            lp_distance_mm=self.e_lp_dist.value(),
            cog_from_lp1_mm=self.e_lp_dist.value() / 2,  # Mitte
            rigging_length_mm=8000,
        )
        
        # Schiffs-Geometrie (vereinfacht aus aktuellem Schiff oder Default)
        ship = ShipGeometry(
            length_mm=120000,
            width_mm=22000,
            freeboard_mm=15000,
        )
        
        # Simulator erstellen
        self.simulator = InteractiveSwingSimulator(c1, c2, load, ship)
        
        # Radien berechnen
        ok = self.simulator.compute_radii(
            self.e_weight.value(),
            load.cog_from_lp1_mm / 1000.0
        )
        
        if not ok:
            QtGui.QMessageBox.critical(self, "Fehler", "Kapazitätsgrenze überschritten!")
            return
            
        # Visualisierung initialisieren
        self.simulator.setup_visualization()
        
        # TODO: Schritte generieren (hier müsste die Logik aus MonopileSwing eingebaut werden)
        # Für Demo: Dummy-Schritte
        self.simulator.steps = self._generate_dummy_steps(c1, c2)
        
        if len(self.simulator.steps) == 0:
            QtGui.QMessageBox.warning(self, "Fehler", "Keine Lösung gefunden!")
            return
            
        self.current_step_idx = 0
        self.showCurrentStep()
        
        # Buttons aktivieren
        self.btn_next.setEnabled(True)
        self.btn_prev.setEnabled(True)
        self.btn_apply_list.setEnabled(True)
        self.btn_test_lp.setEnabled(True)
        
    def _generate_dummy_steps(self, c1, c2):
        """Platzhalter - hier müsste die echte Geometrie-Berechnung rein."""
        # TODO: Implementiere echte Schritt-Generierung aus MonopileSwing
        return []
        
    def showCurrentStep(self):
        """Zeigt aktuellen Schritt an."""
        if not self.simulator or not self.simulator.steps:
            return
            
        step = self.simulator.steps[self.current_step_idx]
        self.simulator.show_step(self.current_step_idx)
        
        self.lbl_step.setText(f"Schritt: {self.current_step_idx + 1} / {len(self.simulator.steps)}")
        
        # Status-Farbe
        colors = {
            SwingStep.STATUS_OK: ("#c8f7c5", "Kollisionsfrei"),
            SwingStep.STATUS_WARN: ("#fff3cd", "Warnung: Geringe Abstände"),
            SwingStep.STATUS_FAIL: ("#f8d7da", "KOLLISION!"),
        }
        bg, text = colors.get(step.status, ("#e2e3e5", "Unbekannt"))
        self.lbl_status.setStyleSheet(f"background-color: {bg}; padding: 5px;")
        self.lbl_status.setText(f"Status: {text}")
        
        # Info-Text
        info = [f"Schritt {self.current_step_idx + 1} von {len(self.simulator.steps)}"]
        info.append(f"Slew Kran 1: {step.slew_1:.1f}°")
        info.append(f"Slew Kran 2: {step.slew_2:.1f}°")
        
        if step.clearance_ship_hull is not None:
            info.append(f"Rumpf-Abstand: {step.clearance_ship_hull/1000:.2f}m")
        if step.clearance_deck is not None:
            info.append(f"Deck-Abstand: {step.clearance_deck/1000:.2f}m")
            
        for msg in step.messages:
            info.append(msg)
            
        self.info_text.setText("\n".join(info))
        
        # Buttons aktualisieren
        self.btn_prev.setEnabled(self.current_step_idx > 0)
        self.btn_next.setEnabled(self.current_step_idx < len(self.simulator.steps) - 1)
        
    def nextStep(self):
        if self.current_step_idx < len(self.simulator.steps) - 1:
            self.current_step_idx += 1
            self.showCurrentStep()
            
    def prevStep(self):
        if self.current_step_idx > 0:
            self.current_step_idx -= 1
            self.showCurrentStep()
            
    def onListAngleChanged(self, val):
        """Live-Vorschau der Schlagseite."""
        # TODO: Echtzeit-Update der Geometrie
        pass
        
    def applyListAngle(self):
        """Wendet Schlagseite an und regeneriert Schritte."""
        angle = self.e_list_angle.value()
        if self.simulator:
            self.simulator.apply_list_angle(angle)
            # Schritte neu berechnen
            self.simulator.steps = self._generate_dummy_steps(
                self.simulator.crane_1, self.simulator.crane_2
            )
            self.current_step_idx = 0
            self.showCurrentStep()
            
    def testAlternativeLP(self):
        """Testet alternative Liftpunkt-Positionen."""
        # TODO: Regeneriere mit verschobenen LP
        pass
        
    def cleanup(self):
        if self.simulator:
            self.simulator.cleanup()
            self.simulator = None
        self.lbl_step.setText("Schritt: - / -")
        self.lbl_status.setText("Status: Nicht initialisiert")
        self.lbl_status.setStyleSheet("padding: 5px;")
        self.btn_next.setEnabled(False)
        self.btn_prev.setEnabled(False)
        
    def closeEvent(self, event):
        self.cleanup()
        event.accept()


# ---------------------------------------------------------------------------
# EXTERNER AUFRUF
# ---------------------------------------------------------------------------

def show_interactive_swing():
    """Zeigt den interaktiven Dialog an."""
    dialog = InteractiveSwingDialog(Gui.getMainWindow())
    dialog.exec_()


__all__ = ['InteractiveSwingDialog', 'show_interactive_swing']
