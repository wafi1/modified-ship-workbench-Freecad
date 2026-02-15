#***************************************************************************
#*                                                                         *
#*   Copyright (c) 2011, 2016 Jose Luis Cercos Pita <jlcercos@gmail.com>   *
#*   Modified to support new LoadCondition format                          *
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
import math
import FreeCAD as App
import FreeCADGui as Gui
from FreeCAD import Units, Vector
from PySide import QtGui, QtCore
from . import PlotAux
from . import Tools
from ..shipUtils import Selection


class TaskPanel:
    def __init__(self):
        self.name = "ship GZ stability curve plotter"
        self.ui = os.path.join(os.path.dirname(__file__),
                               "../resources/ui/",
                               "TaskPanel_shipGZ.ui")
        self.form = Gui.PySideUic.loadUi(self.ui)


    def accept(self):
        if self.lc is None:
            return False
        self.form.group_pbar.show()
        self.save()

        roll = Units.parseQuantity(self.form.angle.text())
        n_points = self.form.n_points.value()
        var_trim = self.form.var_trim.isChecked()
        self.form.pbar.setMinimum(0)
        self.form.pbar.setMaximum(n_points)
        self.form.pbar.setValue(0)

        # NEW FORMAT: Read data from LoadCondition spreadsheet
        try:
            # Try to read from new format (fixed cells)
            total_mass_kg = float(self.lc.get('D4'))
            W = Units.parseQuantity("{} kg".format(total_mass_kg)) * Tools.G
            
            cog_x = float(self.lc.get('E5'))
            cog_y = float(self.lc.get('F5'))
            cog_z = float(self.lc.get('G5'))
            COG = Vector(cog_x, cog_y, cog_z)
            
            App.Console.PrintMessage("Using NEW LoadCondition format:\n")
            App.Console.PrintMessage("  Mass: {} kg, COG: ({:.3f}, {:.3f}, {:.3f}) m\n".format(
                total_mass_kg, cog_x, cog_y, cog_z))
            
            use_new_format = True
            
        except Exception as e:
            # Fallback to old format
            App.Console.PrintWarning("Cannot read new format, trying old format: {}\n".format(str(e)))
            try:
                COG, W = Tools.weights_cog(self.weights)
                TW = Units.parseQuantity("0 kg")
                VOLS = []
                for t in self.tanks:
                    vol = t[0].Proxy.getVolume(t[0], t[2])
                    VOLS.append(vol)
                    TW += vol * t[1]
                TW = TW * Tools.G
                use_new_format = False
            except Exception as e2:
                App.Console.PrintError("Error reading LoadCondition: {}\n".format(str(e2)))
                return False

        # Start traversing the queried angles
        self.loop = QtCore.QEventLoop()
        self.timer = QtCore.QTimer()
        self.timer.setSingleShot(True)
        QtCore.QObject.connect(self.timer,
                               QtCore.SIGNAL("timeout()"),
                               self.loop,
                               QtCore.SLOT("quit()"))
        self.running = True
        rolls = []
        gzs = []
        drafts = []
        trims = []
        plt = None
        
        for i in range(n_points):
            App.Console.PrintMessage("{0} / {1}\n".format(i + 1, n_points))
            self.form.pbar.setValue(i + 1)
            rolls.append(roll * i / float(n_points - 1))
            
            # Use appropriate solve function based on format
            if use_new_format:
                point = Tools.solve_point_direct(W, COG, self.ship, rolls[-1], var_trim)
            else:
                point = Tools.solve_point(W, COG, TW, VOLS, self.ship, self.tanks,
                                          rolls[-1], var_trim)
            
            if point is None:
                gzs.append(Units.Quantity(0, Units.Length))
                drafts.append(Units.Quantity(0, Units.Length))
                trims.append(Units.Quantity(0, Units.Angle))
            else:
                gzs.append(point[0])
                drafts.append(point[1])
                trims.append(point[2])
            
            if plt is None:
                # Create lc_info for SOLAS analysis
                lc_info = {
                    'name': self.lc.Label,
                    'mass': total_mass_kg,
                    'cog': [cog_x, cog_y, cog_z],
                    'ship_label': self.ship.Label if self.ship else 'Unknown',
                    'use_new_format': use_new_format
                }
                plt = PlotAux.Plot(rolls, gzs, drafts, trims, lc_info)
            else:
                plt.update(rolls, gzs, drafts, trims)
            
            self.timer.start(0.0)
            self.loop.exec_()
            if(not self.running):
                break
        
        # Perform SOLAS analysis after all points are calculated
        if use_new_format and gzs and all(gz.Value > 0 for gz in gzs if hasattr(gz, 'Value')):
            try:
                # Call the enhanced gz() function that returns SOLAS data
                points = []
                for gz_val, draft, trim_angle in zip(gzs, drafts, trims):
                    points.append((gz_val, draft, trim_angle))
                
                # Perform SOLAS analysis
                solas_data = Tools.analyze_solas_stability(points, rolls, self.ship, COG)
                
                # Add LoadCondition info to solas_data
                solas_data.update({
                    'lc_label': self.lc.Label,
                    'ship_label': self.ship.Label,
                    'total_mass_kg': total_mass_kg,
                    'cog_x': cog_x,
                    'cog_y': cog_y,
                    'cog_z': cog_z
                })
                
                # Print SOLAS report
                Tools.print_solas_report(solas_data)
                
                # Export SOLAS results to spreadsheet if plt has sheet
                if hasattr(plt, 'sheet') and plt.sheet:
                    self.export_solas_to_spreadsheet(plt.sheet, solas_data)
                    
            except Exception as e:
                App.Console.PrintWarning(f"SOLAS analysis failed: {e}\n")
                import traceback
                traceback.print_exc()
        
        return True
    
    def export_solas_to_spreadsheet(self, sheet, solas_data):
        """Export SOLAS results to existing spreadsheet"""
        try:
            # Start at column F to avoid overwriting original data
            col_offset = 6  # Column F
            
            # Header - keine Formeln, nur Text
            sheet.set(f"F1", "SOLAS/IMO STABILITY ANALYSIS")
            
            # Basic info
            sheet.set(f"F3", f"Ship: {solas_data.get('ship_label', 'N/A')}")
            sheet.set(f"F4", f"Load Condition: {solas_data.get('lc_label', 'N/A')}")
            sheet.set(f"F5", f"Total Mass: {solas_data.get('total_mass_kg', 0):.1f} kg")
            
            # Stability parameters
            sheet.set(f"F7", "STABILITY PARAMETERS:")
            sheet.set(f"F8", f"Max GZ: {solas_data.get('max_gz', 0):.3f} m")
            sheet.set(f"F9", f"Angle of Max GZ: {solas_data.get('max_gz_angle', 0):.1f} °")
            sheet.set(f"F10", f"Vanishing Angle: {solas_data.get('vanishing_angle', 0):.1f} °")
            sheet.set(f"F11", f"GZ at 30°: {solas_data.get('gz_at_30', 0):.3f} m")
            sheet.set(f"F12", f"Initial GM: {solas_data.get('GM0', 0):.3f} m")
            
            # Areas
            sheet.set(f"F14", "AREA UNDER GZ CURVE:")
            sheet.set(f"F15", f"0-30°: {solas_data.get('area_0_30', 0):.4f} m·rad")
            sheet.set(f"F16", f"0-40°: {solas_data.get('area_0_40', 0):.4f} m·rad")
            sheet.set(f"F17", f"30-40°: {solas_data.get('area_30_40', 0):.4f} m·rad")
            
            # SOLAS Criteria
            sheet.set(f"F19", "SOLAS/IMO CRITERIA:")
            row = 20
            
            criteria = solas_data.get('solas_criteria', {})
            for name, crit in criteria.items():
                status = "PASS" if crit.get('passed', False) else "FAIL"
                value = crit.get('value', 0)
                required = crit.get('required', 0)
                
                # Format name
                if name == 'area_0_30':
                    display_name = "Area 0-30°"
                elif name == 'area_0_40':
                    display_name = "Area 0-40°"
                elif name == 'area_30_40':
                    display_name = "Area 30-40°"
                elif name == 'gz_at_30':
                    display_name = "GZ at 30°"
                elif name == 'max_gz_angle':
                    display_name = "Max GZ Angle"
                elif name == 'GM0':
                    display_name = "Initial GM"
                else:
                    display_name = name.replace('_', ' ').title()
                
                sheet.set(f"F{row}", 
                         f"{display_name}: {value:.4f} / {required:.3f} ({status})")
                row += 1
            
            # Summary
            passed = solas_data.get('passed_count', 0)
            total = solas_data.get('total_criteria', 0)
            compliant = solas_data.get('compliant', False)
            
            sheet.set(f"F{row+1}", f"Summary: {passed}/{total} criteria passed")
            sheet.set(f"F{row+2}", 
                     "COMPLIANT" if compliant else "NON-COMPLIANT")
            
            # Recompute spreadsheet
            if hasattr(sheet, 'Document') and sheet.Document:
                sheet.Document.recompute()
                
            App.Console.PrintMessage(f"✓ SOLAS results exported to spreadsheet column F\n")
            
        except Exception as e:
            App.Console.PrintWarning(f"Could not export SOLAS results to spreadsheet: {e}\n")
            import traceback
            traceback.print_exc()



    def reject(self):
        if not self.ship:
            return False
        if self.running:
            self.running = False
            return
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
        self.form.angle = self.widget(QtGui.QLineEdit, "angle")
        self.form.n_points = self.widget(QtGui.QSpinBox, "n_points")
        self.form.var_trim = self.widget(QtGui.QCheckBox, "var_trim")
        self.form.pbar = self.widget(QtGui.QProgressBar, "pbar")
        self.form.group_pbar = self.widget(QtGui.QGroupBox, "group_pbar")
        if self.initValues():
            return True

    def getMainWindow(self):
        toplevel = QtGui.QApplication.topLevelWidgets()
        for i in toplevel:
            if i.metaObject().className() == "Gui::MainWindow":
                return i
        raise RuntimeError("No main window found")

    def widget(self, class_id, name):
        """Return the selected widget.

        Keyword arguments:
        class_id -- Class identifier
        name -- Name of the widget
        """
        mw = self.getMainWindow()
        form = mw.findChild(QtGui.QWidget, "GZTaskPanel")
        return form.findChild(class_id, name)

    def initValues(self):
        """ Set initial values for fields """
        # OLD BROKEN METHOD:
        # sel_lcs = Selection.get_lcs()
        # if not sel_lcs:
        #     msg = App.Qt.translate(
        #         "ship_console",
        #         "A load condition instance must be selected before using this tool")
        #     App.Console.PrintError(msg + '\n')
        #     return True
        
        # NEW SIMPLE METHOD: Find ANY spreadsheet called "LoadCondition"
        self.lc = None
        
        # Method 1: Try to find by name
        for obj in App.ActiveDocument.Objects:
            if (hasattr(obj, 'TypeId') and 'Spreadsheet' in obj.TypeId and
                ('LoadCondition' in obj.Name or 'LoadCondition' in obj.Label)):
                self.lc = obj
                break
        
        # Method 2: If not found, take first spreadsheet
        if not self.lc:
            for obj in App.ActiveDocument.Objects:
                if hasattr(obj, 'TypeId') and 'Spreadsheet' in obj.TypeId:
                    self.lc = obj
                    break
        
        if not self.lc:
            msg = App.Qt.translate(
                "ship_console",
                "A load condition spreadsheet must be present in the document")
            App.Console.PrintError(msg + '\n')
            return True
        
        App.Console.PrintMessage("Using LoadCondition: {}\n".format(self.lc.Label))
        
        # Get ship from spreadsheet
        ship_label = None
        try:
            ship_label = self.lc.get('B2')  # Try new format first
        except:
            try:
                ship_label = self.lc.get('B1')  # Fallback to old format
            except:
                pass
        
        if ship_label:
            ships = App.ActiveDocument.getObjectsByLabel(ship_label)
            if len(ships) == 1:
                self.ship = ships[0]
            else:
                # Fallback method
                from ..shipUtils import Selection as ShipSelection
                self.ship = ShipSelection.get_lc_ship(self.lc)
        else:
            from ..shipUtils import Selection as ShipSelection
            self.ship = ShipSelection.get_lc_ship(self.lc)
        
        if not self.ship:
            msg = App.Qt.translate(
                "ship_console",
                "Cannot find associated ship for this LoadCondition")
            App.Console.PrintError(msg + '\n')
            return True
        
        # For compatibility - create empty lists
        self.weights = []
        self.tanks = []
        
        # Set UI defaults
        self.form.angle.setText("90 deg")
        
        # Try to use saved values
        if hasattr(self.ship, 'PropertiesList'):
            props = self.ship.PropertiesList
            try:
                props.index("GZAngle")
                self.form.angle.setText(self.ship.GZAngle.UserString)
            except:
                pass
            try:
                props.index("GZNumPoints")
                self.form.n_points.setValue(self.ship.GZNumPoints)
            except ValueError:
                pass
            try:
                props.index("GZVariableTrim")
                self.form.var_trim.setChecked(self.ship.GZVariableTrim)
            except ValueError:
                pass
        
        self.form.group_pbar.hide()
        return False

    

    def save(self):
        """ Saves the data into ship instance. """
        angle = Units.parseQuantity(self.form.angle.text())
        n_points = self.form.n_points.value()
        var_trim = self.form.var_trim.isChecked()

        props = self.ship.PropertiesList
        try:
            props.index("GZAngle")
        except ValueError:
            try:
                tooltip = App.Qt.translate(
                    "ship_gz",
                    "GZ curve tool angle selected [deg]")
            except:
                tooltip = "GZ curve tool angle selected [deg]"
            self.ship.addProperty("App::PropertyAngle",
                                  "GZAngle",
                                  "Ship",
                                  tooltip)
        self.ship.GZAngle = angle
        try:
            props.index("GZNumPoints")
        except ValueError:
            try:
                tooltip = App.Qt.translate(
                    "ship_gz",
                    "GZ curve tool number of points selected")
            except:
                tooltip = "GZ curve tool number of points selected"
            self.ship.addProperty("App::PropertyInteger",
                                  "GZNumPoints",
                                  "Ship",
                                  tooltip)
        self.ship.GZNumPoints = n_points
        try:
            props.index("GZVariableTrim")
        except ValueError:
            try:
                tooltip = App.Qt.translate(
                    "ship_gz",
                    "GZ curve tool variable trim angle selection")
            except:
                tooltip = "GZ curve tool variable trim angle selection"
            self.ship.addProperty("App::PropertyBool",
                                  "GZVariableTrim",
                                  "Ship",
                                  tooltip)
        self.ship.GZVariableTrim = var_trim


def createTask():
    panel = TaskPanel()
    Gui.Control.showDialog(panel)
    if panel.setupUi():
        Gui.Control.closeDialog()
        return None
    return panel
