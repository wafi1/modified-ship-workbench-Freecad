#***************************************************************************
#*                                                                         *
#*   TaskPanel_CreateCapytaineMesh.py                                      *
#*                                                                         *
#*   Tool zum Erstellen eines Capytaine-fähigen Boundary-Element-Meshes   *
#*   aus einem FreeCAD Ship-Shape.                                         *
#*                                                                         *
#*   Pipeline:                                                             *
#*     1. Ship-Shape auswählen                                             *
#*     2. Parameter setzen (Tiefgang, Deflection, Halbmodell)             *
#*     3. Shape auf Wasserlinie zuschneiden                                *
#*     4. Optional: Auf Steuerbordseite (Y≥0) reduzieren                  *
#*     5. Tessellieren → Mesh::Feature                                    *
#*     6. Qualitäts-Check (Wasserdichtigkeit, Orientierung)               *
#*     7. Als SeakeepingMesh am Ship-Objekt speichern                     *
#*                                                                         *
#*   GNU LGPL — see LICENCE text file for details.                        *
#*                                                                         *
#***************************************************************************

import os
import numpy as np
import FreeCAD as App
import FreeCADGui as Gui
from FreeCAD import Units, Vector
from PySide import QtGui, QtCore

try:
    import Part
    PART_AVAILABLE = True
except ImportError:
    PART_AVAILABLE = False

try:
    import MeshPart
    import Mesh as FcMesh
    MESHPART_AVAILABLE = True
except ImportError:
    MESHPART_AVAILABLE = False

try:
    import capytaine as cpt
    CAPYTAINE_AVAILABLE = True
except ImportError:
    CAPYTAINE_AVAILABLE = False

# ---------------------------------------------------------------------------
# Konstanten
# ---------------------------------------------------------------------------
RHO_SEAWATER   = 1025.0   # kg/m³
RHO_FRESHWATER = 1000.0   # kg/m³
G              = 9.81     # m/s²


# ===========================================================================
# Hilfsfunktionen (unabhängig vom TaskPanel nutzbar)
# ===========================================================================

def detect_unit_scale(shape):
    """Erkennt ob das Shape in mm oder m vorliegt.
    
    FreeCAD arbeitet intern in mm. Schiffe haben typisch Längen von
    10–500 m, was als mm-Wert 10.000–500.000 wäre.
    
    Returns
    -------
    scale : float
        Multiplikator um interne Einheit → Meter zu konvertieren.
        0.001 für mm-Shape, 1.0 für m-Shape.
    unit_str : str
        Lesbarer String 'mm' oder 'm'.
    """
    bbox = shape.BoundBox
    lpp  = bbox.XLength
    if lpp > 500:
        return 0.001, 'mm'
    else:
        return 1.0, 'm'


def cut_to_waterline(shape, draft_internal, margin_internal=5000.0):
    """Schneidet ein Shape auf die benetzte Fläche zu (z ≤ 0).
    
    Parameters
    ----------
    shape             : OCCT Shape (FreeCAD Part)
    draft_internal    : Tiefgang in interner Einheit (mm oder m)
    margin_internal   : Seitlicher Puffer für den Schnittquader
    
    Returns
    -------
    wetted_shape : OCCT Shape oder None
    """
    bbox = shape.BoundBox

    cut_box = Part.makeBox(
        bbox.XLength + 2 * margin_internal,
        bbox.YLength + 2 * margin_internal,
        draft_internal,
        Vector(
            bbox.XMin - margin_internal,
            bbox.YMin - margin_internal,
            bbox.ZMin
        )
    )
    try:
        wetted = shape.common(cut_box)
    except Exception as e:
        raise RuntimeError(f"Wasserlinienschnitt fehlgeschlagen: {e}")

    if wetted.isNull():
        raise RuntimeError(
            "Benetztes Shape ist leer.\n"
            "Mögliche Ursachen:\n"
            "  • Tiefgang zu gering (Shape liegt komplett über z=0)\n"
            "  • Shape-Koordinatensystem falsch (Z sollte nach oben zeigen)\n"
            "  • Shape nicht wasserdicht")
    return wetted


def cut_to_half_model(shape, margin_internal=5000.0):
    """Reduziert das Shape auf die Steuerbordseite (Y ≥ 0).
    
    Capytaine nutzt die xz-Spiegelsymmetrie automatisch wenn
    das Halbmodell übergeben wird.
    """
    bbox = shape.BoundBox

    half_box = Part.makeBox(
        bbox.XLength + 2 * margin_internal,
        abs(bbox.YMax) + margin_internal,
        abs(bbox.ZMin) + bbox.ZMax + 2 * margin_internal,
        Vector(
            bbox.XMin - margin_internal,
            0.0,
            bbox.ZMin - margin_internal
        )
    )
    try:
        half = shape.common(half_box)
    except Exception as e:
        App.Console.PrintWarning(
            f"Halbmodell-Schnitt fehlgeschlagen, verwende ganzes Modell: {e}\n")
        return shape

    if half.isNull():
        App.Console.PrintWarning(
            "Halbmodell-Schnitt ergab leeres Shape — ganzes Modell wird verwendet.\n")
        return shape

    return half


def tessellate_shape(shape, linear_defl_internal, angular_defl=0.05):
    """Tesselliert ein OCCT Shape zu einem FreeCAD Mesh.
    
    Parameters
    ----------
    shape                : OCCT Shape
    linear_defl_internal : Lineare Deflection in interner Einheit
    angular_defl         : Winkel-Deflection in Radiant
    
    Returns
    -------
    FreeCAD Mesh-Objekt
    """
    if not MESHPART_AVAILABLE:
        raise ImportError("MeshPart-Modul nicht verfügbar.")

    mesh = MeshPart.meshFromShape(
        Shape=shape,
        LinearDeflection=linear_defl_internal,
        AngularDeflection=angular_defl,
        Relative=False
    )

    if mesh.CountPoints == 0:
        raise RuntimeError(
            "Tessellierung ergab leeres Mesh.\n"
            "  → LinearDeflection verringern\n"
            "  → Shape-Geometrie prüfen")

    return mesh


def check_mesh_quality(mesh, scale_to_m):
    """Prüft die Mesh-Qualität für Capytaine-Eignung.
    
    Returns
    -------
    report : dict mit Feldern:
        ok            : bool — True wenn Mesh brauchbar
        n_points      : int
        n_faces       : int
        bbox_m        : tuple (xlen, ylen, zlen) in Metern
        warnings      : list of str
        errors        : list of str
    """
    report = {
        'ok':       True,
        'n_points': mesh.CountPoints,
        'n_faces':  mesh.CountFacets,
        'bbox_m':   (0, 0, 0),
        'warnings': [],
        'errors':   []
    }

    # Mindestgröße
    if mesh.CountPoints < 10:
        report['errors'].append(
            f"Zu wenige Knoten ({mesh.CountPoints}) — Shape prüfen.")
        report['ok'] = False

    if mesh.CountFacets < 6:
        report['errors'].append(
            f"Zu wenige Dreiecke ({mesh.CountFacets}) — Shape prüfen.")
        report['ok'] = False

    # Bounding Box
    bb = mesh.BoundBox
    xlen = bb.XLength * scale_to_m
    ylen = bb.YLength * scale_to_m
    zlen = bb.ZLength * scale_to_m
    report['bbox_m'] = (xlen, ylen, zlen)

    # Dimensionskontrolle
    if xlen < 0.1:
        report['warnings'].append(
            f"Sehr kurzes Mesh: Lpp={xlen:.3f} m — Einheit prüfen.")
    if xlen > 5000:
        report['warnings'].append(
            f"Sehr langes Mesh: Lpp={xlen:.0f} m — evtl. mm statt m.")

    # Ungültige Dreiecke prüfen
    try:
        n_degenerate = sum(
            1 for f in mesh.Facets
            if len(set(f.PointIndices)) < 3
        )
        if n_degenerate > 0:
            report['warnings'].append(
                f"{n_degenerate} degenerierte Dreiecke gefunden.")
    except Exception:
        pass

    # Empfehlung Panel-Anzahl
    if mesh.CountFacets < 100:
        report['warnings'].append(
            "Weniger als 100 Panels — Ergebnis wird sehr ungenau sein.")
    elif mesh.CountFacets > 50000:
        report['warnings'].append(
            "Mehr als 50.000 Panels — Simulation wird sehr langsam sein.")

    return report


def build_capytaine_body(mesh_obj, ship_label, use_symmetry=True):
    """Konvertiert ein FreeCAD Mesh::Feature zu einem Capytaine FloatingBody.
    
    Parameters
    ----------
    mesh_obj     : FreeCAD Mesh::Feature
    ship_label   : Name für den FloatingBody
    use_symmetry : True = Halbmodell mit xz-Symmetrie
    
    Returns
    -------
    cpt.FloatingBody oder None wenn Capytaine nicht verfügbar
    """
    if not CAPYTAINE_AVAILABLE:
        App.Console.PrintWarning(
            "Capytaine nicht installiert — "
            "FloatingBody kann nicht erstellt werden.\n")
        return None

    # Einheit ermitteln
    bb = mesh_obj.Mesh.BoundBox
    scale = 0.001 if bb.XLength > 500 else 1.0

    verts = np.array(
        [[p.x * scale, p.y * scale, p.z * scale]
         for p in mesh_obj.Mesh.Points],
        dtype=float
    )
    faces = np.array(
        [list(f.PointIndices) for f in mesh_obj.Mesh.Facets],
        dtype=int
    )

    cpt_mesh = cpt.Mesh(vertices=verts, faces=faces, name=ship_label)
    cpt_mesh = cpt_mesh.healed()

    if use_symmetry:
        body = cpt.FloatingBody(
            mesh=cpt_mesh,
            name=ship_label,
            center_of_mass=np.array([0.0, 0.0, 0.0])
        )
    else:
        body = cpt.FloatingBody(mesh=cpt_mesh, name=ship_label)

    # An freier Oberfläche beschneiden (Capytaine-intern)
    body.keep_immersed_part()

    return body


# ===========================================================================
# TaskPanel
# ===========================================================================

class TaskPanel:
    def __init__(self):
        self.name       = "Create Capytaine Mesh"
        self.ship       = None
        self.ships      = []
        self.mesh_obj   = None    # Erzeugtes Mesh::Feature
        self.cpt_body   = None    # Capytaine FloatingBody (optional)
        self._result_report = {}

        # UI laden
        try:
            ui_path   = os.path.join(
                os.path.dirname(__file__), "..", "resources", "ui",
                "TaskPanel_CreateCapytaineMesh.ui")
            self.form = Gui.PySideUic.loadUi(ui_path)
            self._fallback_ui = False
        except Exception:
            self.form = self._create_ui()
            self._fallback_ui = True

    # ------------------------------------------------------------------
    # UI aufbauen
    # ------------------------------------------------------------------

    def _create_ui(self):
        """Vollständiges dynamisches UI."""
        widget = QtGui.QWidget()
        widget.setObjectName("CapytaineMeshPanel")
        main_layout = QtGui.QVBoxLayout()
        widget.setLayout(main_layout)

        # --- Titel ---
        title = QtGui.QLabel("CREATE CAPYTAINE HULL MESH")
        title.setAlignment(QtCore.Qt.AlignCenter)
        title.setStyleSheet(
            "font-weight: bold; font-size: 13px; "
            "padding: 6px; background: #1a3a5c; color: white; "
            "border-radius: 4px;")
        main_layout.addWidget(title)
        main_layout.addSpacing(8)

        # --- Schiff auswählen ---
        grp_ship = QtGui.QGroupBox("1 — Ship Object")
        ship_layout = QtGui.QFormLayout()
        grp_ship.setLayout(ship_layout)

        self._ship_combo = QtGui.QComboBox()
        self._ship_combo.currentIndexChanged.connect(self._on_ship_changed)
        ship_layout.addRow("Ship:", self._ship_combo)

        self._ship_info = QtGui.QLabel("—")
        self._ship_info.setStyleSheet("color: gray; font-size: 10px;")
        ship_layout.addRow("Info:", self._ship_info)

        main_layout.addWidget(grp_ship)

        # --- Tiefgang ---
        grp_draft = QtGui.QGroupBox("2 — Draft && Water")
        draft_layout = QtGui.QFormLayout()
        grp_draft.setLayout(draft_layout)

        self._draft_spin = QtGui.QDoubleSpinBox()
        self._draft_spin.setDecimals(3)
        self._draft_spin.setMinimum(0.001)
        self._draft_spin.setMaximum(50.0)
        self._draft_spin.setSingleStep(0.1)
        self._draft_spin.setValue(5.0)
        self._draft_spin.setSuffix(" m")
        draft_layout.addRow("Design Draft:", self._draft_spin)

        self._rho_combo = QtGui.QComboBox()
        self._rho_combo.addItem("Seawater  (1025 kg/m³)", 1025.0)
        self._rho_combo.addItem("Freshwater (1000 kg/m³)", 1000.0)
        draft_layout.addRow("Water Density:", self._rho_combo)

        main_layout.addWidget(grp_draft)

        # --- Mesh-Einstellungen ---
        grp_mesh = QtGui.QGroupBox("3 — Mesh Settings")
        mesh_layout = QtGui.QFormLayout()
        grp_mesh.setLayout(mesh_layout)

        self._defl_spin = QtGui.QDoubleSpinBox()
        self._defl_spin.setDecimals(3)
        self._defl_spin.setMinimum(0.001)
        self._defl_spin.setMaximum(5.0)
        self._defl_spin.setSingleStep(0.01)
        self._defl_spin.setValue(0.05)
        self._defl_spin.setSuffix(" m")
        self._defl_spin.setToolTip(
            "Kleinere Werte = feineres Mesh = langsamere Simulation\n"
            "Empfehlung: 0.02–0.10 m für Seakeeping")
        mesh_layout.addRow("Linear Deflection:", self._defl_spin)

        self._ang_spin = QtGui.QDoubleSpinBox()
        self._ang_spin.setDecimals(3)
        self._ang_spin.setMinimum(0.01)
        self._ang_spin.setMaximum(1.0)
        self._ang_spin.setSingleStep(0.01)
        self._ang_spin.setValue(0.05)
        self._ang_spin.setSuffix(" rad")
        mesh_layout.addRow("Angular Deflection:", self._ang_spin)

        self._half_model_chk = QtGui.QCheckBox(
            "Half model (port/starboard symmetry)")
        self._half_model_chk.setChecked(True)
        self._half_model_chk.setToolTip(
            "Nur Steuerbordseite (Y≥0) — Capytaine nutzt xz-Symmetrie automatisch.\n"
            "Halbiert die Rechenzeit.")
        mesh_layout.addRow("", self._half_model_chk)

        self._keep_immersed_chk = QtGui.QCheckBox(
            "keep_immersed_part (Capytaine)")
        self._keep_immersed_chk.setChecked(True)
        self._keep_immersed_chk.setToolTip(
            "Capytaine beschneidet das Mesh intern nochmals an z=0.\n"
            "Empfohlen: immer aktiviert lassen.")
        mesh_layout.addRow("", self._keep_immersed_chk)

        main_layout.addWidget(grp_mesh)

        # --- Panel-Schätzung ---
        grp_est = QtGui.QGroupBox("4 — Estimated Panel Count")
        est_layout = QtGui.QHBoxLayout()
        grp_est.setLayout(est_layout)

        self._est_label = QtGui.QLabel("— ")
        self._est_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        est_layout.addWidget(self._est_label)

        est_btn = QtGui.QPushButton("Estimate")
        est_btn.clicked.connect(self._estimate_panels)
        est_layout.addWidget(est_btn)

        main_layout.addWidget(grp_est)

        # --- Ergebnis ---
        grp_result = QtGui.QGroupBox("5 — Result")
        result_layout = QtGui.QVBoxLayout()
        grp_result.setLayout(result_layout)

        self._result_text = QtGui.QTextEdit()
        self._result_text.setReadOnly(True)
        self._result_text.setMaximumHeight(130)
        self._result_text.setStyleSheet("font-family: monospace; font-size: 10px;")
        self._result_text.setPlaceholderText(
            "Mesh-Ergebnis und Qualitäts-Check erscheinen hier...")
        result_layout.addWidget(self._result_text)

        main_layout.addWidget(grp_result)

        # Verbinde Deflection-Änderung mit Schätzung
        self._defl_spin.valueChanged.connect(self._update_estimate_label)
        self._half_model_chk.toggled.connect(self._update_estimate_label)

        return widget

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_ship_changed(self, idx):
        """Aktualisiert Ship-Info wenn anderes Schiff gewählt."""
        if 0 <= idx < len(self.ships):
            self.ship = self.ships[idx]
            self._update_ship_info()
            self._update_estimate_label()

    def _update_ship_info(self):
        """Zeigt Abmessungen des gewählten Schiffs."""
        if self.ship is None or not hasattr(self._ship_info, 'setText'):
            return
        try:
            shape  = self.ship.Shape
            scale, unit = detect_unit_scale(shape)
            bb = shape.BoundBox
            lpp = bb.XLength * scale
            b   = bb.YLength * scale
            d   = bb.ZLength * scale
            self._ship_info.setText(
                f"Lpp≈{lpp:.1f}m  B≈{b:.1f}m  D≈{d:.1f}m  (unit:{unit})")
            # Tiefgang vorschlagen: 55% der Gesamthöhe
            suggested_draft = d * 0.55
            self._draft_spin.setValue(round(suggested_draft, 2))
        except Exception:
            self._ship_info.setText("Shape nicht lesbar")

    def _estimate_panels(self):
        """Schätzt Panel-Anzahl ohne vollständige Tessellierung."""
        if self.ship is None:
            return
        try:
            shape = self.ship.Shape
            scale, _ = detect_unit_scale(shape)
            bb   = shape.BoundBox
            lpp  = bb.XLength * scale
            b    = bb.YLength * scale
            defl = self._defl_spin.value()

            # Benetzte Oberfläche grob schätzen
            # Für ein Schiff: ca. 2 × (L×T + B×T + 0.5×B×L×Cb)
            t    = self._draft_spin.value()
            cb   = 0.7   # Block-Koeffizient Schätzwert
            area = 2 * (lpp * t + b * t) + lpp * b * cb

            if self._half_model_chk.isChecked():
                area /= 2

            # Dreiecke: ca. 2 × (area / defl²)
            n_tri = int(2 * area / (defl ** 2))
            self._est_label.setText(f"~{n_tri:,} panels")
            self._update_estimate_label()
        except Exception as e:
            self._est_label.setText(f"Fehler: {e}")

    def _update_estimate_label(self):
        """Passt Farbe der Schätzung je nach Panel-Anzahl an."""
        if not hasattr(self, '_est_label'):
            return
        text = self._est_label.text()
        try:
            n = int(text.replace('~', '').replace(',', '').split()[0])
            if n < 200:
                color = "orange"
            elif n > 30000:
                color = "red"
            else:
                color = "green"
            self._est_label.setStyleSheet(
                f"font-weight: bold; font-size: 12px; color: {color};")
        except Exception:
            pass

    def _log(self, text, level='info'):
        """Schreibt in das Result-Textfeld und die FreeCAD-Konsole."""
        if hasattr(self, '_result_text'):
            current = self._result_text.toPlainText()
            self._result_text.setPlainText(current + text + "\n")
            # Scroll to bottom
            sb = self._result_text.verticalScrollBar()
            sb.setValue(sb.maximum())

        if level == 'error':
            App.Console.PrintError(text + "\n")
        elif level == 'warning':
            App.Console.PrintWarning(text + "\n")
        else:
            App.Console.PrintMessage(text + "\n")

    # ------------------------------------------------------------------
    # Kern: Mesh erstellen
    # ------------------------------------------------------------------

    def _run_mesh_creation(self):
        """Führt die komplette Mesh-Pipeline aus.
        
        Returns True bei Erfolg, False bei Fehler.
        """
        if self.ship is None:
            self._log("FEHLER: Kein Ship-Objekt ausgewählt.", 'error')
            return False

        if not PART_AVAILABLE or not MESHPART_AVAILABLE:
            self._log("FEHLER: Part oder MeshPart Modul nicht verfügbar.", 'error')
            return False

        shape = self.ship.Shape
        if not hasattr(shape, 'BoundBox') or shape.isNull():
            self._log("FEHLER: Ship hat kein gültiges Shape.", 'error')
            return False

        # Parameter lesen
        draft_m     = self._draft_spin.value()
        defl_m      = self._defl_spin.value()
        ang_defl    = self._ang_spin.value()
        half_model  = self._half_model_chk.isChecked()

        scale, unit = detect_unit_scale(shape)
        draft_int   = draft_m / scale
        defl_int    = defl_m  / scale
        margin_int  = 50.0    / scale    # 50 m Puffer

        self._log("=" * 50)
        self._log(f"CAPYTAINE MESH CREATION")
        self._log(f"Ship    : {self.ship.Label}")
        self._log(f"Unit    : {unit} (scale={scale})")
        self._log(f"Draft   : {draft_m} m")
        self._log(f"Defl    : {defl_m} m | AngDefl: {ang_defl} rad")
        self._log(f"Half    : {half_model}")
        self._log("-" * 50)

        # --- Schritt 1: Wasserlinienschnitt ---
        self._log("Schritt 1: Zuschnitt auf Wasserlinie...")
        try:
            wetted = cut_to_waterline(shape, draft_int, margin_int)
            self._log(f"  OK — benetztes Shape erstellt")
        except Exception as e:
            self._log(f"  FEHLER: {e}", 'error')
            return False

        # --- Schritt 2: Halbmodell ---
        if half_model:
            self._log("Schritt 2: Halbmodell (Steuerbord Y≥0)...")
            try:
                proc_shape = cut_to_half_model(wetted, margin_int)
                self._log("  OK — Halbmodell erstellt")
            except Exception as e:
                self._log(f"  WARNUNG: {e} — ganzes Modell wird verwendet", 'warning')
                proc_shape = wetted
        else:
            proc_shape = wetted
            self._log("Schritt 2: Ganzes Modell (keine Symmetrie)")

        # --- Schritt 3: Tessellierung ---
        self._log("Schritt 3: Tessellierung...")
        try:
            raw_mesh = tessellate_shape(proc_shape, defl_int, ang_defl)
            self._log(
                f"  OK — {raw_mesh.CountPoints:,} Knoten, "
                f"{raw_mesh.CountFacets:,} Dreiecke")
        except Exception as e:
            self._log(f"  FEHLER: {e}", 'error')
            return False

        # --- Schritt 4: Qualitäts-Check ---
        self._log("Schritt 4: Qualitäts-Check...")
        report = check_mesh_quality(raw_mesh, scale)
        self._result_report = report

        xlen, ylen, zlen = report['bbox_m']
        self._log(
            f"  BBox: {xlen:.2f} × {ylen:.2f} × {zlen:.2f} m")

        for w in report['warnings']:
            self._log(f"  WARNUNG: {w}", 'warning')
        for e in report['errors']:
            self._log(f"  FEHLER:  {e}", 'error')

        if not report['ok']:
            self._log("Mesh-Qualität nicht ausreichend — Abbruch.", 'error')
            return False

        # --- Schritt 5: FreeCAD Mesh::Feature anlegen ---
        self._log("Schritt 5: Mesh-Objekt im Dokument anlegen...")
        doc       = App.ActiveDocument
        mesh_name = f"{self.ship.Label}_CapytaineMesh"

        # Altes Mesh mit gleichem Namen entfernen
        old = doc.getObject(mesh_name)
        if old is not None:
            doc.removeObject(mesh_name)
            self._log(f"  Altes Mesh '{mesh_name}' entfernt")

        self.mesh_obj        = doc.addObject("Mesh::Feature", mesh_name)
        self.mesh_obj.Mesh   = raw_mesh
        self.mesh_obj.Label  = (
            f"{self.ship.Label} Capytaine Mesh "
            f"({'half' if half_model else 'full'}, "
            f"T={draft_m}m, d={defl_m}m)"
        )
        doc.recompute()
        self._log(f"  OK — '{self.mesh_obj.Label}'")

        # --- Schritt 6: SeakeepingMesh-Property am Ship setzen ---
        self._log("Schritt 6: Mesh dem Ship zuordnen...")
        try:
            if 'SeakeepingMesh' not in self.ship.PropertiesList:
                self.ship.addProperty(
                    "App::PropertyLinkList",
                    "SeakeepingMesh",
                    "Seakeeping",
                    "Hull mesh for seakeeping / Capytaine BEM analysis"
                )
            self.ship.SeakeepingMesh = [self.mesh_obj]
            self._log(
                f"  OK — '{self.mesh_obj.Label}' → '{self.ship.Label}'")
        except Exception as e:
            self._log(
                f"  WARNUNG: Mesh konnte nicht zugeordnet werden: {e}",
                'warning')

        # --- Schritt 7: Optional Capytaine FloatingBody testen ---
        if CAPYTAINE_AVAILABLE and self._keep_immersed_chk.isChecked():
            self._log("Schritt 7: Capytaine FloatingBody Test...")
            try:
                body = build_capytaine_body(
                    self.mesh_obj,
                    self.ship.Label,
                    use_symmetry=half_model
                )
                if body is not None:
                    self.cpt_body = body
                    self._log(
                        f"  OK — FloatingBody: "
                        f"{body.mesh.nb_vertices} Knoten nach healed()")
                else:
                    self._log("  Capytaine nicht verfügbar — übersprungen")
            except Exception as e:
                self._log(
                    f"  WARNUNG: Capytaine-Test fehlgeschlagen: {e}",
                    'warning')
        else:
            self._log("Schritt 7: Capytaine-Test übersprungen")

        self._log("=" * 50)
        self._log(
            f"FERTIG — Mesh '{self.mesh_obj.Label}' bereit für Capytaine")

        # Mesh im 3D-Fenster anzeigen
        try:
            self.mesh_obj.Visibility = True
            self.ship.Visibility     = False
        except Exception:
            pass

        return True

    # ------------------------------------------------------------------
    # TaskPanel Interface
    # ------------------------------------------------------------------

    def accept(self):
        """Mesh erstellen und Dialog schließen."""
        success = self._run_mesh_creation()
        if success:
            App.ActiveDocument.recompute()
        return success

    def reject(self):
        return True

    def clicked(self, index):
        pass

    def open(self):
        pass

    def needsFullSpace(self):
        return True

    def isAllowedAlterSelection(self):
        return False

    def isAllowedAlterView(self):
        return True

    def isAllowedAlterDocument(self):
        return True   # Wir legen Mesh::Feature an

    def helpRequested(self):
        pass

    def setupUi(self):
        if self.initValues():
            return True
        return False

    def initValues(self):
        """Startwerte: alle Ship-Objekte im Dokument laden."""
        doc = App.ActiveDocument
        if doc is None:
            App.Console.PrintError("Kein aktives FreeCAD-Dokument.\n")
            return True

        # Ships suchen
        self.ships = []
        for obj in doc.Objects:
            # Ship-Objekte erkennen: haben typisch Shape + Ship-Properties
            if hasattr(obj, 'Shape') and not obj.Shape.isNull():
                if (hasattr(obj, 'Length') or
                        hasattr(obj, 'Beam')   or
                        'Ship' in obj.TypeId   or
                        'ship' in obj.Label.lower()):
                    self.ships.append(obj)

        # Fallback: alle Objekte mit Shape
        if not self.ships:
            for obj in doc.Objects:
                if (hasattr(obj, 'Shape') and
                        not obj.Shape.isNull() and
                        'Mesh' not in obj.TypeId):
                    self.ships.append(obj)

        if not self.ships:
            App.Console.PrintError(
                "Keine Ship-Objekte mit Shape im Dokument gefunden.\n")
            return True

        # Combo befüllen
        if hasattr(self, '_ship_combo'):
            self._ship_combo.blockSignals(True)
            self._ship_combo.clear()
            for ship in self.ships:
                self._ship_combo.addItem(ship.Label)
            self._ship_combo.setCurrentIndex(0)
            self._ship_combo.blockSignals(False)

        # Erstes Schiff aktivieren
        self.ship = self.ships[0]
        self._update_ship_info()
        self._update_estimate_label()

        App.Console.PrintMessage(
            f"Capytaine Mesh Tool: {len(self.ships)} Ship(s) gefunden.\n")
        return False


# ===========================================================================
# Entry Point
# ===========================================================================

def createTask():
    try:
        panel = TaskPanel()
        Gui.Control.showDialog(panel)
        if panel.setupUi():
            Gui.Control.closeDialog()
            return None
        return panel
    except Exception as e:
        App.Console.PrintError(
            f"Fehler beim Erstellen des Capytaine Mesh Tools: {e}\n")
        import traceback
        traceback.print_exc()
        return None
