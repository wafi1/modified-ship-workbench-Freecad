#***************************************************************************
#*                                                                         *
#*   Copyright (c) 2011, 2016 Jose Luis Cercos Pita <jlcercos@gmail.com>   *
#*   Erweiterung 2025 für Import-Funktionen                                *
#*                                                                         *
#***************************************************************************

import os
import FreeCAD as App
import FreeCADGui as Gui
from FreeCAD import Units
from PySide import QtGui, QtCore
from . import Preview as PreviewDrawer
from . import Tools
from .. import Instance
from ..shipUtils import Locale
from ..shipUtils import Selection
import Mesh
import Points
import Part

# Import des ersten Panels für Zugriff auf importierte Geometrie
from . import TaskPanel as SelectionPanel


class TaskPanel:
    def __init__(self):
        """Constructor - ZWEITES Panel (L/B/T Eingabe mit Preview)"""
        self.name = "ship creation - dimensions"
        self.ui = os.path.join(os.path.dirname(__file__),
                               "../resources/ui/",
                               "TaskPanel_shipCreateShip.ui")
        self.form = Gui.PySideUic.loadUi(self.ui)
        self.preview = PreviewDrawer.Preview()
        self.imported_geometry = None
        self.geometry_type = None

    def accept(self):
        """Create the ship instance"""
        self.preview.clean()
        
        # Bestimme die zu verwendende Geometrie
        solids = self._get_geometry_for_ship()
        
        if not solids:
            QtGui.QMessageBox.critical(
                None,
                "Keine Geometrie",
                "Es konnte keine gültige Geometrie für die\n"
                "Schiffsinstanz gefunden werden.\n\n"
                "Bitte importieren Sie eine Geometrie oder\n"
                "wählen Sie ein Beispielschiff aus.")
            App.Console.PrintError("✗ Keine gültige Geometrie für Schiffsinstanz\n")
            return False
        
        try:
            # Schiffsinstanz erstellen
            App.Console.PrintMessage("\n" + "="*70 + "\n")
            App.Console.PrintMessage("ERSTELLE SCHIFFSINSTANZ...\n")
            App.Console.PrintMessage("="*70 + "\n")
            
            Tools.createShip(solids,
                             Locale.fromString(self.form.length.text()),
                             Locale.fromString(self.form.breadth.text()),
                             Locale.fromString(self.form.draft.text()))
            
            App.Console.PrintMessage("✓ Schiffsinstanz erfolgreich erstellt!\n")
            App.Console.PrintMessage("="*70 + "\n\n")
            
            # Importierte Geometrie aus dem ersten Panel löschen
            SelectionPanel.clear_imported_geometry()
            
            return True
            
        except Exception as e:
            App.Console.PrintError(f"✗ Fehler beim Erstellen der Schiffsinstanz: {e}\n")
            QtGui.QMessageBox.critical(
                None,
                "Fehler",
                f"Fehler beim Erstellen der Schiffsinstanz:\n\n{str(e)}")
            return False

    def reject(self):
        """Cancel the job"""
        self.preview.clean()
        # Importierte Geometrie löschen
        SelectionPanel.clear_imported_geometry()
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
        return False

    def helpRequested(self):
        pass

    def setupUi(self):
        """Create and configurate the user interface"""
        # Hole die Eingabefelder aus der UI
        self.form.length = self.widget(QtGui.QLineEdit, "length")
        self.form.breadth = self.widget(QtGui.QLineEdit, "breadth")
        self.form.draft = self.widget(QtGui.QLineEdit, "draft")
        
        # === IMPORTIERTE GEOMETRIE VOM ERSTEN PANEL HOLEN ===
        self.imported_geometry = SelectionPanel.get_imported_geometry()
        self.geometry_type = SelectionPanel.get_geometry_type()
        
        if self.imported_geometry:
            App.Console.PrintMessage(f"\n{'='*70}\n")
            App.Console.PrintMessage(f"VERWENDE IMPORTIERTE GEOMETRIE\n")
            App.Console.PrintMessage(f"{'='*70}\n")
            App.Console.PrintMessage(f"Typ: {self.geometry_type}\n")
            App.Console.PrintMessage(f"Objekt: {self.imported_geometry.Label}\n")
            
            # Abmessungen aus der importierten Geometrie ermitteln
            self._update_from_imported_geometry()
            
            # Info-Label hinzufügen
            info_text = (f"<b>Importierte Geometrie:</b> {self.imported_geometry.Label}<br>"
                        f"<b>Typ:</b> {self.geometry_type}")
            info_label = QtGui.QLabel(info_text)
            info_label.setStyleSheet("""
                QLabel {
                    background-color: #e8f4f8;
                    border: 2px solid #2a82da;
                    border-radius: 5px;
                    padding: 8px;
                    margin: 5px;
                }
            """)
            
            # Label am Anfang des Layouts einfügen
            layout = self.form.layout()
            if isinstance(layout, QtGui.QGridLayout):
                layout.addWidget(info_label, 0, 0, 1, 2)
            else:
                layout.insertWidget(0, info_label)
                
            App.Console.PrintMessage(f"{'='*70}\n\n")
        else:
            # Keine importierte Geometrie - benutze ausgewählte Solids
            App.Console.PrintMessage("→ Verwende ausgewählte Objekte oder Beispielschiff\n")
            if self.initValues():
                return True
        
        # Vorschau aktualisieren
        self.preview.update(self.L, self.B, self.T)
        
        # === SIGNAL-VERBINDUNGEN ===
        self.form.length.valueChanged.connect(self.onLength)
        self.form.breadth.valueChanged.connect(self.onBreadth)
        self.form.draft.valueChanged.connect(self.onDraft)
        
        return False

    def _get_geometry_for_ship(self):
        """Ermittelt die zu verwendende Geometrie"""
        if self.imported_geometry:
            App.Console.PrintMessage("→ Bereite importierte Geometrie vor...\n")
            return self._prepare_geometry_for_ship(self.imported_geometry)
        elif hasattr(self, 'solids') and self.solids:
            App.Console.PrintMessage("→ Verwende ausgewählte Solids...\n")
            return self.solids
        else:
            # Versuche ausgewählte Objekte zu verwenden
            App.Console.PrintMessage("→ Suche ausgewählte Objekte...\n")
            return Selection.get_solids()

    def _prepare_geometry_for_ship(self, geometry):
        """Bereitet importierte Geometrie für Tools.createShip() vor"""
        if not geometry:
            return []
        
        # Wenn es schon eine Liste ist
        if isinstance(geometry, list):
            return geometry
        
        # Einzelnes Objekt - behandle je nach Typ
        if self.geometry_type == "solid":
            App.Console.PrintMessage("  ✓ Solid-Geometrie bereit\n")
            return [geometry]
        
        elif self.geometry_type == "surface":
            App.Console.PrintWarning("  ⚠ Oberflächengeometrie (kein Volumen)\n")
            App.Console.PrintWarning("  → Versuche trotzdem zu verwenden...\n")
            return [geometry]
        
        elif self.geometry_type == "mesh":
            App.Console.PrintMessage("  → Konvertiere Mesh zu Solid...\n")
            try:
                shape = Part.Shape()
                shape.makeShapeFromMesh(geometry.Mesh.Topology, 0.1)
                if shape.isValid() and shape.Solids:
                    solid = App.ActiveDocument.addObject("Part::Feature", "Converted_Solid")
                    solid.Shape = shape
                    solid.Label = "Ship_Solid_from_Mesh"
                    App.Console.PrintMessage("  ✓ Mesh erfolgreich konvertiert\n")
                    return [solid]
                else:
                    raise Exception("Mesh konnte nicht in Solid konvertiert werden")
            except Exception as e:
                App.Console.PrintError(f"  ✗ Mesh-Konvertierung fehlgeschlagen: {e}\n")
                return []
        
        elif self.geometry_type == "points":
            App.Console.PrintError(
                "  ✗ Punktwolken können nicht direkt verwendet werden!\n")
            App.Console.PrintError(
                "  → Bitte konvertieren Sie die Punktwolke manuell:\n")
            App.Console.PrintError(
                "     1. Points Workbench öffnen\n")
            App.Console.PrintError(
                "     2. Points → Structured point cloud\n")
            App.Console.PrintError(
                "     3. Mesh zu Solid konvertieren\n")
            return []
        
        App.Console.PrintWarning(f"  ⚠ Unbekannter Geometrietyp: {self.geometry_type}\n")
        return []

    def _update_from_imported_geometry(self):
        """Aktualisiert die Eingabefelder basierend auf importierter Geometrie"""
        if not self.imported_geometry:
            return
        
        try:
            # Bounding Box bestimmen
            bbox = None
            
            if hasattr(self.imported_geometry, "Shape"):
                bbox = self.imported_geometry.Shape.BoundBox
            elif hasattr(self.imported_geometry, "Mesh"):
                bbox = self.imported_geometry.Mesh.BoundBox
            elif hasattr(self.imported_geometry, "Points"):
                points = self.imported_geometry.Points.Points
                if points:
                    xs = [p.x for p in points]
                    ys = [p.y for p in points]
                    zs = [p.z for p in points]
                    # Erstelle eine einfache BBox-Struktur
                    bbox = type('BBox', (), {
                        'XMin': min(xs), 'XMax': max(xs),
                        'YMin': min(ys), 'YMax': max(ys),
                        'ZMin': min(zs), 'ZMax': max(zs)
                    })()
            
            if not bbox:
                App.Console.PrintWarning("  ⚠ Konnte keine BoundingBox bestimmen\n")
                return
            
            # Abmessungen berechnen
            length = bbox.XMax - bbox.XMin
            breadth = max(bbox.YMax - bbox.YMin, abs(bbox.YMax), abs(bbox.YMin)) * 2
            depth = bbox.ZMax - bbox.ZMin
            
            # Setze Werte in die Eingabefelder
            qty = Units.Quantity(length, Units.Length)
            self.form.length.setText(qty.UserString)
            self.L = length / Units.Metre.Value
            
            qty = Units.Quantity(breadth, Units.Length)
            self.form.breadth.setText(qty.UserString)
            self.B = breadth / Units.Metre.Value
            
            # Draft = halbe Tiefe (typische Annahme)
            draft = depth * 0.5
            qty = Units.Quantity(draft, Units.Length)
            self.form.draft.setText(qty.UserString)
            self.T = draft / Units.Metre.Value
            
            # Bounds für Referenz speichern
            self.bounds = [length, breadth, depth]
            
            App.Console.PrintMessage(
                f"Abmessungen ermittelt:\n"
                f"  • Länge (L):  {length:.2f} m\n"
                f"  • Breite (B): {breadth:.2f} m\n"
                f"  • Tiefgang (T): {draft:.2f} m\n"
                f"  • Höhe gesamt: {depth:.2f} m\n")
            
        except Exception as e:
            App.Console.PrintError(f"✗ Fehler bei Dimensionsberechnung: {e}\n")
            import traceback
            App.Console.PrintError(traceback.format_exc())

    def getMainWindow(self):
        toplevel = QtGui.QApplication.topLevelWidgets()
        for i in toplevel:
            if i.metaObject().className() == "Gui::MainWindow":
                return i
        raise RuntimeError("No main window found")

    def widget(self, class_id, name):
        """Return the selected widget"""
        mw = self.getMainWindow()
        form = mw.findChild(QtGui.QWidget, "CreateShipTaskPanel")
        return form.findChild(class_id, name)

    def initValues(self):
        """Setup the initial values from selected solids"""
        self.solids = Selection.get_solids()
        if not self.solids:
            # Dummy-Werte für Vorschau (wenn nichts ausgewählt)
            self.bounds = [10.0, 2.0, 2.0]
            qty = Units.Quantity(self.bounds[0], Units.Length)
            self.form.length.setText(qty.UserString)
            self.L = self.bounds[0] / Units.Metre.Value
            qty = Units.Quantity(self.bounds[1], Units.Length)
            self.form.breadth.setText(qty.UserString)
            self.B = self.bounds[1] / Units.Metre.Value
            qty = Units.Quantity(self.bounds[2], Units.Length)
            self.form.draft.setText(qty.UserString)
            self.T = 0.5 * self.bounds[2] / Units.Metre.Value
            return False
        
        # Berechne Bounding Box aus ausgewählten Solids
        self.bounds = [0.0, 0.0, 0.0]
        bbox = self.solids[0].BoundBox
        minX, maxX = bbox.XMin, bbox.XMax
        minY, maxY = bbox.YMin, bbox.YMax
        minZ, maxZ = bbox.ZMin, bbox.ZMax
        
        for i in range(1, len(self.solids)):
            bbox = self.solids[i].BoundBox
            minX = min(minX, bbox.XMin)
            maxX = max(maxX, bbox.XMax)
            minY = min(minY, bbox.YMin)
            maxY = max(maxY, bbox.YMax)
            minZ = min(minZ, bbox.ZMin)
            maxZ = max(maxZ, bbox.ZMax)
        
        self.bounds[0] = maxX - minX
        self.bounds[1] = max(maxY - minY, abs(maxY), abs(minY))
        self.bounds[2] = maxZ - minZ

        qty = Units.Quantity(self.bounds[0], Units.Length)
        self.form.length.setText(qty.UserString)
        self.L = self.bounds[0] / Units.Metre.Value
        qty = Units.Quantity(self.bounds[1], Units.Length)
        self.form.breadth.setText(qty.UserString)
        self.B = self.bounds[1] / Units.Metre.Value
        qty = Units.Quantity(self.bounds[2], Units.Length)
        self.form.draft.setText(qty.UserString)
        self.T = 0.5 * self.bounds[2] / Units.Metre.Value
        
        App.Console.PrintMessage(
            f"Ausgewählte Objekte:\n"
            f"  • Anzahl: {len(self.solids)}\n"
            f"  • L: {self.L:.2f} m\n"
            f"  • B: {self.B:.2f} m\n"
            f"  • T: {self.T:.2f} m\n")
        
        return False

    def clampVal(self, widget, val_min, val_max, val):
        """Keine Begrenzung - Vertraue dem Ingenieur!"""
        return val

    def onData(self, widget, val_max):
        """Updates the 3D preview on data changes"""
        val_min = 0.001
        qty = Units.parseQuantity(Locale.fromString(widget.text()))
        try:
            val = qty.getValueAs('m').Value
        except ValueError:
            return
        return self.clampVal(widget, val_min, val_max, val)

    def onLength(self, value):
        """Answer to length changes"""
        L = self.onData(self.form.length,
                        self.bounds[0] / Units.Metre.Value)
        if L is not None:
            self.L = L
            self.preview.update(self.L, self.B, self.T)

    def onBreadth(self, value):
        """Answer to breadth changes"""
        B = self.onData(self.form.breadth,
                        self.bounds[1] / Units.Metre.Value)
        if B is not None:
            self.B = B
            self.preview.update(self.L, self.B, self.T)

    def onDraft(self, value):
        """Answer to draft changes"""
        T = self.onData(self.form.draft,
                        self.bounds[2] / Units.Metre.Value)
        if T is not None:
            self.T = T
            self.preview.update(self.L, self.B, self.T)


def createTask():
    """Erstellt das zweite TaskPanel (Preview)"""
    panel = TaskPanel()
    Gui.Control.showDialog(panel)
    if panel.setupUi():
        Gui.Control.closeDialog()
        return None
    return panel
