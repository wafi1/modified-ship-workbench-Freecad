#***************************************************************************
#*                                                                         *
#*   Copyright (c) 2011, 2016 Jose Luis Cercos Pita <jlcercos@gmail.com>   *
#*   Copyright (c) 2024, 2025 Peter Gottwald <yachtdesign@peter-gottwald.de>            *
#*                                                                         *
#*   This program is free software; you can redistribute it and/or modify  *
#*   it under the terms of the GNU Lesser General Public License (LGPL)    *
#*   as published by the Free Software Foundation; either version 2 of     *
#*   the License, or (at your option) any later version.                   *
#*   for detail see the LICENCE text file.                                 *
#*                                                                         *
#*   This program is distributed in the hope that it will be useful,       *
#*   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
#*   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
#*   GNU Library General Public License for more details.                  *
#*                                                                         *
#*   You should have received a copy of the GNU Library General Public     *
#*   License along with this program; if not, write to the Free Software   *
#*   Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  *
#*   USA                                                                   *
#*                                                                         *
#***************************************************************************

import os
import sys
import FreeCAD as App
import FreeCADGui as Gui
from FreeCAD import Units
from PySide import QtGui, QtCore
from . import Tools
from .. import Instance
from ..shipUtils import Locale
from ..shipUtils import Selection
from ..shipUtils import Paths

from .GeometryConverter import GeometryConverter, check_solid_validity

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
        
        # WICHTIG: Initialwerte müssen korrekt sein
        self.real_length_m = 100.0
        self.real_breadth_m = 16.0
        self.real_depth_m = 12.0
        
        self.ensure_document()
        
    def ensure_document(self):
        """Stellt sicher, dass ein Dokument geöffnet ist"""
        if not App.ActiveDocument:
            App.newDocument("ShipDesign")
            App.Console.PrintMessage("✓ Neues Dokument erstellt\n")
    
    def get_document(self):
        """Gibt aktives Dokument zurück oder erstellt neues"""
        self.ensure_document()
        return App.ActiveDocument
        
    def create_ui(self):
        """Erstellt die Benutzeroberfläche"""
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
        self.selected_info.setWordWrap(True)
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
        """Reagiert auf Änderung der Geometrie-Quelle"""
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
        dimensions = [
            (25.5, 3.5, 1.0),   # Series 60 Slender
            (4.0, 0.8, 0.4),    # Wigley
            (25.5, 3.5, 1.0),   # Series 60 Block
            (4.0, 0.8, 0.4),    # Wigley Katamaran
        ]
        
        L, B, T = dimensions[example]
        self._updating_ui = True
        self.length_input.setText(f"{L} m")
        self.breadth_input.setText(f"{B} m")
        self.draft_input.setText(f"{T} m")
        
        self.real_length_m = L
        self.real_breadth_m = B
        self.real_depth_m = T * 2
    
    def on_unit_changed(self, index):
        """Reagiert auf Änderung der Einheit"""
        if self.original_bbox:
            self.recalculate_dimensions()
    
    def on_dimension_changed(self):
        """Aktualisiert interne Dimensionen"""
        if getattr(self, '_updating_ui', False):
            return

        try:
            length_text = self.length_input.text()
            breadth_text = self.breadth_input.text()
            draft_text = self.draft_input.text()
            
            try:
                length_qty = Units.parseQuantity(length_text)
                breadth_qty = Units.parseQuantity(breadth_text)
                draft_qty = Units.parseQuantity(draft_text)
                
                self.real_length_m = float(length_qty.getValueAs('m'))
                self.real_breadth_m = float(breadth_qty.getValueAs('m'))
                self.real_depth_m = float(draft_qty.getValueAs('m') * 2)
                
            except Exception as parse_err:
                App.Console.PrintError(f"Parse Fehler: {parse_err}\n")
                self.real_length_m = self._parse_manual(length_text)
                self.real_breadth_m = self._parse_manual(breadth_text)
                self.real_depth_m = self._parse_manual(draft_text) * 2
            
        except Exception as e:
            App.Console.PrintError(f"Fehler in on_dimension_changed: {e}\n")
    
    def _parse_manual(self, text):
        """Manuelles Parsen als Fallback"""
        if not text:
            return 0.0
        text = text.strip().replace(',', '.')
        for unit in ['m', 'mm', 'km', 'ft', 'in']:
            if unit in text.lower():
                text = text.lower().replace(unit, '').strip()
        try:
            return float(text)
        except:
            return 0.0
    
    def detect_units(self, bbox):
        """Erkennt Einheiten basierend auf Bounding Box"""
        length = bbox.XMax - bbox.XMin
        breadth = bbox.YMax - bbox.YMin
        depth = bbox.ZMax - bbox.ZMin
        
        unit_idx = self.unit_combo.currentIndex()
        
        if unit_idx == 1:
            return "mm", 1000.0
        elif unit_idx == 2:
            return "m", 1.0
        
        # Auto-Erkennung
        if 10.0 <= length <= 500.0 and 1.0 <= breadth <= 100.0:
            ratio = length / breadth if breadth > 0 else 0
            if 2.0 < ratio < 20.0:
                return "m", 1.0
        
        if length > 10000:
            return "mm", 1000.0
        
        return "m", 1.0
    
    def recalculate_dimensions(self):
        """Berechnet Dimensionen basierend auf erkannter Einheit"""
        if not self.original_bbox:
            return
        
        length_raw = self.original_bbox.XMax - self.original_bbox.XMin
        breadth_raw = self.original_bbox.YMax - self.original_bbox.YMin
        depth_raw = self.original_bbox.ZMax - self.original_bbox.ZMin
        
        if self.detected_unit == "m":
            length_m = length_raw
            breadth_m = breadth_raw
            depth_m = depth_raw
        else:
            length_m = length_raw / 1000.0
            breadth_m = breadth_raw / 1000.0
            depth_m = depth_raw / 1000.0
        
        self.real_length_m = float(length_m)
        self.real_breadth_m = float(breadth_m)
        self.real_depth_m = float(depth_m)
        
        self._updating_ui = True
        self.length_input.setText(f"{self.real_length_m:.2f} m")
        self.breadth_input.setText(f"{self.real_breadth_m:.2f} m")
        self.draft_input.setText(f"{self.real_depth_m * 0.5:.2f} m")
        
        self.unit_info.setText(
            f"Erkannt: {self.detected_unit} → "
            f"L={self.real_length_m:.2f}m, B={self.real_breadth_m:.2f}m")
    
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
        """Importiert STL Datei - MIT VALIDIERUNG"""
        doc = self.get_document()
        
        mesh = Mesh.Mesh()
        mesh.read(file_path)
        
        original_facets = mesh.CountFacets
        App.Console.PrintMessage(f"→ STL: {mesh.CountPoints} Punkte, {original_facets} Facets\n")
        
        # Vereinfachung
        mesh.harmonizeNormals()
        if original_facets > 5000:
            mesh.decimate(0.1, 0.85)
            App.Console.PrintMessage(
                f"  Dezimiert: {original_facets} → {mesh.CountFacets} Facets\n")
        
        # WICHTIG: Original Bounding Box VOR jeder Transformation speichern!
        self.original_bbox = mesh.BoundBox
        
        # Einheit erkennen
        self.detected_unit, self.scale_factor = self.detect_units(self.original_bbox)
        self.recalculate_dimensions()
        
        mesh_copy = mesh.copy()
        
        # Skalieren wenn in Metern
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
        
        # Zu Solid konvertieren MIT NEUEM CONVERTER
        converter = GeometryConverter()
        solid_obj = converter.convert_mesh_to_solid(mesh_obj)
        
        if solid_obj:
            # VALIDIERUNG
            is_valid, msg = check_solid_validity(solid_obj)
            if is_valid:
                App.Console.PrintMessage(f"✓ Solid validiert: {msg}\n")
                self.converted_solid = solid_obj
                self.geometry_type = "solid"
            else:
                App.Console.PrintError(f"✗ Solid ungültig: {msg}\n")
                App.Console.PrintMessage("→ Verwende Mesh-Proxy\n")
                # Fallback: Verwende Mesh
                self.converted_solid = mesh_obj
        else:
            self.converted_solid = mesh_obj
        
        doc.recompute()
        
    def _import_brep(self, file_path):
        """Importiert IGES/STEP Datei"""
        doc = self.get_document()
        
        App.Console.PrintMessage(f"→ IGES/STEP Import...\n")
        
        shape = Part.Shape()
        shape.read(file_path)
        
        if not shape.isValid():
            raise Exception("Ungültige Geometrie")
        
        if not shape.Solids:
            raise Exception("Keine Solids gefunden")
        
        self.original_bbox = shape.BoundBox
        self.detected_unit, self.scale_factor = self.detect_units(self.original_bbox)
        
        final_shape = shape.copy()
        
        if self.detected_unit == "m":
            final_shape.scale(1000.0)
            App.Console.PrintMessage(f"  → Skaliert: m → mm (×1000)\n")
        
        # Alte entfernen
        if self.imported_geometry and self.imported_geometry in doc.Objects:
            doc.removeObject(self.imported_geometry.Name)
        if self.converted_solid and self.converted_solid in doc.Objects:
            doc.removeObject(self.converted_solid.Name)
        
        solid_obj = doc.addObject("Part::Feature", "Imported_Hull")
        solid_obj.Shape = final_shape
        solid_obj.Label = f"Hull_{os.path.basename(file_path)}"
        
        self.imported_geometry = solid_obj
        self.converted_solid = solid_obj
        self.geometry_type = "solid"
        
        self.recalculate_dimensions()
        
        if self.auto_center.isChecked():
            bbox = solid_obj.Shape.BoundBox
            shift_x = -(bbox.XMax + bbox.XMin) / 2
            shift_y = -(bbox.YMax + bbox.YMin) / 2
            solid_obj.Placement.Base = App.Vector(shift_x, shift_y, 0)
            App.Console.PrintMessage(f"  → Zentriert\n")
        
        doc.recompute()

    def _import_gf(self, file_path):
        """Importiert GF/GF1 Datei"""
        doc = self.get_document()
        
        App.Console.PrintMessage(f"→ GF/GF1 Import...\n")
        
        from .GF_Parser import parse_gf_file
        
        solid_obj, length_m, breadth_m, depth_m = parse_gf_file(file_path, doc)
        
        if not solid_obj:
            raise Exception("GF-Parsing fehlgeschlagen")
        
        if self.imported_geometry and self.imported_geometry in doc.Objects:
            doc.removeObject(self.imported_geometry.Name)
        if self.converted_solid and self.converted_solid in doc.Objects:
            doc.removeObject(self.converted_solid.Name)
        
        self.imported_geometry = solid_obj
        self.converted_solid = solid_obj
        self.geometry_type = "solid"
        
        self.original_bbox = solid_obj.Shape.BoundBox
        
        self.real_length_m = length_m
        self.real_breadth_m = breadth_m
        self.real_depth_m = depth_m
        self.detected_unit = "m"
        
        self._updating_ui = True
        self.length_input.setText(f"{length_m:.2f} m")
        self.breadth_input.setText(f"{breadth_m:.2f} m")
        self.draft_input.setText(f"{depth_m * 0.5:.2f} m")
        
        self.unit_info.setText(
            f"GF-Datei: L={length_m:.2f}m, B={breadth_m:.2f}m, H={depth_m:.2f}m")
        
        if self.auto_center.isChecked():
            bbox = solid_obj.Shape.BoundBox
            shift_x = -(bbox.XMax + bbox.XMin) / 2
            shift_y = -(bbox.YMax + bbox.YMin) / 2
            solid_obj.Placement.Base = App.Vector(shift_x, shift_y, 0)
            App.Console.PrintMessage(f"  → Zentriert\n")
        
        doc.recompute()
    
    def refresh_selection(self):
        """Aktualisiert die Anzeige der ausgewählten Objekte"""
        try:
            solids = Selection.get_solids()
        except Exception as e:
            self.selected_info.setText(f"⚠ Fehler: {str(e)}")
            self.selected_info.setStyleSheet("color: red;")
            return
        
        if solids:
            names = []
            for s in solids[:3]:
                if hasattr(s, 'Label'):
                    names.append(s.Label)
                elif hasattr(s, 'Name'):
                    names.append(s.Name)
                else:
                    names.append(type(s).__name__)
            
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
        
        App.Console.PrintMessage(f"DEBUG accept():\n")
        App.Console.PrintMessage(f"  L={self.real_length_m}m, B={self.real_breadth_m}m, T={self.real_depth_m*0.5}m\n")
        
        try:
            if self.radio_example.isChecked():
                solids = self.load_example_ship()
                if not solids:
                    QtGui.QMessageBox.critical(None, "Fehler",
                        "Beispielschiff konnte nicht geladen werden!")
                    return False
                
            elif self.radio_import.isChecked():
                if not self.converted_solid:
                    QtGui.QMessageBox.warning(None, "Kein Solid",
                        "Bitte importieren Sie zuerst eine Geometrie!")
                    return False
                
                # KORREKTUR: Prüfe ob wir ein Document-Objekt haben
                if hasattr(self.converted_solid, 'Shape'):
                    # Validierung vor dem Weitergeben
                    shape = self.converted_solid.Shape
                    if not shape.isValid():
                        QtGui.QMessageBox.warning(None, "Ungültige Geometrie",
                            "Das Solid ist ungültig. Bitte importieren Sie erneut.")
                        return False
                    solids = [shape]
                else:
                    solids = [self.converted_solid]
                    
            elif self.radio_selected.isChecked():
                solids = Selection.get_solids()
                if not solids:
                    QtGui.QMessageBox.warning(None, "Keine Auswahl",
                        "Bitte wählen Sie Solids aus!")
                    return False
            
            if not solids:
                QtGui.QMessageBox.critical(None, "Fehler", "Keine gültige Geometrie!")
                return False
            
            # NEU - durch Quantity-Objekte ersetzen:
            from FreeCAD import Units

            L = Units.parseQuantity(f"{self.real_length_m} m")
            B = Units.parseQuantity(f"{self.real_breadth_m} m")
            T = Units.parseQuantity(f"{self.real_depth_m * 0.5} m")

            App.Console.PrintMessage(f"→ Erstelle Schiff: L={L}, B={B}, T={T}\n")

            Gui.Control.closeDialog()

            ship = Tools.createShip(solids, L, B, T)
            
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
        """Dialog abbrechen"""
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
        
        if example_idx >= len(files):
            example_idx = 0
            
        file_path = path + files[example_idx]
        
        App.Console.PrintMessage(f"→ Lade Beispielschiff: {files[example_idx]}\n")
        
        if not os.path.exists(file_path):
            App.Console.PrintError(f"✗ Datei nicht gefunden: {file_path}\n")
            return None
        
        try:
            new_doc = App.open(file_path)
            App.ActiveDocument.recompute()
        except Exception as e:
            App.Console.PrintError(f"✗ Fehler beim Öffnen: {e}\n")
            return None

        solids = []
        
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
    """Erstellt und zeigt den Task Panel an"""
    panel = TaskPanel()
    Gui.Control.showDialog(panel)
    return panel
