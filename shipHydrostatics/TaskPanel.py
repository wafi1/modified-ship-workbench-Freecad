#***************************************************************************
#*                                                                         *
#*   Copyright (c) 2011, 2016 Jose Luis Cercos Pita <jlcercos@gmail.com>   *
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
from FreeCAD import Base, Vector
import Part
from FreeCAD import Units
from PySide import QtGui, QtCore
from . import PlotAux
from . import Tools
from .. import Instance
from ..shipUtils import Locale
from ..shipUtils import Selection

QT_TRANSLATE_NOOP = App.Qt.QT_TRANSLATE_NOOP


class TaskPanel:
    def __init__(self):
        self.name = "ship hydrostatic curves plotter"
        self.ui = os.path.join(os.path.dirname(__file__),
                               "../resources/ui/",
                               "TaskPanel_shipHydrostatics.ui")
        self.form = Gui.PySideUic.loadUi(self.ui)
        self.ship = None
        self.running = False

    def accept(self):
        if not self.ship:
            return False
        if self.running:
            return
        self.form.group_pbar.show()
        self.save()

        trim = Units.parseQuantity(Locale.fromString(self.form.trim.text()))
        min_draft = Units.parseQuantity(Locale.fromString(self.form.min_draft.text()))
        max_draft = Units.parseQuantity(Locale.fromString(self.form.max_draft.text()))
        n_draft = self.form.n_draft.value()
        self.form.pbar.setMinimum(0)
        self.form.pbar.setMaximum(n_draft)
        self.form.pbar.setValue(0)

        draft = min_draft
        drafts = [draft]
        dDraft = (max_draft - min_draft) / (n_draft - 1)
        for i in range(1, n_draft):
            draft = draft + dDraft
            drafts.append(draft)

        # Get external faces
        self.loop = QtCore.QEventLoop()
        self.timer = QtCore.QTimer()
        self.timer.setSingleShot(True)
        QtCore.QObject.connect(self.timer,
                               QtCore.SIGNAL("timeout()"),
                               self.loop,
                               QtCore.SLOT("quit()"))
        self.running = True
        faces = self.externalFaces(self.ship.Shape)
        if not self.running:
            return False
        if len(faces) == 0:
            msg = App.Qt.translate(
                "ship_console",
                "Failure detecting external faces from the ship object")
            App.Console.PrintError(msg + '\n')
            return False
        faces = Part.makeShell(faces)

        # Get the hydrostatics
        msg = App.Qt.translate(
            "ship_console",
            "Computing hydrostatics")
        App.Console.PrintMessage(msg + '...\n')
        points = []
        plt = None
        for i in range(len(drafts)):
            App.Console.PrintMessage("\t{} / {}\n".format(i + 1, len(drafts)))
            self.form.pbar.setValue(i + 1)
            draft = drafts[i]
            point = Tools.Point(self.ship,
                                faces,
                                draft,
                                trim)
            points.append(point)
            if plt is None:
                plt = PlotAux.Plot(self.ship, points)
            else:
                plt.update(self.ship, points)
            self.timer.start(0.0)
            self.loop.exec_()
            if(not self.running):
                break
        return True

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
        self.form.trim = self.widget(QtGui.QLineEdit, "trim")
        self.form.min_draft = self.widget(QtGui.QLineEdit, "min_draft")
        self.form.max_draft = self.widget(QtGui.QLineEdit, "max_draft")
        self.form.n_draft = self.widget(QtGui.QSpinBox, "n_draft")
        self.form.pbar = self.widget(QtGui.QProgressBar, "pbar")
        self.form.group_pbar = self.widget(QtGui.QGroupBox, "group_pbar")
        if self.initValues():
            return True
        QtCore.QObject.connect(self.form.trim,
                               QtCore.SIGNAL("valueChanged(const Base::Quantity&)"),
                               self.onData)
        QtCore.QObject.connect(self.form.min_draft,
                               QtCore.SIGNAL("valueChanged(const Base::Quantity&)"),
                               self.onData)
        QtCore.QObject.connect(self.form.max_draft,
                               QtCore.SIGNAL("valueChanged(const Base::Quantity&)"),
                               self.onData)

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
        form = mw.findChild(QtGui.QWidget, "HydrostaticsTaskPanel")
        return form.findChild(class_id, name)

    def initValues(self):
        """ Set initial values for fields
        """
        sel_ships = Selection.get_ships()
        if not sel_ships:
            msg = App.Qt.translate(
                "ship_console",
                "A ship instance must be selected before using this tool")
            App.Console.PrintError(msg + '\n')
            return True
        self.ship = sel_ships[0]
        if len(sel_ships) > 1:
            msg = App.Qt.translate(
                "ship_console",
                "More than one ship have been selected (just the one labelled"
                " '{}' is considered)".format(self.ship.Label))
            App.Console.PrintWarning(msg + '\n')

        props = self.ship.PropertiesList

        try:
            props.index("HydrostaticsTrim")
            self.form.trim.setText(self.ship.HydrostaticsTrim.UserString)
        except ValueError:
            self.form.trim.setText("0 deg")

        try:
            props.index("HydrostaticsMinDraft")
            self.form.min_draft.setText(
                self.ship.HydrostaticsMinDraft.UserString)
        except ValueError:
            self.form.min_draft.setText(
                (0.9 * self.ship.Draft).UserString)
        try:
            props.index("HydrostaticsMaxDraft")
            self.form.max_draft.setText(
                self.ship.HydrostaticsMaxDraft.UserString)
        except ValueError:
            self.form.max_draft.setText(
                (1.1 * self.ship.Draft).UserString)

        try:
            props.index("HydrostaticsNDraft")
            self.form.n_draft.setValue(self.ship.HydrostaticsNDraft)
        except ValueError:
            pass

        self.form.group_pbar.hide()
        return False

    def clampValue(self, widget, val_min, val_max, val):
        if val_min <= val <= val_max:
            return val
        val = min(val_max, max(val_min, val))
        widget.setText(val.UserString)
        return val

    def onData(self, value):
        """ Method called when input data is changed.
         @param value Changed value.
        """
        min_draft = Units.parseQuantity(Locale.fromString(
            self.form.min_draft.text()))
        max_draft = Units.parseQuantity(Locale.fromString(
            self.form.max_draft.text()))
        trim = Units.parseQuantity(Locale.fromString(self.form.trim.text()))
        if min_draft.Unit != Units.Length or \
            max_draft.Unit != Units.Length or \
            trim.Unit != Units.Angle:
            return

        bbox = self.ship.Shape.BoundBox
        draft_min = Units.Quantity(bbox.ZMin, Units.Length)
        draft_max = Units.Quantity(bbox.ZMax, Units.Length)
        min_draft = self.clampValue(
            self.form.min_draft, draft_min, draft_max, min_draft)
        max_draft = self.clampValue(
            self.form.max_draft, draft_min, draft_max, max_draft)
        min_draft = self.clampValue(self.form.min_draft,
                                    draft_min,
                                    max_draft,
                                    min_draft)
        trim = self.clampValue(self.form.trim,
                               Units.parseQuantity("-90 deg"),
                               Units.parseQuantity("90 deg"),
                               trim)

    def save(self):
        """ Saves data into ship instance.
        """
        trim = Units.Quantity(self.form.trim.text())
        min_draft = Units.Quantity(self.form.min_draft.text())
        max_draft = Units.Quantity(self.form.max_draft.text())
        n_draft = self.form.n_draft.value()

        props = self.ship.PropertiesList
        try:
            props.index("HydrostaticsTrim")
        except ValueError:
            tooltip = QT_TRANSLATE_NOOP(
                "App::Property",
                "Hydrostatics tool selected trim angle")
            self.ship.addProperty("App::PropertyAngle",
                                  "HydrostaticsTrim",
                                  "Ship",
                                  tooltip)
        self.ship.HydrostaticsTrim = trim

        try:
            props.index("HydrostaticsMinDraft")
        except ValueError:
            tooltip = QT_TRANSLATE_NOOP(
                "App::Property",
                "Hydrostatics tool selected minimum draft")
            self.ship.addProperty("App::PropertyLength",
                                  "HydrostaticsMinDraft",
                                  "Ship",
                                  tooltip)
        self.ship.HydrostaticsMinDraft = min_draft

        try:
            props.index("HydrostaticsMaxDraft")
        except ValueError:
            tooltip = QT_TRANSLATE_NOOP(
                "App::Property",
                "Hydrostatics tool selected maximum draft")
            self.ship.addProperty("App::PropertyLength",
                                  "HydrostaticsMaxDraft",
                                  "Ship",
                                  tooltip)
        self.ship.HydrostaticsMaxDraft = max_draft

        try:
            props.index("HydrostaticsNDraft")
        except ValueError:
            tooltip = QT_TRANSLATE_NOOP(
                "App::Property",
                "Hydrostatics tool number of points selected")
            self.ship.addProperty("App::PropertyInteger",
                                  "HydrostaticsNDraft",
                                  "Ship",
                                  tooltip)
        self.ship.HydrostaticsNDraft = self.form.n_draft.value()

    def lineFaceSection(self, line, surface):
        """ Returns the point of section of a line with a face
        @param line Line object, that can be a curve.
        @param surface Surface object (must be a Part::Shape)
        @return Section points array, [] if line don't cut surface
        """
        section = line.cut(surface)
        return section.Vertexes

    @staticmethod
    def _ray_param(p0, p1, pt):
        """Robustly compute the parameter t of 'pt' along the ray p0 → p1.

        Uses the axis with the largest extent to avoid division-by-near-zero
        errors that occurred in the original code when the ray direction was
        mostly in Y or Z but the code only checked the X component.

        Returns a float in [0, 1] if pt lies between p0 and p1.
        """
        dx = p1.x - p0.x
        dy = p1.y - p0.y
        dz = p1.z - p0.z
        # Pick the numerically largest component
        adx, ady, adz = abs(dx), abs(dy), abs(dz)
        if adx >= ady and adx >= adz:
            return (pt.X - p0.x) / dx if adx > 1e-9 else 0.5
        elif ady >= adx and ady >= adz:
            return (pt.Y - p0.y) / dy if ady > 1e-9 else 0.5
        else:
            return (pt.Z - p0.z) / dz if adz > 1e-9 else 0.5

    def externalFaces(self, shape):
        """Returns external faces using FreeCAD's native isInside() check.

        Strategy
        --------
        For every face we move a tiny probe point along the outward normal
        and ask every solid of the shape whether that point is inside it.
        If *no* solid contains the probe point the face is external.

        This replaces the previous manual ray-casting loop which had two
        known bugs:
          1. The parameter calculation only used the X component of the ray
             direction, giving wrong results for faces whose normal points
             mainly in Y or Z.
          2. The face sampling (n_faces // sample_size) was inconsistent and
             could miss intersections entirely for small meshes.

        isInside() is a native C++ call and is therefore much faster than
        iterating over faces in Python.
        """
        import time
        start_time = time.time()

        faces = shape.Faces
        solids = shape.Solids
        n_faces = len(faces)

        if n_faces == 0:
            return []

        msg = App.Qt.translate(
            "ship_console",
            "Computing external faces")
        App.Console.PrintMessage(msg + '...\n')
        App.Console.PrintMessage("\tTotal faces: {}\n".format(n_faces))

        # Probe distance: 0.1 % of the bounding-box diagonal is enough to
        # clear floating-point noise on the surface itself.
        bbox = shape.BoundBox
        diag = math.sqrt((bbox.XMax - bbox.XMin) ** 2 +
                         (bbox.YMax - bbox.YMin) ** 2 +
                         (bbox.ZMax - bbox.ZMin) ** 2)
        probe_dist = diag * 0.001

        result = []
        for idx, face in enumerate(faces):
            if not self.running:
                break

            # Yield to the Qt event loop periodically so the UI stays responsive
            if idx % 50 == 0:
                App.Console.PrintMessage(
                    "\t\t{:.1f}%\n".format(100.0 * idx / n_faces))
                self.timer.start(0.0)
                self.loop.exec_()

            try:
                cog = face.CenterOfMass
                u, v = face.Surface.parameter(cog)
                normal = face.normalAt(u, v).normalize()
            except Exception:
                # Degenerate face – skip it
                continue

            # Probe point just outside the surface in the normal direction
            probe = Vector(cog.x + normal.x * probe_dist,
                           cog.y + normal.y * probe_dist,
                           cog.z + normal.z * probe_dist)

            # A face is external when its outward probe point is not enclosed
            # by any solid of the shape.
            is_external = not any(
                solid.isInside(probe, probe_dist * 0.1, False)
                for solid in solids
            )
            if is_external:
                result.append(face)

        elapsed = time.time() - start_time
        App.Console.PrintMessage(
            "\tFound {} external faces in {:.1f}s\n".format(
                len(result), elapsed))

        # Safety fallback: if suspiciously few faces were found, return all
        if len(result) < n_faces * 0.05:
            App.Console.PrintWarning(
                "Warning: Very few external faces detected – "
                "falling back to all faces\n")
            return faces

        return result


def createTask():
    panel = TaskPanel()
    Gui.Control.showDialog(panel)
    if panel.setupUi():
        Gui.Control.closeDialog()
        return None
    return panel
