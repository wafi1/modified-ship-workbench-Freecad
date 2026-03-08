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
# TaskPanel.py - KORRIGIERTE VERSION mit Float-Handling

import os
import math
import FreeCAD as App
import FreeCADGui as Gui
from FreeCAD import Units
from PySide import QtGui, QtCore

# KORRIGIERT: Absoluter Import
try:
    from freecad.ship.shipSinkAndTrim.Tools import compute
    print("✓ TaskPanel: Imported compute from Tools")
except ImportError as e:
    print(f"✗ TaskPanel: Failed to import compute: {e}")
    import traceback
    traceback.print_exc()
    
    # Fallback: Versuche relativen Import
    try:
        from .Tools import compute
        print("✓ TaskPanel: Imported compute from .Tools (relative)")
    except ImportError as e2:
        print(f"✗ TaskPanel: Relative import also failed: {e2}")
        compute = None


class TaskPanel:
    def __init__(self):
        self.name = "ship equilibrium state plotter"
        
        # Create UI dynamically (no .ui file needed)
        self.form = self.create_ui()
        
        self.doc = App.ActiveDocument
        self.ship = None
        self.lc = None
        self.results_group = None
        
        # Store calculation results
        self.last_results = {}
        
        # Initialize
        self.initialize()
    
    def create_ui(self):
        """Create UI dynamically"""
        widget = QtGui.QWidget()
        layout = QtGui.QVBoxLayout()
        widget.setLayout(layout)
        
        # Title
        title = QtGui.QLabel("SHIP SINK AND TRIM ANALYSIS")
        title.setAlignment(QtCore.Qt.AlignCenter)
        title.setStyleSheet("font-weight: bold; font-size: 16px; color: #003366;")
        layout.addWidget(title)
        
        layout.addSpacing(10)
        
        # Ship selection
        ship_frame = QtGui.QGroupBox("Ship Selection")
        ship_layout = QtGui.QVBoxLayout()
        
        self.ship_label = QtGui.QLabel("No ship selected")
        self.ship_label.setStyleSheet("font-weight: bold; color: #666666;")
        ship_layout.addWidget(self.ship_label)
        
        ship_buttons = QtGui.QHBoxLayout()
        self.btn_find_ship = QtGui.QPushButton("Find Ship")
        self.btn_find_ship.clicked.connect(self.find_ship)
        ship_buttons.addWidget(self.btn_find_ship)
        
        self.btn_select_ship = QtGui.QPushButton("Select from Tree")
        self.btn_select_ship.clicked.connect(self.select_ship_from_tree)
        ship_buttons.addWidget(self.btn_select_ship)
        
        ship_layout.addLayout(ship_buttons)
        ship_frame.setLayout(ship_layout)
        layout.addWidget(ship_frame)
        
        layout.addSpacing(10)
        
        # Load Condition selection
        lc_frame = QtGui.QGroupBox("Load Condition")
        lc_layout = QtGui.QVBoxLayout()
        
        self.lc_label = QtGui.QLabel("No load condition selected")
        self.lc_label.setStyleSheet("font-weight: bold; color: #666666;")
        lc_layout.addWidget(self.lc_label)
        
        lc_buttons = QtGui.QHBoxLayout()
        self.btn_find_lc = QtGui.QPushButton("Find Load Condition")
        self.btn_find_lc.clicked.connect(self.find_load_condition_new)
        lc_buttons.addWidget(self.btn_find_lc)
        
        self.btn_select_lc = QtGui.QPushButton("Select from Tree")
        self.btn_select_lc.clicked.connect(self.select_lc_from_tree)
        lc_buttons.addWidget(self.btn_select_lc)
        
        self.btn_test_lc = QtGui.QPushButton("Test LC Format")
        self.btn_test_lc.clicked.connect(self.test_lc_format)
        lc_buttons.addWidget(self.btn_test_lc)
        
        lc_layout.addLayout(lc_buttons)
        lc_frame.setLayout(lc_layout)
        layout.addWidget(lc_frame)
        
        layout.addSpacing(10)
        
        # Calculation options
        options_frame = QtGui.QGroupBox("Calculation Options")
        options_layout = QtGui.QVBoxLayout()
        
        # Reference selection
        ref_layout = QtGui.QHBoxLayout()
        ref_layout.addWidget(QtGui.QLabel("Waterplane Reference:"))
        
        self.ref_combo = QtGui.QComboBox()
        self.ref_combo.addItem("At zero trim (horizontal)")
        self.ref_combo.addItem("At actual trim")
        ref_layout.addWidget(self.ref_combo)
        
        options_layout.addLayout(ref_layout)
        
        # Density
        density_layout = QtGui.QHBoxLayout()
        density_layout.addWidget(QtGui.QLabel("Water Density (kg/m³):"))
        
        self.density_spin = QtGui.QDoubleSpinBox()
        self.density_spin.setRange(900, 1100)
        self.density_spin.setValue(1025.0)
        self.density_spin.setDecimals(1)
        self.density_spin.setSuffix(" kg/m³")
        density_layout.addWidget(self.density_spin)
        
        options_layout.addLayout(density_layout)
        options_frame.setLayout(options_layout)
        layout.addWidget(options_frame)
        
        layout.addSpacing(10)
        
        # Calculate button
        self.calc_button = QtGui.QPushButton("CALCULATE EQUILIBRIUM")
        self.calc_button.setStyleSheet(
            "QPushButton {"
            "background-color: #0066cc;"
            "color: white;"
            "font-weight: bold;"
            "padding: 8px;"
            "border-radius: 4px;"
            "}"
            "QPushButton:hover {"
            "background-color: #0055aa;"
            "}"
            "QPushButton:disabled {"
            "background-color: #cccccc;"
            "color: #666666;"
            "}"
        )
        self.calc_button.clicked.connect(self.calculate)
        self.calc_button.setEnabled(False)
        layout.addWidget(self.calc_button)
        
        layout.addSpacing(10)
        
        # Results display
        results_frame = QtGui.QGroupBox("Results")
        results_layout = QtGui.QVBoxLayout()
        
        self.results_text = QtGui.QTextEdit()
        self.results_text.setReadOnly(True)
        self.results_text.setMaximumHeight(250)
        self.results_text.setStyleSheet(
            "background-color: #f8f8f8;"
            "border: 1px solid #cccccc;"
            "padding: 5px;"
            "font-family: monospace;"
        )
        results_layout.addWidget(self.results_text)
        
        results_frame.setLayout(results_layout)
        layout.addWidget(results_frame)
        
        layout.addSpacing(10)
        
        # Status bar
        self.status_label = QtGui.QLabel("Ready")
        self.status_label.setAlignment(QtCore.Qt.AlignCenter)
        self.status_label.setStyleSheet(
            "background-color: #e8e8e8;"
            "padding: 4px;"
            "border: 1px solid #cccccc;"
        )
        layout.addWidget(self.status_label)
        
        # Add stretch at the end
        layout.addStretch()
        
        return widget
    
    def initialize(self):
        """Initialize the task panel"""
        self.update_status("Initializing...")
        
        # Try to find ship and load condition automatically
        if self.find_ship() and self.find_load_condition_new():
            self.calc_button.setEnabled(True)
            self.update_status("Ready to calculate")
        else:
            self.update_status("Please select ship and load condition")
    
    def find_ship(self):
        """Find ship object in document"""
        self.update_status("Looking for ship...")
        
        # Look for objects with 'Ship' in name or label
        for obj in self.doc.Objects:
            if 'Ship' in obj.Label or 'Ship' in obj.Name:
                self.ship = obj
                self.ship_label.setText(f"Ship: {obj.Label}")
                self.ship_label.setStyleSheet("font-weight: bold; color: #006600;")
                self.update_status(f"Found ship: {obj.Label}")
                return True
        
        # Check for objects with shape
        for obj in self.doc.Objects:
            if hasattr(obj, 'Shape') and obj.Shape:
                bbox = obj.Shape.BoundBox
                if bbox.XLength > bbox.YLength * 2:  # Probably a ship
                    self.ship = obj
                    self.ship_label.setText(f"Ship (auto-detected): {obj.Label}")
                    self.ship_label.setStyleSheet("font-weight: bold; color: #cc6600;")
                    self.update_status(f"Auto-detected ship: {obj.Label}")
                    return True
        
        self.ship_label.setText("No ship found")
        self.ship_label.setStyleSheet("font-weight: bold; color: #cc0000;")
        self.update_status("No ship found")
        return False
    
    def select_ship_from_tree(self):
        """Let user select ship from tree view"""
        selection = Gui.Selection.getSelection()
        if selection:
            obj = selection[0]
            self.ship = obj
            self.ship_label.setText(f"Ship: {obj.Label}")
            self.ship_label.setStyleSheet("font-weight: bold; color: #006600;")
            self.update_status(f"Selected ship: {obj.Label}")
            self.check_ready()
        else:
            QtGui.QMessageBox.warning(None, "No Selection", "Please select a ship object first")
    
    def find_load_condition_new(self):
        """Find load condition spreadsheet using NEW format detection"""
        self.update_status("Looking for load condition...")
        
        best_lc = None
        best_score = 0
        
        for obj in self.doc.Objects:
            if hasattr(obj, 'TypeId') and 'Spreadsheet' in obj.TypeId:
                score = 0
                
                try:
                    # Check D4 for mass
                    d4 = obj.get('D4')
                    if d4:
                        try:
                            mass = float(d4)
                            if mass > 0:
                                score += 3
                        except:
                            pass
                    
                    # Check E5, F5, G5 for COG
                    for cell in ['E5', 'F5', 'G5']:
                        val = obj.get(cell)
                        if val:
                            try:
                                float(val)
                                score += 1
                            except:
                                pass
                    
                    # Check for header
                    a1 = obj.get('A1')
                    if a1 and 'LOAD CONDITION' in str(a1).upper():
                        score += 2
                    
                except:
                    continue
                
                if score > best_score:
                    best_score = score
                    best_lc = obj
        
        if best_lc and best_score >= 3:
            self.lc = best_lc
            self.lc_label.setText(f"Load Condition: {best_lc.Label}")
            self.lc_label.setStyleSheet("font-weight: bold; color: #006600;")
            
            # Show brief data info
            try:
                mass = float(best_lc.get('D4'))
                self.update_status(f"Found LC: {best_lc.Label} (Mass: {mass/1000:.1f} t)")
            except:
                self.update_status(f"Found LC: {best_lc.Label}")
            
            return True
        
        self.lc_label.setText("No load condition found")
        self.lc_label.setStyleSheet("font-weight: bold; color: #cc0000;")
        self.update_status("No load condition found")
        return False
    
    def get_cell_value(self, cell):
        """Get value from current LC cell"""
        if not self.lc:
            return None
        try:
            val = self.lc.get(cell)
            if val:
                return str(val)
        except:
            pass
        return None
    
    def test_lc_format(self):
        """Test the format of the selected load condition"""
        if not self.lc:
            QtGui.QMessageBox.warning(None, "No LC", "No load condition selected")
            return
        
        test_results = []
        
        # Check key cells
        key_cells = [
            ('A1', 'Header'),
            ('D4', 'Total mass (kg)'),
            ('E5', 'COG X (m)'),
            ('F5', 'COG Y (m)'),
            ('G5', 'COG Z (m)'),
            ('K4', 'Free surface')
        ]
        
        for cell, description in key_cells:
            val = self.get_cell_value(cell)
            if val:
                test_results.append(f"✓ {cell} ({description}): {val}")
            else:
                test_results.append(f"✗ {cell} ({description}): EMPTY")
        
        message = f"Load Condition Format Test: {self.lc.Label}\n\n"
        message += "\n".join(test_results)
        
        QtGui.QMessageBox.information(None, "LC Format Test", message)
    
    def select_lc_from_tree(self):
        """Let user select load condition from tree view"""
        selection = Gui.Selection.getSelection()
        if selection:
            obj = selection[0]
            if hasattr(obj, 'TypeId') and 'Spreadsheet' in obj.TypeId:
                self.lc = obj
                self.lc_label.setText(f"Load Condition: {obj.Label}")
                self.lc_label.setStyleSheet("font-weight: bold; color: #006600;")
                self.update_status(f"Selected load condition: {obj.Label}")
                self.check_ready()
            else:
                QtGui.QMessageBox.warning(None, "Invalid Selection", "Please select a spreadsheet")
        else:
            QtGui.QMessageBox.warning(None, "No Selection", "Please select a load condition spreadsheet first")
    
    def check_ready(self):
        """Check if ready to calculate"""
        if self.ship and self.lc:
            self.calc_button.setEnabled(True)
            self.update_status("Ready to calculate")
        else:
            self.calc_button.setEnabled(False)

    def format_quantity(self, value, unit=None, default_format=None):
        """Format a value that could be a float or a Quantity"""
        if hasattr(value, 'UserString'):
            # Es ist eine Quantity
            return value.UserString
        else:
            # Es ist ein float oder int
            if unit:
                # Füge die Einheit hinzu
                if unit == 'kg':
                    if value > 1000:
                        return f"{value/1000:.2f} t"
                    else:
                        return f"{value:.2f} kg"
                elif unit == 'm':
                    return f"{value:.3f} m"
                elif unit == 'deg':
                    return f"{value:.2f} deg"
                else:
                    return f"{value:.3f} {unit}"
            elif default_format:
                # Verwende das angegebene Format
                return default_format.format(value)
            else:
                # Standardformat
                return str(value)
    
    def calculate(self):
        """Perform the equilibrium calculation"""
        # Lokaler Import (vermeidet UnboundLocalError)
        try:
            from freecad.ship.shipSinkAndTrim.Tools import compute
        except ImportError:
            try:
                from .Tools import compute
            except ImportError as e:
                QtGui.QMessageBox.critical(None, "Error", f"Cannot import Tools module: {e}")
                self.update_status("Import error")
                return
        
        if not self.ship or not self.lc:
            QtGui.QMessageBox.critical(None, "Error", "Ship or load condition not selected!")
            return
        
        if not hasattr(self.ship, 'Shape') or not self.ship.Shape:
            QtGui.QMessageBox.critical(None, "Error", "Selected ship has no geometry!")
            return
        
        self.update_status("Calculating...")
        self.calc_button.setEnabled(False)
        
        try:
            # Clear previous results
            self.clear_previous_results()
            
            # Get options
            fs_ref = self.ref_combo.currentIndex() == 0
            density = self.density_spin.value()
            
            # Run calculation - ALLE Werte kommen aus Tools.py
            result_tuple = compute(
                self.lc, 
                fs_ref=fs_ref,
                ship_obj=self.ship,
                doc=self.doc
            )
            
            # Entpacke Ergebnisse (6 Rückgabewerte)
            if len(result_tuple) == 6:
                group, draft, trim, displacement, vis_objects, result_dict = result_tuple
            else:
                # Fallback für alte Version
                group, draft, trim, displacement, vis_objects = result_tuple[:5]
                result_dict = None
            
            if draft is None or result_dict is None:
                self.results_text.setText("ERROR: Calculation failed")
                return
            
            self.results_group = group
            
            # Ergebnis-Text zusammenstellen
            results_text = "EQUILIBRIUM CALCULATION RESULTS\n"
            results_text += "=" * 50 + "\n\n"
            
            # Hauptwerte aus Tools.py - MIT FLOAT-HANDLING
            results_text += f"Displacement: {self.format_quantity(displacement, 'kg')}\n"
            results_text += f"Draft:        {self.format_quantity(draft, 'm')}\n"
            results_text += f"Trim:         {self.format_quantity(trim, 'deg')}\n\n"
            
            # Detaillierte Werte aus result_dict (wenn verfügbar)
            if result_dict:
                results_text += "Hydrostatic Data:\n"
                
                # LCB
                lcb_val = result_dict.get('lcb', 0)
                results_text += f"  LCB:  {self.format_quantity(lcb_val, 'm')}\n"
                
                # VCB
                vcb_val = result_dict.get('vcb', 0)
                results_text += f"  VCB:  {self.format_quantity(vcb_val, 'm')}\n"
                
                # KB
                kb_val = result_dict.get('kb', 0)
                results_text += f"  KB:   {self.format_quantity(kb_val, 'm')}\n"
                
                # BMt
                bmt_val = result_dict.get('bmt', 0)
                results_text += f"  BMt:  {self.format_quantity(bmt_val, 'm')}\n"
                
                # KMt
                km_val = result_dict.get('km', 0)
                results_text += f"  KMt:  {self.format_quantity(km_val, 'm')}\n"
                
                # GM und Stabilität
                gm = result_dict.get('gm')
                if gm is not None:
                    gm_val = gm.Value if hasattr(gm, 'Value') else gm
                    results_text += f"  GMt:  {self.format_quantity(gm, 'm')}\n"
                    results_text += "\nStability Assessment:\n"
                    if gm_val > 0.5:
                        results_text += "  ✓ GOOD STABILITY (GM > 0.5m)\n"
                    elif gm_val > 0.15:
                        results_text += "  ⚠ ACCEPTABLE STABILITY (GM > 0.15m)\n"
                    elif gm_val > 0:
                        results_text += "  ⚠ MARGINAL STABILITY (GM < 0.15m)\n"
                    else:
                        results_text += "  ✗ UNSTABLE (Negative GM!)\n"
            
            # Load Condition Daten anzeigen
            try:
                mass_kg = float(self.lc.get('D4'))
                cog_x = float(self.lc.get('E5'))
                cog_y = float(self.lc.get('F5'))
                cog_z = float(self.lc.get('G5'))
                
                results_text += "\nLoad Condition Input:\n"
                results_text += f"  Mass:  {self.format_quantity(mass_kg, 'kg')}\n"
                results_text += f"  LCG:   {cog_x:.3f} m\n"
                results_text += f"  TCG:   {cog_y:.3f} m\n"
                results_text += f"  VCG:   {cog_z:.3f} m\n"
                
            except Exception as e:
                print(f"Could not read LC details: {e}")
            
            self.results_text.setText(results_text)
            self.update_status("Calculation complete")
            
            # Zoom to fit
            Gui.SendMsgToActiveView("ViewFit")
            
        except Exception as e:
            error_msg = f"Calculation error:\n{str(e)}"
            print(error_msg)
            import traceback
            traceback.print_exc()
            
            self.results_text.setText(f"ERROR:\n{error_msg}")
            self.update_status("Error in calculation")
        finally:
            self.calc_button.setEnabled(True)

    
    def clear_previous_results(self):
        """Clear previous calculation results"""
        # Remove visualization objects
        for obj in self.doc.Objects:
            if any(x in obj.Name for x in ['SinkAndTrim', 'Waterplane', 'Ship_Equilibrium', 'COG', 'Buoyancy']):
                try:
                    self.doc.removeObject(obj.Name)
                except:
                    pass
        
        self.results_group = None
    
    def update_status(self, message):
        """Update status label"""
        self.status_label.setText(message)
        QtGui.QApplication.processEvents()
    
    # Required FreeCAD TaskPanel methods
    def accept(self):
        self.clear_previous_results()
        return True
    
    def reject(self):
        self.clear_previous_results()
        return True
    
    def clicked(self, index):
        pass
    
    def open(self):
        pass
    
    def needsFullSpace(self):
        return True
    
    def isAllowedAlterSelection(self):
        return True
    
    def isAllowedAlterView(self):
        return True
    
    def isAllowedAlterDocument(self):
        return True


def createTask():
    """Create and show the task panel"""
    try:
        panel = TaskPanel()
        return panel
    except Exception as e:
        print(f"Error creating task panel: {e}")
        import traceback
        traceback.print_exc()
        return None
