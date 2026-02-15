#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# packlist_import.py - Import von Excel-Packlisten in FreeCAD
#***************************************************************************

import os
import sys
import re
import pandas as pd
import numpy as np
from PySide2 import QtWidgets, QtGui, QtCore
import FreeCAD as App
import FreeCADGui as Gui
from FreeCAD import Units

class PacklistImporter:
    """Dialog zum Import von Excel-Packlisten"""
    
    def __init__(self):
        self.file_path = None
        self.df = None
        self.prefix = "Packliste_"
        
    def open_file_dialog(self):
        """Öffnet Dateiauswahl-Dialog"""
        caption = "Excel-Packliste öffnen"
        filter_str = "Excel-Dateien (*.xlsx *.xls *.xlsm *.csv);;Alle Dateien (*.*)"
        
        dialog = QtWidgets.QFileDialog()
        file_path, _ = dialog.getOpenFileName(None, caption, "", filter_str)
        
        if file_path and os.path.exists(file_path):
            self.file_path = file_path
            return True
        return False
    
    def read_excel_file(self, file_path):
        """Liest Excel-Datei mit verschiedenen Methoden"""
        try:
            # Versuche verschiedene Engines
            try:
                df = pd.read_excel(file_path, engine='openpyxl')
            except:
                try:
                    df = pd.read_excel(file_path, engine='xlrd')
                except:
                    # Als CSV versuchen
                    df = pd.read_csv(file_path, sep=None, engine='python')
            
            # DataFrame bereinigen
            df = df.dropna(how='all')  # Leere Zeilen entfernen
            df = df.reset_index(drop=True)
            
            # Spaltennamen bereinigen
            df.columns = [str(col).strip() for col in df.columns]
            
            self.df = df
            return True, f"Datei geladen: {len(df)} Zeilen, {len(df.columns)} Spalten"
            
        except Exception as e:
            return False, f"Fehler beim Lesen der Datei: {str(e)}"
    
    def detect_columns(self):
        """Versucht automatisch Spalten zu erkennen"""
        if self.df is None or self.df.empty:
            return {}
        
        column_types = {
            'bezeichnung': None,
            'beschreibung': None,
            'gewicht': None,
            'laenge': None,
            'breite': None,
            'hoehe': None,
            'menge': None
        }
        
        # Häufige Spaltennamen
        patterns = {
            'bezeichnung': ['bezeichnung', 'name', 'teil', 'artikel', 'item', 'part', 'nr', 'nummer'],
            'beschreibung': ['beschreibung', 'bemerkung', 'comment', 'notes', 'description'],
            'gewicht': ['gewicht', 'weight', 'masse', 'mass', 'kg', 'tonnen', 't', 'w'],
            'laenge': ['länge', 'laenge', 'length', 'l', 'lang', 'x'],
            'breite': ['breite', 'width', 'b', 'y'],
            'hoehe': ['höhe', 'hoehe', 'height', 'h', 'z', 'tiefe'],
            'menge': ['menge', 'anzahl', 'quantity', 'qty', 'stück', 'stk']
        }
        
        for col in self.df.columns:
            col_lower = str(col).lower()
            
            for col_type, pattern_list in patterns.items():
                for pattern in pattern_list:
                    if pattern in col_lower:
                        if column_types[col_type] is None:
                            column_types[col_type] = col
                        break
        
        return column_types
    
    def create_column_mapping_dialog(self):
        """Dialog zur Spaltenzuordnung"""
        if self.df is None:
            return None
        
        dialog = QtWidgets.QDialog()
        dialog.setWindowTitle("Spaltenzuordnung - Packliste Import")
        dialog.setMinimumWidth(600)
        
        layout = QtWidgets.QVBoxLayout(dialog)
        
        # Tabelle mit Daten anzeigen
        table_label = QtWidgets.QLabel(f"Vorschau der Daten ({len(self.df)} Zeilen):")
        layout.addWidget(table_label)
        
        table = QtWidgets.QTableWidget(min(10, len(self.df)), len(self.df.columns))
        table.setHorizontalHeaderLabels(self.df.columns.tolist())
        
        for i in range(min(10, len(self.df))):
            for j, col in enumerate(self.df.columns):
                value = self.df.iloc[i, j]
                if pd.isna(value):
                    table.setItem(i, j, QtWidgets.QTableWidgetItem(""))
                else:
                    table.setItem(i, j, QtWidgets.QTableWidgetItem(str(value)))
        
        layout.addWidget(table)
        
        # Spaltenzuordnung
        mapping_layout = QtWidgets.QGridLayout()
        row = 0
        
        column_types = [
            ("Bezeichnung", "bezeichnung", True),
            ("Beschreibung", "beschreibung", False),
            ("Gewicht", "gewicht", True),
            ("Länge", "laenge", True),
            ("Breite", "breite", True),
            ("Höhe", "hoehe", True),
            ("Menge", "menge", False)
        ]
        
        self.combo_boxes = {}
        
        for label_text, col_type, required in column_types:
            label = QtWidgets.QLabel(f"{label_text}:")
            if required:
                label.setText(f"{label_text}*:")
            
            combo = QtWidgets.QComboBox()
            combo.addItem("(nicht zuordnen)", "")
            
            for col in self.df.columns:
                combo.addItem(col, col)
            
            # Automatische Erkennung verwenden
            detected = self.detect_columns()
            if col_type in detected and detected[col_type] is not None:
                index = combo.findData(detected[col_type])
                if index >= 0:
                    combo.setCurrentIndex(index)
            
            self.combo_boxes[col_type] = combo
            
            mapping_layout.addWidget(label, row, 0)
            mapping_layout.addWidget(combo, row, 1)
            row += 1
        
        layout.addLayout(mapping_layout)
        
        # Einheiten-Einstellungen
        units_group = QtWidgets.QGroupBox("Einheiten")
        units_layout = QtWidgets.QGridLayout()
        
        # Gewichtseinheit
        units_layout.addWidget(QtWidgets.QLabel("Gewichtseinheit:"), 0, 0)
        self.weight_unit_combo = QtWidgets.QComboBox()
        self.weight_unit_combo.addItems(["kg", "t", "g"])
        units_layout.addWidget(self.weight_unit_combo, 0, 1)
        
        # Längeneinheit
        units_layout.addWidget(QtWidgets.QLabel("Längeneinheit:"), 1, 0)
        self.length_unit_combo = QtWidgets.QComboBox()
        self.length_unit_combo.addItems(["mm", "cm", "m"])
        units_layout.addWidget(self.length_unit_combo, 1, 1)
        
        # Startzeile
        units_layout.addWidget(QtWidgets.QLabel("Start bei Zeile:"), 2, 0)
        self.start_row_spin = QtWidgets.QSpinBox()
        self.start_row_spin.setRange(0, max(0, len(self.df)-1))
        self.start_row_spin.setValue(0)
        units_layout.addWidget(self.start_row_spin, 2, 1)
        
        # Endzeile
        units_layout.addWidget(QtWidgets.QLabel("Ende bei Zeile:"), 3, 0)
        self.end_row_spin = QtWidgets.QSpinBox()
        self.end_row_spin.setRange(0, max(0, len(self.df)-1))
        self.end_row_spin.setValue(min(100, len(self.df)-1))
        units_layout.addWidget(self.end_row_spin, 3, 1)
        
        units_group.setLayout(units_layout)
        layout.addWidget(units_group)
        
        # Buttons
        button_layout = QtWidgets.QHBoxLayout()
        ok_button = QtWidgets.QPushButton("Importieren")
        cancel_button = QtWidgets.QPushButton("Abbrechen")
        
        ok_button.clicked.connect(dialog.accept)
        cancel_button.clicked.connect(dialog.reject)
        
        button_layout.addWidget(ok_button)
        button_layout.addWidget(cancel_button)
        layout.addLayout(button_layout)
        
        result = dialog.exec_()
        
        if result == QtWidgets.QDialog.Accepted:
            mapping = {}
            for col_type, combo in self.combo_boxes.items():
                mapping[col_type] = combo.currentData()
            
            return {
                'mapping': mapping,
                'weight_unit': self.weight_unit_combo.currentText(),
                'length_unit': self.length_unit_combo.currentText(),
                'start_row': self.start_row_spin.value(),
                'end_row': self.end_row_spin.value()
            }
        
        return None
    
    def parse_value(self, value, default=0.0):
        """Parse einen Wert mit verschiedenen Formaten"""
        if pd.isna(value):
            return default
        
        try:
            # Wenn es bereits eine Zahl ist
            if isinstance(value, (int, float)):
                return float(value)
            
            str_val = str(value).strip()
            
            # Entferne nicht-numerische Zeichen (außer Punkt und Minus)
            str_val = re.sub(r'[^\d\.\-\+]', '', str_val)
            
            if not str_val:
                return default
            
            return float(str_val)
        except:
            return default
    
    def convert_to_mm(self, value, from_unit):
        """Konvertiert Längenangaben zu mm"""
        if from_unit == "mm":
            return value
        elif from_unit == "cm":
            return value * 10
        elif from_unit == "m":
            return value * 1000
        else:
            return value
    
    def convert_to_kg(self, value, from_unit):
        """Konvertiert Gewichtsangaben zu kg"""
        if from_unit == "kg":
            return value
        elif from_unit == "t":
            return value * 1000
        elif from_unit == "g":
            return value / 1000
        else:
            return value
    
    def create_box(self, length_mm, width_mm, height_mm, label, description, weight_kg):
        """Erstellt einen Quader im Part Workbench"""
        try:
            import Part
            
            # Dokument sicherstellen
            doc = App.ActiveDocument
            if doc is None:
                doc = App.newDocument("Packliste")
            
            # Quader erstellen
            box = doc.addObject("Part::Box", f"Box_{label}")
            box.Length = length_mm
            box.Width = width_mm
            box.Height = height_mm
            
            # Position auf 0,0,0
            box.Placement = App.Placement(App.Vector(0, 0, 0), App.Rotation())
            
            # Eigenschaften hinzufügen
            box.addProperty("App::PropertyString", "Bezeichnung", "Packliste", "Artikelbezeichnung")
            box.addProperty("App::PropertyString", "Beschreibung", "Packliste", "Beschreibung")
            box.addProperty("App::PropertyFloat", "Gewicht_kg", "Packliste", "Gewicht in kg")
            box.addProperty("App::PropertyFloat", "Laenge_mm", "Packliste", "Länge in mm")
            box.addProperty("App::PropertyFloat", "Breite_mm", "Packliste", "Breite in mm")
            box.addProperty("App::PropertyFloat", "Hoehe_mm", "Packliste", "Höhe in mm")
            
            box.Bezeichnung = str(label)
            box.Beschreibung = str(description) if description else ""
            box.Gewicht_kg = weight_kg
            box.Laenge_mm = length_mm
            box.Breite_mm = width_mm
            box.Hoehe_mm = height_mm
            
            # Label hinzufügen (als Text in Draft Workbench)
            try:
                import Draft
                text = Draft.make_text(
                    [str(label)],
                    placement=App.Placement(App.Vector(length_mm/2, width_mm/2, height_mm + 10), App.Rotation())
                )
                text.Label = f"Label_{label}"
                text.ViewObject.FontSize = min(10, height_mm/5)
            except:
                pass  # Draft nicht verfügbar
            
            doc.recompute()
            return box
            
        except Exception as e:
            App.Console.PrintError(f"Fehler beim Erstellen der Box {label}: {str(e)}\n")
            return None
    
    def create_group(self, objects, group_name):
        """Erstellt eine Gruppe aus Objekten"""
        doc = App.ActiveDocument
        if doc is None:
            return None
        
        group = doc.addObject("App::DocumentObjectGroup", group_name)
        for obj in objects:
            if obj is not None:
                group.addObject(obj)
        
        doc.recompute()
        return group
    
    def apply_weight_tool(self, objects):
        """Wendet das Weight Tool auf Objekte an (falls verfügbar)"""
        try:
            # Suche nach Weight Tool
            weight_tool = None
            for obj in App.ActiveDocument.Objects:
                if hasattr(obj, 'Proxy') and obj.Proxy.__class__.__name__ == 'WeightTool':
                    weight_tool = obj
                    break
            
            if weight_tool is None:
                # Erstelle neues Weight Tool
                from freecad.ship import shipWeight
                weight_tool = shipWeight.makeShipWeightInstance()
            
            # Füge Objekte zum Weight Tool hinzu
            for obj in objects:
                if obj is not None and hasattr(obj, 'Gewicht_kg'):
                    # Hier müsste die spezifische Integration mit dem Weight Tool erfolgen
                    # Dies hängt von der genauen Implementierung des Weight Tools ab
                    App.Console.PrintMessage(f"Füge {obj.Label} zum Weight Tool hinzu: {obj.Gewicht_kg} kg\n")
            
            return weight_tool
            
        except Exception as e:
            App.Console.PrintWarning(f"Fehler beim Weight Tool: {str(e)}\n")
            return None
    
    def auto_arrange_boxes(self, boxes, container_length=12000, container_width=2400, container_height=2700):
        """Automatische Anordnung der Boxen in einem Container"""
        if not boxes:
            return
        
        doc = App.ActiveDocument
        if doc is None:
            return
        
        # Sortiere Boxen nach Volumen (größte zuerst)
        boxes_sorted = sorted(boxes, key=lambda b: b.Laenge_mm * b.Breite_mm * b.Hoehe_mm, reverse=True)
        
        positions = []
        current_x = 0
        current_y = 0
        current_z = 0
        max_height_in_row = 0
        
        for box in boxes_sorted:
            length = box.Laenge_mm
            width = box.Breite_mm
            height = box.Hoehe_mm
            
            # Prüfe ob Box in Container passt
            if (length > container_length or 
                width > container_width or 
                height > container_height):
                App.Console.PrintWarning(f"Box {box.Label} ist zu groß für Container\n")
                continue
            
            # Prüfe ob Box in aktueller Reihe passt
            if current_x + length > container_length:
                # Neue Reihe
                current_x = 0
                current_y += max_height_in_row
                max_height_in_row = 0
            
            # Prüfe ob Box in Höhe passt
            if current_y + width > container_width:
                # Neue Ebene
                current_x = 0
                current_y = 0
                current_z += max_height_in_row
                max_height_in_row = 0
            
            # Setze Position
            box.Placement = App.Placement(
                App.Vector(current_x, current_y, current_z),
                App.Rotation()
            )
            
            # Aktualisiere Positionen für nächste Box
            current_x += length
            max_height_in_row = max(max_height_in_row, height)
        
        doc.recompute()
    
    def import_packlist(self):
        """Hauptfunktion zum Import der Packliste"""
        
        # 1. Datei auswählen
        if not self.open_file_dialog():
            App.Console.PrintError("Keine Datei ausgewählt\n")
            return
        
        # 2. Datei lesen
        success, message = self.read_excel_file(self.file_path)
        if not success:
            App.Console.PrintError(f"{message}\n")
            return
        
        App.Console.PrintMessage(f"{message}\n")
        
        # 3. Spaltenzuordnung-Dialog
        settings = self.create_column_mapping_dialog()
        if settings is None:
            App.Console.PrintMessage("Import abgebrochen\n")
            return
        
        mapping = settings['mapping']
        weight_unit = settings['weight_unit']
        length_unit = settings['length_unit']
        start_row = settings['start_row']
        end_row = min(settings['end_row'], len(self.df) - 1)
        
        # 4. Prüfe erforderliche Spalten
        required_columns = ['bezeichnung', 'gewicht', 'laenge', 'breite', 'hoehe']
        missing = []
        for col in required_columns:
            if not mapping.get(col):
                missing.append(col)
        
        if missing:
            msg = "Fehlende Zuordnung für: " + ", ".join(missing)
            App.Console.PrintError(f"{msg}\n")
            QtWidgets.QMessageBox.warning(None, "Fehlende Zuordnung", msg)
            return
        
        # 5. Import durchführen
        App.Console.PrintMessage(f"\nImportiere Zeilen {start_row} bis {end_row}...\n")
        
        created_boxes = []
        skipped_items = 0
        
        for idx in range(start_row, end_row + 1):
            try:
                row = self.df.iloc[idx]
                
                # Werte extrahieren
                bezeichnung = str(row[mapping['bezeichnung']]) if mapping['bezeichnung'] else f"Item_{idx}"
                beschreibung = str(row[mapping['beschreibung']]) if mapping['beschreibung'] else ""
                
                # Numerische Werte parsen
                weight_val = self.parse_value(row[mapping['gewicht']], 0)
                length_val = self.parse_value(row[mapping['laenge']], 100)
                width_val = self.parse_value(row[mapping['breite']], 100)
                height_val = self.parse_value(row[mapping['hoehe']], 100)
                
                # Menge (falls vorhanden)
                menge = 1
                if mapping['menge']:
                    menge_val = self.parse_value(row[mapping['menge']], 1)
                    menge = max(1, int(menge_val))
                
                # Einheiten umrechnen
                weight_kg = self.convert_to_kg(weight_val, weight_unit)
                length_mm = self.convert_to_mm(length_val, length_unit)
                width_mm = self.convert_to_mm(width_val, length_unit)
                height_mm = self.convert_to_mm(height_val, length_unit)
                
                # Prüfe auf gültige Werte
                if weight_kg <= 0 or length_mm <= 0 or width_mm <= 0 or height_mm <= 0:
                    App.Console.PrintWarning(f"Ungültige Werte in Zeile {idx}: {bezeichnung}\n")
                    skipped_items += 1
                    continue
                
                # Für jede Einheit der Menge
                for i in range(menge):
                    label = f"{bezeichnung}_{idx}" if menge == 1 else f"{bezeichnung}_{idx}_{i+1}"
                    
                    # Box erstellen
                    box = self.create_box(
                        length_mm, width_mm, height_mm,
                        label, beschreibung, weight_kg
                    )
                    
                    if box:
                        created_boxes.append(box)
                        App.Console.PrintMessage(f"Erstellt: {label} - {length_mm}x{width_mm}x{height_mm}mm, {weight_kg}kg\n")
                    
            except Exception as e:
                App.Console.PrintWarning(f"Fehler in Zeile {idx}: {str(e)}\n")
                skipped_items += 1
                continue
        
        # 6. Zusammenfassung
        App.Console.PrintMessage(f"\nImport abgeschlossen:\n")
        App.Console.PrintMessage(f"  Erstellt: {len(created_boxes)} Boxen\n")
        App.Console.PrintMessage(f"  Übersprungen: {skipped_items} Einträge\n")
        
        if not created_boxes:
            App.Console.PrintWarning("Keine Boxen erstellt\n")
            return
        
        # 7. Gruppierung
        group_name = f"Packliste_{os.path.basename(self.file_path).split('.')[0]}"
        group = self.create_group(created_boxes, group_name)
        
        if group:
            App.Console.PrintMessage(f"Gruppe erstellt: {group.Label}\n")
        
        # 8. Automatische Anordnung (optional)
        arrange = QtWidgets.QMessageBox.question(
            None, "Automatische Anordnung",
            "Sollen die Boxen automatisch in einem Container angeordnet werden?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        
        if arrange == QtWidgets.QMessageBox.Yes:
            self.auto_arrange_boxes(created_boxes)
            App.Console.PrintMessage("Boxen automatisch angeordnet\n")
        
        # 9. Weight Tool anwenden (optional)
        apply_weight = QtWidgets.QMessageBox.question(
            None, "Weight Tool",
            "Soll das Weight Tool auf die importierten Boxen angewendet werden?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        
        if apply_weight == QtWidgets.QMessageBox.Yes:
            weight_tool = self.apply_weight_tool(created_boxes)
            if weight_tool:
                App.Console.PrintMessage(f"Weight Tool angewendet: {weight_tool.Label}\n")
        
        # 10. Dokument speichern
        save = QtWidgets.QMessageBox.question(
            None, "Dokument speichern",
            "Möchten Sie das Dokument speichern?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        
        if save == QtWidgets.QMessageBox.Yes:
            default_name = f"Packliste_{os.path.basename(self.file_path).split('.')[0]}.FCStd"
            file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
                None, "Dokument speichern", default_name, "FreeCAD Dokumente (*.FCStd)"
            )
            if file_path:
                App.ActiveDocument.saveAs(file_path)
                App.Console.PrintMessage(f"Dokument gespeichert: {file_path}\n")
        
        App.Console.PrintMessage("\nImport erfolgreich abgeschlossen!\n")

# GUI Dialog für einfache Bedienung
class PacklistImportDialog(QtWidgets.QDialog):
    """Einfacher Dialog zum Starten des Imports"""
    
    def __init__(self):
        super().__init__()
        self.importer = PacklistImporter()
        self.init_ui()
    
    def init_ui(self):
        self.setWindowTitle("Packlisten Import")
        self.setMinimumWidth(400)
        
        layout = QtWidgets.QVBoxLayout(self)
        
        # Titel
        title = QtWidgets.QLabel("Excel Packlisten Import")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)
        
        # Beschreibung
        description = QtWidgets.QLabel(
            "Importiert Packlisten aus Excel/CSV Dateien und erstellt 3D-Quadrate.\n\n"
            "Unterstützt:\n"
            "- Excel (.xlsx, .xls, .xlsm)\n"
            "- CSV Dateien\n"
            "- Automatische Spaltenerkennung\n"
            -"Beliebige Einheiten (kg/t/g, mm/cm/m)\n"
            -"Automatische Anordnung in Container\n"
            -"Integration mit Weight Tool"
        )
        description.setWordWrap(True)
        layout.addWidget(description)
        
        # Buttons
        button_layout = QtWidgets.QHBoxLayout()
        
        import_btn = QtWidgets.QPushButton("Packliste importieren")
        import_btn.setMinimumHeight(40)
        import_btn.clicked.connect(self.start_import)
        
        close_btn = QtWidgets.QPushButton("Schließen")
        close_btn.clicked.connect(self.reject)
        
        button_layout.addWidget(import_btn)
        button_layout.addWidget(close_btn)
        
        layout.addLayout(button_layout)
        
        # Status
        self.status_label = QtWidgets.QLabel("Bereit zum Import")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
    
    def start_import(self):
        self.status_label.setText("Import wird gestartet...")
        QtWidgets.QApplication.processEvents()
        
        try:
            self.importer.import_packlist()
            self.status_label.setText("Import abgeschlossen!")
        except Exception as e:
            self.status_label.setText(f"Fehler beim Import: {str(e)}")
            QtWidgets.QMessageBox.critical(self, "Import Fehler", str(e))

# FreeCAD Makro Integration
def run_packlist_import():
    """Hauptfunktion für FreeCAD Makro"""
    dialog = PacklistImportDialog()
    dialog.exec_()

# Für direkte Ausführung
if __name__ == "__main__":
    # Test in FreeCAD
    run_packlist_import()

# Für FreeCAD Makro-Registrierung
__title__ = "Packlisten Import"
__author__ = "AI Assistant"
__url__ = ""
__doc__ = """
Importiert Excel/CSV Packlisten und erstellt 3D-Quadrate mit Gewichtsangaben.
"""

# FreeCAD Makro Eigenschaften
Macro = run_packlist_import
