#***************************************************************************
#*                                                                         *
#*   Copyright (c) 2011, 2016                                              *
#*   Jose Luis Cercos Pita <jlcercos@gmail.com>                            *
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
import FreeCAD as App
import FreeCADGui as Gui
from FreeCAD import Units
from PySide import QtGui, QtCore
from ..shipUtils import Selection


class TaskPanel:
    def __init__(self):
        """Constructor"""
        self.name   = "ship mesh association"
        self.ships  = []
        self.meshes = []   # FIX 3: komplette Liste, nicht nur Selektion
        self.lc_data = None  # NEU: LoadCondition Daten

        try:
            self.ui   = ":/ui/TaskPanel_seakeepingSetMesh.ui"
            self.form = Gui.PySideUic.loadUi(self.ui)
        except Exception:
            try:
                base_path = os.path.dirname(__file__)
                ui_path   = os.path.join(base_path, "..", "resources", "ui",
                                         "TaskPanel_seakeepingSetMesh.ui")
                self.ui   = ui_path
                self.form = Gui.PySideUic.loadUi(ui_path)
            except Exception as e:
                App.Console.PrintWarning(f"Could not load UI file: {e}\n")
                self.form = self._create_fallback_ui()

    # ------------------------------------------------------------------
    # NEU: LoadCondition Daten auslesen
    # ------------------------------------------------------------------

    def _find_loadcondition(self):
        """Findet das LoadCondition-Spreadsheet im Dokument."""
        doc = App.ActiveDocument
        if not doc:
            return None
        
        for obj in doc.Objects:
            if (hasattr(obj, 'TypeId') and 
                obj.TypeId == 'Spreadsheet::Sheet' and 
                'LoadCondition' in obj.Label):
                return obj
        
        # Fallback: suche nach Namen
        for obj in doc.Objects:
            if obj.Name == 'LoadCondition' or obj.Label == 'LoadCondition':
                return obj
        
        return None

    def _read_loadcondition_data(self):
        """Liest Daten aus dem LoadCondition-Spreadsheet."""
        lc = self._find_loadcondition()
        if not lc:
            self.lc_data = None
            return
            
        def _cell(cell, default=0.0):
            try:
                val = lc.get(cell)
                if val is None or val == '':
                    return default
                return float(str(val).replace(',', '.').strip())
            except Exception:
                return default
        
        # KORRIGIERTE ZELLREFERENZEN gemäß Vorgabe:
        # Mass: D4, Draft: E4 (oder D6 als Fallback)
        # COG: E5 (x), F5 (y), G5 (z)
        # KM: F4, GM: G4
        
        self.lc_data = {
            'mass': _cell('D4', 0.0),
            'draft': _cell('E4', 0.0),
            'cog_x': _cell('E5', 0.0),
            'cog_y': _cell('F5', 0.0),
            'cog_z': _cell('G5', 0.0),
            'km': _cell('F4', 0.0),
            'gm': _cell('G4', 0.0),
        }
        
        # Fallback für Draft: D6 wenn E4 leer
        if self.lc_data['draft'] == 0.0:
            self.lc_data['draft'] = _cell('D6', 0.0)

    # ------------------------------------------------------------------
    # Fallback-UI
    # ------------------------------------------------------------------

    def _create_fallback_ui(self):
        widget = QtGui.QWidget()
        layout = QtGui.QVBoxLayout()
        widget.setLayout(layout)

        title = QtGui.QLabel("MESH ASSOCIATION FOR SEAKEEPING")
        title.setAlignment(QtCore.Qt.AlignCenter)
        title.setStyleSheet(
            "font-weight: bold; font-size: 13px; padding: 6px; "
            "background: #1a3a5c; color: white; border-radius: 4px;")
        layout.addWidget(title)
        layout.addSpacing(12)

        # NEU: LoadCondition Info Anzeige
        lc_grp = QtGui.QGroupBox("Load Condition Data")
        lc_form = QtGui.QFormLayout()
        lc_grp.setLayout(lc_form)

        self.lc_status = QtGui.QLabel("Checking...")
        self.lc_status.setStyleSheet("color: gray; font-size: 10px;")
        lc_form.addRow("Status:", self.lc_status)

        self.lc_mass = QtGui.QLabel("—")
        lc_form.addRow("Mass (D4):", self.lc_mass)
        
        self.lc_draft = QtGui.QLabel("—")
        lc_form.addRow("Draft (E4):", self.lc_draft)
        
        self.lc_cog = QtGui.QLabel("—")
        lc_form.addRow("COG (E5/F5/G5):", self.lc_cog)
        
        self.lc_gm = QtGui.QLabel("—")
        lc_form.addRow("GM (G4):", self.lc_gm)

        layout.addWidget(lc_grp)

        # Mesh-Dropdown (FIX 3: alle Mesh::Feature im Dokument)
        mesh_grp  = QtGui.QGroupBox("Mesh")
        mesh_form = QtGui.QFormLayout()
        mesh_grp.setLayout(mesh_form)

        self.mesh_combo = QtGui.QComboBox()
        self.mesh_combo.currentIndexChanged.connect(self._on_mesh_changed)
        mesh_form.addRow("Mesh:", self.mesh_combo)

        self.mesh_info = QtGui.QLabel("—")
        self.mesh_info.setStyleSheet("color: gray; font-size: 10px;")
        mesh_form.addRow("Info:", self.mesh_info)

        layout.addWidget(mesh_grp)

        # Ship-Dropdown
        ship_grp  = QtGui.QGroupBox("Ship")
        ship_form = QtGui.QFormLayout()
        ship_grp.setLayout(ship_form)

        self.ship_combo = QtGui.QComboBox()
        self.ship_combo.currentIndexChanged.connect(self._on_ship_changed)
        ship_form.addRow("Ship:", self.ship_combo)

        self.ship_status = QtGui.QLabel("—")
        self.ship_status.setStyleSheet("color: gray; font-size: 10px;")
        ship_form.addRow("Current mesh:", self.ship_status)

        layout.addWidget(ship_grp)
        layout.addStretch()
        return widget

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_mesh_changed(self, idx):
        if not (0 <= idx < len(self.meshes)):
            return
        mesh = self.meshes[idx]
        try:
            pts  = mesh.Mesh.CountPoints
            face = mesh.Mesh.CountFacets
            self.mesh_info.setText(f"{pts:,} points  |  {face:,} faces")
            self.mesh_info.setStyleSheet("color: green; font-size: 10px;")
        except Exception:
            self.mesh_info.setText("(info unavailable)")

    def _on_ship_changed(self, idx):
        if not (0 <= idx < len(self.ships)):
            return
        ship = self.ships[idx]
        if hasattr(ship, 'SeakeepingMesh') and ship.SeakeepingMesh:
            names = ', '.join(m.Label for m in ship.SeakeepingMesh if m)
            self.ship_status.setText(f"Already: {names}")
            self.ship_status.setStyleSheet("color: green; font-size: 10px;")
        else:
            self.ship_status.setText("None assigned yet")
            self.ship_status.setStyleSheet("color: gray; font-size: 10px;")

    # ------------------------------------------------------------------
    # accept / reject
    # ------------------------------------------------------------------

    def accept(self):
        # Mesh auslesen
        if hasattr(self, 'mesh_combo'):
            idx = self.mesh_combo.currentIndex()
            if not (0 <= idx < len(self.meshes)):
                App.Console.PrintError("No mesh selected.\n")
                return False
            mesh = self.meshes[idx]
        else:
            # Original .ui: mesh wurde in initValues gesetzt
            if not hasattr(self, 'mesh') or self.mesh is None:
                App.Console.PrintError("No mesh available.\n")
                return False
            mesh = self.mesh

        # Ship auslesen
        if hasattr(self, 'ship_combo'):
            idx = self.ship_combo.currentIndex()
        else:
            idx = self.form.ship.currentIndex()
        if not (0 <= idx < len(self.ships)):
            App.Console.PrintError("No ship selected.\n")
            return False
        ship = self.ships[idx]

        # FIX 1: Property anlegen falls noch nicht vorhanden
        if 'SeakeepingMesh' not in ship.PropertiesList:
            ship.addProperty(
                "App::PropertyLinkList",
                "SeakeepingMesh",
                "Seakeeping",
                "Hull mesh for Capytaine BEM seakeeping analysis"
            )

        # FIX 2a: Property-Name ist SeakeepingMesh, NICHT Mesh
        # FIX 2b: Objekt-Referenz übergeben, NICHT String-Name
        ship.SeakeepingMesh = [mesh]    # war: ship.Mesh = [self.mesh.Name]

        mesh.Visibility = False
        App.ActiveDocument.recompute()

        App.Console.PrintMessage(
            f"Mesh '{mesh.Label}' -> Ship '{ship.Label}' "
            f"[property: SeakeepingMesh]\n")
        
        # NEU: Hinweis auf LoadCondition Daten
        if self.lc_data and self.lc_data['mass'] > 0:
            App.Console.PrintMessage(
                f"  LoadCondition available: m={self.lc_data['mass']:.0f}kg, "
                f"T={self.lc_data['draft']:.2f}m, "
                f"GM={self.lc_data['gm']:.3f}m\n")
        
        return True

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
        return True     # FIX 4: War False → Dokument konnte nicht geändert werden!

    def helpRequested(self):
        pass

    def setupUi(self):
        if self.initValues():
            return True
        return False

    def initValues(self):
        doc = App.ActiveDocument
        if doc is None:
            App.Console.PrintError("No active document.\n")
            return True

        # NEU: LoadCondition Daten laden
        self._read_loadcondition_data()
        if hasattr(self, 'lc_status'):
            if self.lc_data and self.lc_data['mass'] > 0:
                self.lc_status.setText("✓ Found")
                self.lc_status.setStyleSheet("color: green; font-weight: bold;")
                
                self.lc_mass.setText(f"{self.lc_data['mass']:,.0f} kg")
                self.lc_draft.setText(f"{self.lc_data['draft']:.2f} m")
                self.lc_cog.setText(
                    f"({self.lc_data['cog_x']:.2f}, "
                    f"{self.lc_data['cog_y']:.2f}, "
                    f"{self.lc_data['cog_z']:.2f}) m"
                )
                self.lc_gm.setText(f"{self.lc_data['gm']:.3f} m")
                
                App.Console.PrintMessage(
                    f"LoadCondition found: {self.lc_data['mass']:.0f}kg, "
                    f"T={self.lc_data['draft']:.2f}m\n")
            else:
                self.lc_status.setText("❌ Not found")
                self.lc_status.setStyleSheet("color: red; font-weight: bold;")
                App.Console.PrintWarning("No LoadCondition spreadsheet found!\n")

        # FIX 3: Meshes aus dem Dokument laden, NICHT aus Selektion.
        # Selection.get_meshes() liefert auch Weights/Tanks → falsches Objekt,
        # daher direkt alle Mesh::Feature-Objekte aus dem Dokument sammeln.
        self.meshes = []
        for obj in doc.Objects:
            if 'Mesh' in getattr(obj, 'TypeId', ''):
                try:
                    if obj.Mesh.CountPoints > 0:
                        self.meshes.append(obj)
                except Exception:
                    pass

        if not self.meshes:
            App.Console.PrintError(
                "No mesh objects found in document.\n"
                "Please run 'Create Capytaine Mesh' first.\n")
            return True

        # Ships
        self.ships = Selection.get_doc_ships()
        if not self.ships:
            App.Console.PrintError("No ship objects found in document.\n")
            return True

        # Fallback-UI befüllen
        if hasattr(self, 'mesh_combo'):
            self.mesh_combo.blockSignals(True)
            self.mesh_combo.clear()
            for m in self.meshes:
                try:
                    pts  = m.Mesh.CountPoints
                    face = m.Mesh.CountFacets
                    self.mesh_combo.addItem(
                        f"{m.Label}  ({pts:,} pts, {face:,} faces)")
                except Exception:
                    self.mesh_combo.addItem(m.Label)
            self.mesh_combo.setCurrentIndex(0)
            self.mesh_combo.blockSignals(False)
            self._on_mesh_changed(0)

            self.ship_combo.blockSignals(True)
            self.ship_combo.clear()
            for s in self.ships:
                self.ship_combo.addItem(s.Label)
            self.ship_combo.setCurrentIndex(0)
            self.ship_combo.blockSignals(False)
            self._on_ship_changed(0)

        else:
            # Original-UI: self.mesh für accept() setzen
            self.mesh = self.meshes[0]
            try:
                ship_combo = self.form.findChild(QtGui.QComboBox, "ship")
                if ship_combo:
                    ship_combo.clear()
                    try:
                        icon = QtGui.QIcon(
                            QtGui.QPixmap(":/icons/Ship_Instance.svg"))
                    except Exception:
                        icon = QtGui.QIcon()
                    for ship in self.ships:
                        ship_combo.addItem(icon, ship.Label)
                    ship_combo.setCurrentIndex(0)
            except Exception as e:
                App.Console.PrintWarning(
                    f"Could not fill ship combo in .ui form: {e}\n")

        # Falls ein Mesh in der Selektion ist → bevorzugen
        try:
            for sel_obj in Gui.Selection.getSelection():
                for i, m in enumerate(self.meshes):
                    if m.Name == sel_obj.Name:
                        if hasattr(self, 'mesh_combo'):
                            self.mesh_combo.setCurrentIndex(i)
                        else:
                            self.mesh = m
                        break
        except Exception:
            pass

        App.Console.PrintMessage(
            f"SetMesh: {len(self.ships)} ship(s), "
            f"{len(self.meshes)} mesh(es) found.\n")
        return False


# ---------------------------------------------------------------------------

def createTask():
    try:
        panel = TaskPanel()
        Gui.Control.showDialog(panel)
        if panel.setupUi():
            Gui.Control.closeDialog()
            return None
        return panel
    except Exception as e:
        App.Console.PrintError(f"Error creating SetMesh panel: {e}\n")
        import traceback
        traceback.print_exc()
        return None
