#***************************************************************************
#*   Copyright (c) 2011, 2016 Jose Luis Cercos Pita <jlcercos@gmail.com>   *
#*   Modified to support new LoadCondition format                          *
#*   FIXED: lc_info now reads GM, KM, VCG directly from spreadsheet       *
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
        self.ship = None
        self.lc = None
        self.running = False

    # ------------------------------------------------------------------ #
    # accept                                                               #
    # ------------------------------------------------------------------ #
    def accept(self):
        if self.lc is None:
            return False
        self.form.group_pbar.show()
        self.save()

        roll_max  = Units.parseQuantity(self.form.angle.text())
        n_points  = self.form.n_points.value()
        var_trim  = self.form.var_trim.isChecked()
        self.form.pbar.setMinimum(0)
        self.form.pbar.setMaximum(n_points)
        self.form.pbar.setValue(0)

        # ---------------------------------------------------------------- #
        # Read LoadCondition data                                           #
        # ---------------------------------------------------------------- #
        use_new_format = False
        W = None
        COG = None
        total_mass_kg = cog_x = cog_y = cog_z = 0.0

        # --- Spreadsheet values read once here, passed to lc_info --------
        gm_from_sheet  = None   # G4  (KM - KG, free-surface corrected)
        km_from_sheet  = None   # F4  (metacentric height above keel)
        vcg_from_sheet = None   # G5  (VCG = KG)

        try:
            # New-format: plain numbers in fixed cells
            total_mass_kg = float(self.lc.get('D4'))
            W = Units.parseQuantity("{} kg".format(total_mass_kg)) * Tools.G

            COG = Tools._parse_cog_from_sheet(self.lc)

            # Keep raw metre values for the SOLAS report
            cog_x = COG.x / 1000.0   # mm → m
            cog_y = COG.y / 1000.0
            cog_z = COG.z / 1000.0

            # --- Read stability values directly from spreadsheet ----------
            # G4 = GM (corrected), F4 = KM, G5 = VCG (= KG)
            try:
                gm_from_sheet = float(self.lc.get('G4'))
                App.Console.PrintMessage(
                    "GM read from spreadsheet G4: {:.3f} m\n".format(gm_from_sheet))
            except Exception as e:
                App.Console.PrintWarning(
                    "Could not read GM from G4: {} – will use curve fit fallback\n".format(e))

            try:
                km_from_sheet = float(self.lc.get('F4'))
            except Exception:
                km_from_sheet = None

            try:
                vcg_from_sheet = float(self.lc.get('G5'))
            except Exception:
                vcg_from_sheet = cog_z   # fallback: use COG z

            App.Console.PrintMessage(
                "LoadCondition (new format):\n"
                "  Mass: {:.1f} kg  COG: ({:.3f}, {:.3f}, {:.3f}) m\n"
                "  KM: {}  GM: {}  VCG/KG: {}\n".format(
                    total_mass_kg, cog_x, cog_y, cog_z,
                    "{:.3f} m".format(km_from_sheet) if km_from_sheet is not None else "n/a",
                    "{:.3f} m".format(gm_from_sheet) if gm_from_sheet is not None else "n/a",
                    "{:.3f} m".format(vcg_from_sheet) if vcg_from_sheet is not None else "n/a",
                ))
            use_new_format = True

        except Exception as e:
            App.Console.PrintWarning(
                "New format not readable, trying legacy format: {}\n".format(e))
            try:
                COG, W = Tools.weights_cog(self.weights)
                TW = Units.parseQuantity("0 kg")
                VOLS = []
                for t in self.tanks:
                    vol = t[0].Proxy.getVolume(t[0], t[2])
                    VOLS.append(vol)
                    TW += vol * t[1]
                TW = TW * Tools.G
            except Exception as e2:
                App.Console.PrintError(
                    "Error reading LoadCondition: {}\n".format(e2))
                return False

        # ---------------------------------------------------------------- #
        # Compute all points first (no plot updates during loop)           #
        # ---------------------------------------------------------------- #
        self.running = True

        rolls  = []
        gzs    = []
        drafts = []
        trims  = []
        displacements = []

        for i in range(n_points):
            App.Console.PrintMessage("{0} / {1}\n".format(i + 1, n_points))
            self.form.pbar.setValue(i + 1)
            roll_val = roll_max * i / float(max(n_points - 1, 1))
            rolls.append(roll_val)

            if use_new_format:
                point = Tools.solve_point_direct(
                    W, COG, self.ship, roll_val, var_trim)

                if point is None:
                    gzs.append(Units.Quantity(0.0, Units.Length))
                    drafts.append(Units.Quantity(0.0, Units.Length))
                    trims.append(Units.parseQuantity("0 deg"))
                    displacements.append(0.0)
                else:
                    gzs.append(point[0])
                    drafts.append(point[1])
                    trims.append(point[2])
                    displacements.append(point[3] if len(point) >= 4 else 0.0)
            else:
                point = Tools.solve_point(
                    W, COG, TW, VOLS,
                    self.ship, self.tanks, roll_val, var_trim)

                if point is None:
                    gzs.append(Units.Quantity(0.0, Units.Length))
                    drafts.append(Units.Quantity(0.0, Units.Length))
                    trims.append(Units.parseQuantity("0 deg"))
                    displacements.append(0.0)
                else:
                    gzs.append(point[0])
                    drafts.append(point[1])
                    trims.append(point[2])
                    displacements.append(0.0)

            QtCore.QCoreApplication.processEvents()

        # ---------------------------------------------------------------- #
        # All data computed – create plot and spreadsheet once             #
        # ---------------------------------------------------------------- #
        App.Console.PrintMessage(
            "\n--- All data computed, creating plot and spreadsheet ---\n")

        lc_info = {
            # identification
            'name':           self.lc.Label,
            'vessel':         self.ship.Label if self.ship else 'Unknown',
            'load_case':      self.lc.Label,
            # weight / geometry
            'displacement':   round(total_mass_kg / 1000.0, 2),   # tonnes
            'vcg':            round(vcg_from_sheet, 3) if vcg_from_sheet is not None else '-',
            'kg':             round(vcg_from_sheet, 3) if vcg_from_sheet is not None else '-',
            'km':             round(km_from_sheet, 3)  if km_from_sheet  is not None else '-',
            # THE KEY VALUE: GM read directly from spreadsheet cell G4
            'gm':             gm_from_sheet,
            # raw data (for internal use)
            'mass':           total_mass_kg,
            'cog':            [cog_x, cog_y, cog_z],
            'ship_label':     self.ship.Label if self.ship else 'Unknown',
            'use_new_format': use_new_format,
        }

        plt = PlotAux.Plot(rolls, gzs, drafts, trims, lc_info)

        if use_new_format and displacements and any(d > 0 for d in displacements):
            plt.set_displacement(displacements)

        # ---------------------------------------------------------------- #
        # SOLAS post-processing                                            #
        # ---------------------------------------------------------------- #
        if use_new_format and gzs:
            try:
                points_with_disp = list(zip(gzs, drafts, trims, displacements))

                # Pass gm_from_sheet so Tools does not recompute via curve fit
                solas_data = Tools.analyze_solas_stability(
                    points_with_disp, rolls, self.ship, COG,
                    gm_from_sheet=gm_from_sheet)

                solas_data.update({
                    'lc_label':      self.lc.Label,
                    'ship_label':    self.ship.Label,
                    'total_mass_kg': total_mass_kg,
                    'cog_x':         COG.x,
                    'cog_y':         COG.y,
                    'cog_z':         COG.z,
                })

                Tools.print_solas_report(solas_data)

                if hasattr(plt, 'sheet') and plt.sheet:
                    self._export_solas_to_spreadsheet(plt.sheet, solas_data)

            except Exception as e:
                App.Console.PrintWarning(
                    "SOLAS analysis failed: {}\n".format(e))
                import traceback
                traceback.print_exc()

        self.form.group_pbar.hide()
        return True

    # ------------------------------------------------------------------ #
    # _export_solas_to_spreadsheet                                        #
    # ------------------------------------------------------------------ #
    def _export_solas_to_spreadsheet(self, sheet, solas_data):
        """Write SOLAS results to column H of the results spreadsheet."""
        try:
            sheet.set("H1",  "SOLAS/IMO STABILITY ANALYSIS")
            sheet.set("H3",  "Ship: {}".format(solas_data.get('ship_label', 'N/A')))
            sheet.set("H4",  "Load Condition: {}".format(solas_data.get('lc_label', 'N/A')))
            sheet.set("H5",  "Total Mass: {:.1f} kg".format(
                solas_data.get('total_mass_kg', 0)))

            sheet.set("H7",  "STABILITY PARAMETERS:")
            sheet.set("H8",  "Max GZ: {:.3f} m".format(solas_data.get('max_gz', 0)))
            sheet.set("H9",  "Angle of Max GZ: {:.1f} deg".format(
                solas_data.get('max_gz_angle', 0)))
            sheet.set("H10", "Vanishing Angle: {:.1f} deg".format(
                solas_data.get('vanishing_angle', 0)))
            sheet.set("H11", "GZ at 30 deg: {:.3f} m".format(
                solas_data.get('gz_at_30', 0)))
            sheet.set("H12", "Initial GM: {:.3f} m  [{}]".format(
                solas_data.get('GM0', 0),
                solas_data.get('gm_source', 'curve fit')))

            sheet.set("H14", "AREA UNDER GZ CURVE:")
            sheet.set("H15", "0-30 deg:  {:.4f} m*rad".format(
                solas_data.get('area_0_30', 0)))
            sheet.set("H16", "0-40 deg:  {:.4f} m*rad".format(
                solas_data.get('area_0_40', 0)))
            sheet.set("H17", "30-40 deg: {:.4f} m*rad".format(
                solas_data.get('area_30_40', 0)))

            sheet.set("H19", "SOLAS/IMO CRITERIA:")
            label_map = {
                'area_0_30':    'Area  0-30 deg',
                'area_0_40':    'Area  0-40 deg',
                'area_30_40':   'Area 30-40 deg',
                'gz_at_30':     'GZ at 30 deg  ',
                'max_gz_angle': 'Angle max GZ  ',
                'GM0':          'Initial GM    ',
            }
            row = 20
            for name, crit in solas_data.get('solas_criteria', {}).items():
                status  = "PASS" if crit.get('passed') else "FAIL"
                display = label_map.get(name, name.replace('_', ' ').title())
                sheet.set("H{}".format(row),
                          "{}: {:.4f} / {:.3f} ({})".format(
                              display,
                              crit.get('value', 0),
                              crit.get('required', 0),
                              status))
                row += 1

            passed    = solas_data.get('passed_count', 0)
            total     = solas_data.get('total_criteria', 0)
            compliant = solas_data.get('compliant', False)
            sheet.set("H{}".format(row + 1),
                      "Summary: {}/{} criteria passed".format(passed, total))
            sheet.set("H{}".format(row + 2),
                      "COMPLIANT" if compliant else "NON-COMPLIANT")

            if hasattr(sheet, 'Document') and sheet.Document:
                sheet.Document.recompute()

            App.Console.PrintMessage(
                "SOLAS results written to spreadsheet column H\n")

        except Exception as e:
            App.Console.PrintWarning(
                "Could not export SOLAS results to spreadsheet: {}\n".format(e))
            import traceback
            traceback.print_exc()

    # ------------------------------------------------------------------ #
    # Standard TaskPanel interface                                        #
    # ------------------------------------------------------------------ #
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
        self.form.angle    = self.widget(QtGui.QLineEdit,    "angle")
        self.form.n_points = self.widget(QtGui.QSpinBox,     "n_points")
        self.form.var_trim = self.widget(QtGui.QCheckBox,    "var_trim")
        self.form.pbar     = self.widget(QtGui.QProgressBar, "pbar")
        self.form.group_pbar = self.widget(QtGui.QGroupBox,  "group_pbar")
        if self.initValues():
            return True

    def getMainWindow(self):
        toplevel = QtGui.QApplication.topLevelWidgets()
        for i in toplevel:
            if i.metaObject().className() == "Gui::MainWindow":
                return i
        raise RuntimeError("No main window found")

    def widget(self, class_id, name):
        mw   = self.getMainWindow()
        form = mw.findChild(QtGui.QWidget, "GZTaskPanel")
        return form.findChild(class_id, name)

    def initValues(self):
        """Locate ship and LoadCondition spreadsheet; populate UI defaults."""
        self.lc = None

        for obj in App.ActiveDocument.Objects:
            if (hasattr(obj, 'TypeId') and
                    'Spreadsheet' in obj.TypeId and
                    ('LoadCondition' in obj.Name or
                     'LoadCondition' in obj.Label)):
                self.lc = obj
                break

        if not self.lc:
            for obj in App.ActiveDocument.Objects:
                if hasattr(obj, 'TypeId') and 'Spreadsheet' in obj.TypeId:
                    self.lc = obj
                    break

        if not self.lc:
            msg = App.Qt.translate(
                "ship_console",
                "A LoadCondition spreadsheet must be present in the document")
            App.Console.PrintError(msg + '\n')
            return True

        App.Console.PrintMessage(
            "Using LoadCondition: {}\n".format(self.lc.Label))

        ship_label = None
        for cell in ('B2', 'B1'):
            try:
                ship_label = self.lc.get(cell)
                break
            except Exception:
                continue

        if ship_label:
            ships = App.ActiveDocument.getObjectsByLabel(ship_label)
            self.ship = ships[0] if len(ships) == 1 else None

        if not self.ship:
            try:
                from ..shipUtils import Selection as ShipSelection
                self.ship = ShipSelection.get_lc_ship(self.lc)
            except Exception:
                pass

        if not self.ship:
            msg = App.Qt.translate(
                "ship_console",
                "Cannot find the ship associated with this LoadCondition")
            App.Console.PrintError(msg + '\n')
            return True

        self.weights = []
        self.tanks   = []

        self.form.angle.setText("90 deg")
        # Variable trim defaults to OFF.
        # The iterative trim solver tends to diverge at large heel angles
        # where trim is physically irrelevant. The user can still enable it
        # via the checkbox for upright / small-angle calculations.
        self.form.var_trim.setChecked(False)
        if hasattr(self.ship, 'PropertiesList'):
            props = self.ship.PropertiesList
            for prop, setter in (
                    ("GZAngle",     lambda: self.form.angle.setText(
                                        self.ship.GZAngle.UserString)),
                    ("GZNumPoints", lambda: self.form.n_points.setValue(
                                        self.ship.GZNumPoints)),
                    # GZVariableTrim deliberately excluded – var_trim is
                    # always OFF by default (set above). The saved True value
                    # must not override the safe default.
            ):
                if prop in props:
                    try:
                        setter()
                    except Exception:
                        pass

        self.form.group_pbar.hide()
        return False

    def save(self):
        """Persist UI state into ship properties."""
        angle    = Units.parseQuantity(self.form.angle.text())
        n_points = self.form.n_points.value()
        var_trim = self.form.var_trim.isChecked()

        props    = self.ship.PropertiesList
        prop_defs = [
            ("GZAngle",        "App::PropertyAngle",   "GZ curve angle [deg]",        angle),
            ("GZNumPoints",    "App::PropertyInteger",  "GZ curve number of points",   n_points),
            ("GZVariableTrim", "App::PropertyBool",     "GZ curve variable trim flag", var_trim),
        ]
        for name, type_, tooltip, value in prop_defs:
            if name not in props:
                self.ship.addProperty(type_, name, "Ship", tooltip)
            setattr(self.ship, name, value)


def createTask():
    panel = TaskPanel()
    Gui.Control.showDialog(panel)
    if panel.setupUi():
        Gui.Control.closeDialog()
        return None
    return panel
