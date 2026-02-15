#***************************************************************************
#*   TaskPanel.py - VOLLSTÄNDIG: Beispielschiffe + Alle Formate            *
#***************************************************************************

import os
import FreeCAD as App
import FreeCADGui as Gui
from FreeCAD import Units
from PySide import QtGui, QtCore
from . import Tools
from .. import Instance
from ..shipUtils import Locale
from ..shipUtils import Selection
from ..shipUtils import Paths

from .GeometryConverter import GeometryConverter

import Mesh
import Points
import Part


class TaskPanel:
    def __init__(self):
        self.name = "ship creation"
        self.form = self.create_ui()
        self.imported_geometry = None
        self.converted_solid = None
        self.geometry_type = None
        self.example_ship = None
        self.original_bbox = None
        self.detected_unit = "m"
        self.scale_factor = 1.0
        
        self.real_length_m = 100.0
        self.real_breadth_m = 16.0
        self.real_depth_m = 12.0
        
        self.ensure_document()
        
    def ensure_document(self):
        if not App.ActiveDocument:
            App.newDocument("ShipDesign")
            App.Console.PrintMessage("✓ Neues Dokument erstellt\n")
    
    def get_document(self):
        self.ensure_document()
        return App.ActiveDocument
        
    def create_ui(self):
        form = QtGui.QWidget()
        main_layout = QtGui.QVBoxLayout()
        main_layout.setSpacing(10)
        
        # GEOMETRIE-QUELLE
        source_group = QtGui.QGroupBox("Geometrie-Quelle")
        source_layout = QtGui.QVBoxLayout()
        
        self.radio_example = QtGui.QRadioButton("Beispielschiff verwenden")
        self.radio_import = QtGui.QRadioButton("Geometrie importieren")
        self.radio_selected = QtGui.QRadioButton("Ausgewähltes Objekt verwenden")
        
        self.radio_import.setChecked(True)
        
        self.radio_example.toggled.connect(self.on_source_changed)
        self.radio_import.toggled.connect(self.on_source_changed)
        self.radio_selected.toggled.connect(self.on_source_changed)
        
        source_layout.addWidget(self.radio_example)
        source_layout.addWidget(self.radio_import)
        source_layout.addWidget(self.radio_selected)
        
        source_group.setLayout(source_layout)
        main_layout.addWidget(source_group)
        
        # EINHEITEN & KOORDINATEN
        unit_group = QtGui.QGroupBox("Einheiten & Koordinatensystem")
        unit_layout = QtGui.QVBoxLayout()
        
        self.unit_combo = QtGui.QComboBox()
        self.unit_combo.addItems([
            "Auto (empfohlen)",
            "Millimeter (mm)",
            "Meter (m)",
        ])
        self.unit_combo.currentIndexChanged.connect(self.on_unit_changed)
        
        unit_layout.addWidget(QtGui.QLabel("Einheit der importierten Datei:"))
        unit_layout.addWidget(self.unit_combo)
        
        self.unit_info = QtGui.QLabel("")
        self.unit_info.setWordWrap(True)
        self.unit_info.setStyleSheet("color: #666; font-size: 10px;")
        unit_layout.addWidget(self.unit_info)
        
        self.auto_center = QtGui.QCheckBox("Automatisch auf L/2 zentrieren")
        self.auto_center.setChecked(True)
        unit_layout.addWidget(self.auto_center)
        
        self.coord_info = QtGui.QLabel(
            "<small><i>FreeCAD Ship: Mitte bei X=0</i></small>")
        self.coord_info.setWordWrap(True)
        unit_layout.addWidget(self.coord_info)
        
        unit_group.setLayout(unit_layout)
        main_layout.addWidget(unit_group)
        
        # BEISPIELSCHIFF
        self.example_widget = QtGui.QWidget()
        example_layout = QtGui.QVBoxLayout()
        example_layout.setContentsMargins(20, 5, 5, 5)
        
        self.example_combo = QtGui.QComboBox()
        self.example_combo.addItems([
            "Series 60 (Slender)",
            "Wigley Hull (Canonical)",
            "Series 60 (Block)",
            "Wigley (Catamaran)"
        ])
        self.example_combo.currentIndexChanged.connect(self.on_example_changed)
        
        example_layout.addWidget(QtGui.QLabel("Beispielschiff:"))
        example_layout.addWidget(self.example_combo)
        
        example_info = QtGui.QLabel(
            "<small><i>Lädt Original FreeCAD Beispielschiff</i></small>")
        example_info.setWordWrap(True)
        example_layout.addWidget(example_info)
        
        self.example_widget.setLayout(example_layout)
        self.example_widget.setVisible(False)
        main_layout.addWidget(self.example_widget)
        
        # IMPORT
        self.import_widget = QtGui.QWidget()
        import_layout = QtGui.QVBoxLayout()
        import_layout.setContentsMargins(20, 5, 5, 5)
        
        self.import_button = QtGui.QPushButton("📁 Datei wählen...")
        self.import_button.setMinimumHeight(40)
        self.import_button.clicked.connect(self.import_geometry)
        
        self.import_status = QtGui.QLabel("<i>Keine Datei gewählt</i>")
        self.import_status.setWordWrap(True)
        
        format_info = QtGui.QLabel(
            "<small>Formate: STL, IGES, STEP, GF/GF1 Punktwolken</small>")
        format_info.setStyleSheet("color: #666;")
        
        import_layout.addWidget(format_info)
        import_layout.addWidget(self.import_button)
        import_layout.addWidget(self.import_status)
        
        self.import_widget.setLayout(import_layout)
        self.import_widget.setVisible(True)
        main_layout.addWidget(self.import_widget)
        
        # AUSGEWÄHLTES OBJEKT
        self.selected_widget = QtGui.QWidget()
        selected_layout = QtGui.QVBoxLayout()
        selected_layout.setContentsMargins(20, 5, 5, 5)
        
        self.selected_info = QtGui.QLabel()
        self.selected_refresh = QtGui.QPushButton("🔄 Aktualisieren")
        self.selected_refresh.clicked.connect(self.refresh_selection)
        
        selected_layout.addWidget(self.selected_info)
        selected_layout.addWidget(self.selected_refresh)
        
        self.selected_widget.setLayout(selected_layout)
        self.selected_widget.setVisible(False)
        main_layout.addWidget(self.selected_widget)
        
        # DIMENSIONEN
        dim_group = QtGui.QGroupBox("Schiffsdimensionen (in Metern)")
        dim_layout = QtGui.QGridLayout()
        
        dim_layout.addWidget(QtGui.QLabel("Länge (L):"), 0, 0)
        self.length_input = Gui.UiLoader().createWidget("Gui::InputField")
        self.length_input.setProperty("unit", "m")
        self.length_input.setText("100.0 m")
        self.length_input.textChanged.connect(self.on_dimension_changed)
        dim_layout.addWidget(self.length_input, 0, 1)
        
        dim_layout.addWidget(QtGui.QLabel("Breite (B):"), 1, 0)
        self.breadth_input = Gui.UiLoader().createWidget("Gui::InputField")
        self.breadth_input.setProperty("unit", "m")
        self.breadth_input.setText("16.0 m")
        self.breadth_input.textChanged.connect(self.on_dimension_changed)
        dim_layout.addWidget(self.breadth_input, 1, 1)
        
        dim_layout.addWidget(QtGui.QLabel("Tiefgang (T):"), 2, 0)
        self.draft_input = Gui.UiLoader().createWidget("Gui::InputField")
        self.draft_input.setProperty("unit", "m")
        self.draft_input.setText("6.0 m")
        self.draft_input.textChanged.connect(self.on_dimension_changed)
        dim_layout.addWidget(self.draft_input, 2, 1)
        
        dim_group.setLayout(dim_layout)
        main_layout.addWidget(dim_group)
        
        main_layout.addStretch()
        
        form.setLayout(main_layout)
        form.setMinimumWidth(450)
        
        self.refresh_selection()
        
        return form
    
    def on_source_changed(self):
        self.example_widget.setVisible(self.radio_example.isChecked())
        self.import_widget.setVisible(self.radio_import.isChecked())
        self.selected_widget.setVisible(self.radio_selected.isChecked())
        
        if self.radio_example.isChecked():
            self.on_example_changed()
    
    def on_example_changed(self):
        """Lädt Beispielschiff-Dimensionen"""
        if not self.radio_example.isChecked():
            return
        
        example = self.example_combo.currentIndex()
        # Dimensionen der Original-Beispielschiffe
        dimensions = [
            (25.5, 3.5, 1.0),   # Series 60 Slender
            (4.0, 0.8, 0.4),    # Wigley (klein!)
            (25.5, 3.5, 1.0),   # Series 60 Block
            (4.0, 0.8, 0.4),    # Wigley Katamaran
        ]
        
        L, B, T = dimensions[example]
        self.length_input.setText(f"{L} m")
        self.breadth_input.setText(f"{B} m")
        self.draft_input.setText(f"{T} m")
    
    def on_unit_changed(self, index):
        if self.original_bbox:
            self.recalculate_dimensions()
    
    def on_dimension_changed(self):
        try:
            length_text = self.length_input.text()
            breadth_text = self.breadth_input.text()
            draft_text = self.draft_input.text()
            
            self.real_length_m = self._parse_length(length_text)
            self.real_breadth_m = self._parse_length(breadth_text)
            self.real_depth_m = self._parse_length(draft_text) * 2
            
        except Exception as e:
            pass
    
    def _parse_length(self, text):
        if not text:
            return 0.0
        
        text = text.strip()
        
        try:
            if 'm' in text.lower():
                return float(text.lower().replace('m', '').strip())
            else:
                return float(text)
        except ValueError:
            pass
        
        try:
            quantity = Units.parseQuantity(text)
            return quantity.Value
        except:
            pass
        
        try:
            return Locale.fromString(text)
        except:
            pass
        
        return 0.0
    
    def detect_units(self, bbox):
        """Erkennt Einheiten"""
        length = bbox.XMax - bbox.XMin
        breadth = bbox.YMax - bbox.YMin
        
        App.Console.PrintMessage(f"    Roh-Maße: L={length:.6f}, B={breadth:.6f}\n")
        
        unit_idx = self.unit_combo.currentIndex()
        
        if unit_idx == 1:
            App.Console.PrintMessage("    → Manuell: MILLIMETER\n")
            return "mm", 1000.0
        
        elif unit_idx == 2:
            App.Console.PrintMessage("    → Manuell: METER\n")
            return "m", 1.0
        
        # Auto-Erkennung
        if 1.0 <= length <= 1000.0 and 0.1 <= breadth <= 100.0:
            ratio = length / breadth if breadth > 0 else 0
            if 2.0 < ratio < 20.0:
                App.Console.PrintMessage(f"    → Auto: METER (L={length:.1f}m, L/B={ratio:.1f})\n")
                return "m", 1.0
        
        if length > 10000:
            App.Console.PrintMessage(f"    → Auto: MILLIMETER (L={length:.0f} > 10000)\n")
            return "mm", 1000.0
        
        if length < 0.1:
            App.Console.PrintMessage(f"    → Auto: METER (L={length:.3f} < 0.1)\n")
            return "m", 1.0
        
        App.Console.PrintMessage(f"    → Auto: METER (Default)\n")
        return "m", 1.0
    
    def recalculate_dimensions(self):
        if not self.original_bbox:
            return
        
        einheit, scale = self.detect_units(self.original_bbox)
        
        if einheit == "m":
            length_m = self.original_bbox.XMax - self.original_bbox.XMin
            breadth_m = self.original_bbox.YMax - self.original_bbox.YMin
            depth_m = self.original_bbox.ZMax - self.original_bbox.ZMin
        else:
            length_m = (self.original_bbox.XMax - self.original_bbox.XMin) / scale
            breadth_m = (self.original_bbox.YMax - self.original_bbox.YMin) / scale
            depth_m = (self.original_bbox.ZMax - self.original_bbox.ZMin) / scale
        
        self.length_input.setText(f"{length_m:.2f} m")
        self.breadth_input.setText(f"{breadth_m:.2f} m")
        self.draft_input.setText(f"{depth_m * 0.5:.2f} m")
        
        self.real_length_m = length_m
        self.real_breadth_m = breadth_m
        self.real_depth_m = depth_m
        
        self.unit_info.setText(f"Erkannt: {einheit} → L={length_m:.2f}m, B={breadth_m:.2f}m")
        
        App.Console.PrintMessage(f"  Dimensionen: L={length_m:.2f}m, B={breadth_m:.2f}m, D={depth_m:.2f}m\n")
    
    def import_geometry(self):
        """Importiert verschiedene Formate"""
        file_path, _ = QtGui.QFileDialog.getOpenFileName(
            None, "Geometrie importieren", "",
            "Alle Formate (*.stl *.iges *.igs *.step *.stp *.gf *.gf1 *.txt);;"
            "STL (*.stl);;"
            "IGES/STEP (*.iges *.igs *.step *.stp);;"
            "GF/GF1 Punktwolken (*.gf *.gf1 *.txt)")
        
        if not file_path:
            return
        
        try:
            ext = os.path.splitext(file_path)[1].lower()
            
            if ext == '.stl':
                self._import_stl(file_path)
            elif ext in ['.iges', '.igs', '.step', '.stp']:
                self._import_brep(file_path)
            elif ext in ['.gf', '.gf1', '.txt']:
                self._import_gf(file_path)
            else:
                raise Exception(f"Format nicht unterstützt: {ext}")
            
            self.import_status.setText(
                f"✓ <b>{os.path.basename(file_path)}</b><br>"
                f"Typ: {self.geometry_type}, L={self.real_length_m:.1f}m")
            self.import_status.setStyleSheet("color: green;")
            
        except Exception as e:
            self.import_status.setText(f"✗ Fehler: {str(e)}")
            self.import_status.setStyleSheet("color: red;")
            App.Console.PrintError(f"Import-Fehler: {e}\n")
            import traceback
            traceback.print_exc()
    
    def _import_stl(self, file_path):
        """Importiert STL"""
        doc = self.get_document()
        
        mesh = Mesh.Mesh()
        mesh.read(file_path)
        
        App.Console.PrintMessage(f"→ STL: {mesh.CountPoints} Punkte\n")
        
        self.original_bbox = mesh.BoundBox
        self.detected_unit, self.scale_factor = self.detect_units(self.original_bbox)
        self.recalculate_dimensions()
        
        mesh_copy = mesh.copy()
        
        # WICHTIG: Skalieren wenn in Metern!
        if self.detected_unit == "m":
            scale_matrix = App.Matrix()
            scale_matrix.scale(1000.0, 1000.0, 1000.0)
            mesh_copy.transform(scale_matrix)
            App.Console.PrintMessage("  → Skaliere: m → mm (×1000)\n")
        
        # Zentrieren
        if self.auto_center.isChecked():
            bbox_scaled = mesh_copy.BoundBox
            shift_x = -(bbox_scaled.XMax + bbox_scaled.XMin) / 2
            shift_y = -(bbox_scaled.YMax + bbox_scaled.YMin) / 2
            
            transform = App.Matrix()
            transform.move(App.Vector(shift_x, shift_y, 0))
            mesh_copy.transform(transform)
            App.Console.PrintMessage(f"  → Zentriert ({shift_x/1000:.1f}m)\n")
        
        # Alte entfernen
        if self.imported_geometry and self.imported_geometry in doc.Objects:
            doc.removeObject(self.imported_geometry.Name)
        if self.converted_solid and self.converted_solid in doc.Objects:
            doc.removeObject(self.converted_solid.Name)
        
        # Mesh-Objekt
        mesh_obj = doc.addObject("Mesh::Feature", "Imported_Hull")
        mesh_obj.Mesh = mesh_copy
        mesh_obj.Label = f"Hull_{os.path.basename(file_path)}"
        self.imported_geometry = mesh_obj
        self.geometry_type = "mesh"
        
        # Zu Solid konvertieren
        converter = GeometryConverter()
        solid_obj = converter.convert_mesh_to_solid(mesh_obj)
        
        if solid_obj:
            self.converted_solid = solid_obj
            self.geometry_type = "solid"
        else:
            self.converted_solid = mesh_obj
        
        doc.recompute()
    
    def _import_brep(self, file_path):
        """Importiert IGES/STEP"""
        doc = self.get_document()
        
        App.Console.PrintMessage(f"→ IGES/STEP Import...\n")
        
        shape = Part.Shape()
        shape.read(file_path)
        
        if not shape.isValid():
            raise Exception("Ungültige Geometrie")
        
        if not shape.Solids:
            raise Exception("Keine Solids gefunden")
        
        # Alte entfernen
        if self.imported_geometry and self.imported_geometry in doc.Objects:
            doc.removeObject(self.imported_geometry.Name)
        if self.converted_solid and self.converted_solid in doc.Objects:
            doc.removeObject(self.converted_solid.Name)
        
        solid_obj = doc.addObject("Part::Feature", "Imported_Hull")
        solid_obj.Shape = shape
        solid_obj.Label = f"Hull_{os.path.basename(file_path)}"
        
        self.imported_geometry = solid_obj
        self.converted_solid = solid_obj
        self.geometry_type = "solid"
        
        # Dimensionen
        self.original_bbox = shape.BoundBox
        self.detected_unit, self.scale_factor = self.detect_units(self.original_bbox)
        self.recalculate_dimensions()
        
        # Skalieren und zentrieren
        if self.detected_unit == "m":
            solid_obj.Shape = shape.copy()
            solid_obj.Shape.scale(1000.0)
            App.Console.PrintMessage("  → Skaliert: m → mm\n")
        
        if self.auto_center.isChecked():
            bbox = solid_obj.Shape.BoundBox
            shift_x = -(bbox.XMax + bbox.XMin) / 2
            shift_y = -(bbox.YMax + bbox.YMin) / 2
            solid_obj.Placement.Base = App.Vector(shift_x, shift_y, 0)
            App.Console.PrintMessage(f"  → Zentriert\n")
        
        doc.recompute()

        
    def _import_gf(self, file_path):
            """Importiert GF/GF1 Datei (strukturiert mit Spanten)"""
            doc = self.get_document()
            
            App.Console.PrintMessage(f"→ GF/GF1 Import...\n")
            
            # Importiere GF_Parser
            from .GF_Parser import parse_gf_file
            
            # Parse GF-Datei
            solid_obj, length_m, breadth_m, depth_m = parse_gf_file(file_path, doc)
            
            if not solid_obj:
                raise Exception("GF-Parsing fehlgeschlagen")
            
            # Alte entfernen
            if self.imported_geometry and self.imported_geometry in doc.Objects:
                doc.removeObject(self.imported_geometry.Name)
            if self.converted_solid and self.converted_solid in doc.Objects:
                doc.removeObject(self.converted_solid.Name)
            
            self.imported_geometry = solid_obj
            self.converted_solid = solid_obj
            self.geometry_type = "solid"
            
            # Dimensionen setzen
            self.real_length_m = length_m
            self.real_breadth_m = breadth_m
            self.real_depth_m = depth_m
            
            # UI aktualisieren
            self.length_input.setText(f"{length_m:.2f} m")
            self.breadth_input.setText(f"{breadth_m:.2f} m")
            self.draft_input.setText(f"{depth_m * 0.5:.2f} m")
            
            self.unit_info.setText(
                f"GF-Datei: L={length_m:.2f}m, B={breadth_m:.2f}m, H={depth_m:.2f}m")
            
            # Zentrieren (GF ist schon in mm)
            if self.auto_center.isChecked():
                bbox = solid_obj.Shape.BoundBox
                shift_x = -(bbox.XMax + bbox.XMin) / 2
                shift_y = -(bbox.YMax + bbox.YMin) / 2
                solid_obj.Placement.Base = App.Vector(shift_x, shift_y, 0)
                App.Console.PrintMessage(f"  → Zentriert\n")
            
            doc.recompute()


    
    def refresh_selection(self):
        solids = Selection.get_solids()
        
        if solids:
            names = [s.Label for s in solids[:3]]
            self.selected_info.setText(
                f"✓ <b>{len(solids)} Objekt(e)</b><br>{', '.join(names)}")
            self.selected_info.setStyleSheet("color: green;")
        else:
            self.selected_info.setText("⚠ <i>Keine Solids ausgewählt</i>")
            self.selected_info.setStyleSheet("color: orange;")

        
    def accept(self):
        """Erstellt Schiffsinstanz"""
        solids = None
        
        self.ensure_document()
        
        try:
            if self.radio_example.isChecked():
                # Beispielschiff laden
                solids = self.load_example_ship()
                
                if not solids:
                    QtGui.QMessageBox.critical(None, "Fehler",
                        "Beispielschiff konnte nicht geladen werden!")
                    return False
                
                # WICHTIG: Beispielschiffe haben bereits eine Ship Instance!
                # Prüfe ob schon eine existiert
                existing_ships = []
                for obj in App.ActiveDocument.Objects:
                    if hasattr(obj, 'Length') and hasattr(obj, 'Breadth'):
                        existing_ships.append(obj)
                
                if existing_ships:
                    # Beispielschiff ist komplett - verwende existierende Ship Instance
                    App.Console.PrintMessage(
                        f"✓ Beispielschiff geladen mit Ship Instance: {existing_ships[0].Label}\n")
                    Gui.Control.closeDialog()
                    return True
                
                # Falls keine Ship Instance existiert, erstelle eine
                # (sollte normalerweise nicht vorkommen bei Beispielschiffen)
                App.Console.PrintWarning("⚠ Beispielschiff hat keine Ship Instance - erstelle neue\n")
                
            elif self.radio_import.isChecked():
                # Importierte Geometrie
                if not self.converted_solid:
                    QtGui.QMessageBox.warning(None, "Kein Solid",
                        "Bitte importieren Sie zuerst eine Geometrie!")
                    return False
                
                if hasattr(self.converted_solid, 'Shape') and self.converted_solid.Shape:
                    solids = [self.converted_solid.Shape]
                else:
                    solids = [self.converted_solid]
                    
            elif self.radio_selected.isChecked():
                # Ausgewähltes Objekt
                solids = Selection.get_solids()
                if not solids:
                    QtGui.QMessageBox.warning(None, "Keine Auswahl",
                        "Bitte wählen Sie Solids aus!")
                    return False
            
            # Wenn wir bis hierher kommen, brauchen wir eine neue Ship Instance
            if not solids:
                QtGui.QMessageBox.critical(None, "Fehler",
                    "Keine gültige Geometrie!")
                return False
            
            # Ship erwartet mm
            length_mm = self.real_length_m * 1000.0
            breadth_mm = self.real_breadth_m * 1000.0
            draft_mm = (self.real_depth_m * 0.5) * 1000.0
            
            App.Console.PrintMessage(f"→ Erstelle Schiff:\n")
            App.Console.PrintMessage(f"   L={length_mm}mm ({self.real_length_m}m)\n")
            App.Console.PrintMessage(f"   B={breadth_mm}mm ({self.real_breadth_m}m)\n")
            App.Console.PrintMessage(f"   T={draft_mm}mm ({self.real_depth_m * 0.5}m)\n")
            
            Gui.Control.closeDialog()
            
            ship = Tools.createShip(solids, length_mm, breadth_mm, draft_mm)
            
            if ship:
                App.Console.PrintMessage(f"✓ Schiff erstellt: {ship.Name}\n")
                return True
            else:
                raise Exception("createShip hat None zurückgegeben")
                
        except Exception as e:
            App.Console.PrintError(f"Fehler: {e}\n")
            import traceback
            traceback.print_exc()
            QtGui.QMessageBox.critical(None, "Fehler", str(e))
            return False

    
    def reject(self):
        return True
    

    def load_example_ship(self):
        """Lädt Original-Beispielschiff"""
        example_idx = self.example_combo.currentIndex()
        
        path = Paths.modulePath() + "/resources/examples/"
        
        files = [
            "s60.fcstd",
            "wigley.fcstd",
            "s60_katamaran.fcstd",
            "wigley_katamaran.fcstd"
        ]
        
        file_path = path + files[example_idx]
        
        App.Console.PrintMessage(f"→ Lade Beispielschiff: {files[example_idx]}\n")
        
        if not os.path.exists(file_path):
            App.Console.PrintError(f"✗ Datei nicht gefunden: {file_path}\n")
            QtGui.QMessageBox.critical(None, "Fehler",
                f"Beispielschiff nicht gefunden:\n{file_path}")
            return None
        
        new_doc = App.open(file_path)
        App.ActiveDocument.recompute()

        # ===== DEBUG: Zeige ALLE Objekte =====
        App.Console.PrintMessage("\n=== DEBUG: Objekte im Dokument ===\n")
        for obj in App.ActiveDocument.Objects:
            App.Console.PrintMessage(f"  {obj.Name:20s} | {obj.Label:20s} | TypeId: {obj.TypeId}\n")
            
            # Prüfe verschiedene Attribute
            if hasattr(obj, 'Length'):
                App.Console.PrintMessage(f"    → Hat 'Length' Attribut - IST SHIP!\n")
            if hasattr(obj, 'Breadth'):
                App.Console.PrintMessage(f"    → Hat 'Breadth' Attribut - IST SHIP!\n")
        App.Console.PrintMessage("=== ENDE DEBUG ===\n\n")
        # ===== ENDE DEBUG =====

            
        
        solids = []  # ← WICHTIG: Liste initialisieren!
        
        for obj in App.ActiveDocument.Objects:
            if hasattr(obj, 'Shape') and obj.Shape and obj.Shape.Solids:
                solids.extend(obj.Shape.Solids)
                App.Console.PrintMessage(f"  Gefunden: {obj.Label} ({len(obj.Shape.Solids)} Solids)\n")
        
        if solids:
            App.Console.PrintMessage(f"✓ {len(solids)} Solid(s) gefunden\n")
            
            if solids[0].BoundBox:
                bbox = solids[0].BoundBox
                length_m = (bbox.XMax - bbox.XMin) / 1000.0
                breadth_m = (bbox.YMax - bbox.YMin) / 1000.0
                depth_m = (bbox.ZMax - bbox.ZMin) / 1000.0
                
                self.real_length_m = length_m
                self.real_breadth_m = breadth_m
                self.real_depth_m = depth_m
                
                self.length_input.setText(f"{length_m:.2f} m")
                self.breadth_input.setText(f"{breadth_m:.2f} m")
                self.draft_input.setText(f"{depth_m * 0.5:.2f} m")
                
                App.Console.PrintMessage(f"  Dimensionen: L={length_m:.1f}m, B={breadth_m:.1f}m\n")
            
            return solids
        else:
            App.Console.PrintWarning("⚠ Keine Solids gefunden\n")
            return None

    
    def needsFullSpace(self): 
        return True
    
    def isAllowedAlterSelection(self): 
        return False
    
    def isAllowedAlterView(self): 
        return True
    
    def isAllowedAlterDocument(self): 
        return False


def createTask():
    panel = TaskPanel()
    Gui.Control.showDialog(panel)
    return panel
