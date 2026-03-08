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

import FreeCAD
import FreeCADGui
import os


from .shipUtils import Selection


FreeCADGui.addLanguagePath(os.path.join(os.path.dirname(__file__),
                                        "resources/translations"))
FreeCADGui.addIconPath(os.path.join(os.path.dirname(__file__),
                                        "resources/icons"))


QT_TRANSLATE_NOOP = FreeCAD.Qt.QT_TRANSLATE_NOOP


class LoadExample:
    def Activated(self):
        from . import shipLoadExample
        shipLoadExample.load()

    def GetResources(self):
        MenuText = QT_TRANSLATE_NOOP(
            'Ship_LoadExample',
            'Load an example ship geometry')
        ToolTip = QT_TRANSLATE_NOOP(
            'Ship_LoadExample',
            'Load an example ship hull geometry.')
        return {'Pixmap': 'Ship_Load',
                'MenuText': MenuText,
                'ToolTip': ToolTip}


class CreateShip:
    def IsActive(self):
        return True

    def Activated(self):
        from . import shipCreateShip
        shipCreateShip.load()

    def GetResources(self):
        MenuText = QT_TRANSLATE_NOOP(
            'Ship_CreateShip',
            'Create a new ship')
        ToolTip = QT_TRANSLATE_NOOP(
            'Ship_CreateShip',
            'Create a new ship instance on top of the hull geometry')
        return {'Pixmap': 'Ship_Module',
                'MenuText': MenuText,
                'ToolTip': ToolTip}


class AreasCurve:
    def IsActive(self):
        return bool(Selection.get_ships())

    def Activated(self):
        from . import shipAreasCurve
        shipAreasCurve.load()

    def GetResources(self):
        MenuText = QT_TRANSLATE_NOOP(
            'Ship_AreasCurve',
            'Areas curve')
        ToolTip = QT_TRANSLATE_NOOP(
            'Ship_AreasCurve',
            'Plot the transversal areas curve')
        return {'Pixmap': 'Ship_AreaCurve',
                'MenuText': MenuText,
                'ToolTip': ToolTip}


class Hydrostatics:
    def IsActive(self):
        return bool(Selection.get_ships())

    def Activated(self):
        from . import shipHydrostatics
        shipHydrostatics.load()

    def GetResources(self):
        MenuText = QT_TRANSLATE_NOOP(
            'Ship_Hydrostatics',
            'Hydrostatics')
        ToolTip = QT_TRANSLATE_NOOP(
            'Ship_Hydrostatics',
            'Plot the ship hydrostatics')
        return {'Pixmap': 'Ship_Hydrostatics',
                'MenuText': MenuText,
                'ToolTip': ToolTip}


class CreateWeight:
    def IsActive(self):
        return bool(Selection.get_sfrom setuptools import setup
import os
from freecad.ship.compile_resources import compile_resources

version_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 
                            "freecad", "ship", "version.py")
with open(version_path) as fp:
    exec(fp.read())
    
compile_resources()

setup(name='freecad.ship',
      version=str(__version__),
      packages=['freecad',
                'freecad.ship',
                'freecad.ship.shipAreasCurve',
                'freecad.ship.shipCapacityCurve',
                'freecad.ship.shipCreateLoadCondition',
                'freecad.ship.shipCreateShip',
                'freecad.ship.shipCreateTank',
                'freecad.ship.shipCreateWeight',
                'freecad.ship.shipGZ',
                'freecad.ship.shipHydrostatics',
                'freecad.ship.shipLoadExample',
                'freecad.ship.shipSinkAndTrim',
                'freecad.ship.seakeepingSetMesh',
                'freecad.ship.seakeepingRAOs',
                'freecad.ship.shipUtils',
                ],
      maintainer="sanguinariojoe",
      maintainer_email="jlcercos@gmail.com",
      url="https://github.com/FreeCAD/ship",
      description="externalized ship workbench. Created by Jose Luis Cercos Pita",
      install_requires=['numpy', 'scipy', 'capytaine', ],
      include_package_data=True)
hapes()) and bool(Selection.get_doc_ships())

    def Activated(self):
        from . import shipCreateWeight
        shipCreateWeight.load()

    def GetResources(self):
        MenuText = QT_TRANSLATE_NOOP(
            'Ship_Weight',
            'Create a new ship weight')
        ToolTip = QT_TRANSLATE_NOOP(
            'Ship_Weight',
            'Create a new ship weight')
        return {'Pixmap': 'Ship_Weight',
                'MenuText': MenuText,
                'ToolTip': ToolTip}


class CreateTank:
    def IsActive(self):
        return bool(Selection.get_solids()) and bool(Selection.get_doc_ships())

    def Activated(self):
        from . import shipCreateTank
        shipCreateTank.load()

    def GetResources(self):
        MenuText = QT_TRANSLATE_NOOP(
            'Ship_Tank',
            'Create a new tank')
        ToolTip = QT_TRANSLATE_NOOP(
            'Ship_Tank',
            'Create a new tank')
        return {'Pixmap': 'Ship_Tank',
                'MenuText': MenuText,
                'ToolTip': ToolTip}


class TankCapacity:
    def IsActive(self):
        return bool(Selection.get_tanks())

    def Activated(self):
        from . import shipCapacityCurve
        shipCapacityCurve.load()

    def GetResources(self):
        MenuText = QT_TRANSLATE_NOOP(
            'Ship_Capacity',
            'Tank capacity curve')
        ToolTip = QT_TRANSLATE_NOOP(
            'Ship_Capacity',
            'Plot the tank capacity curve (level-volume curve)')
        return {'Pixmap': 'Ship_CapacityCurve',
                'MenuText': MenuText,
                'ToolTip': ToolTip}


class LoadCondition:
    def IsActive(self):
        return bool(Selection.get_ships())

    def Activated(self):
        from . import shipCreateLoadCondition
        shipCreateLoadCondition.load()

    def GetResources(self):
        MenuText = QT_TRANSLATE_NOOP(
            'Ship_LoadCondition',
            'Create a new loading condition')
        ToolTip = QT_TRANSLATE_NOOP(
            'Ship_LoadCondition',
            'Create a new load condition spreadsheet')
        return {'Pixmap': 'Ship_LoadCondition',
                'MenuText': MenuText,
                'ToolTip': ToolTip}


class CalculateLoadCondition:
    def IsActive(self):
        return FreeCAD.ActiveDocument is not None

    def Activated(self):
        from .shipCreateLoadCondition.CalculateLoadCondition import \
            CalculateLoadCondition as CalcCmd
        cmd = CalcCmd()
        cmd.recalculate_current()

    def GetResources(self):
        MenuText = QT_TRANSLATE_NOOP(
            'Ship_CalculateLoadCondition',
            'Calculate Load Case')
        ToolTip = QT_TRANSLATE_NOOP(
            'Ship_CalculateLoadCondition',
            'Recalculate tank conditions for current load case')
        return {'Pixmap': 'ship_calc',
                'MenuText': MenuText,
                'ToolTip': ToolTip}


class CargoStowagePlan:
    def IsActive(self):
        return FreeCAD.ActiveDocument is not None

    def Activated(self):
        try:
            from .shipCreateLoadCondition.CargoStowagePlanGUI import \
                CargoImportDialog
            dialog = CargoImportDialog()
            dialog.exec_()
        except Exception as e:
            FreeCAD.Console.PrintWarning(
                f"CargoStowagePlanGUI failed ({e}), trying fallback...\n")
            try:
                from .shipCreateLoadCondition.CargoStowagePlan import \
                    CargoImportCommand
                CargoImportCommand().Activated()
            except Exception as e2:
                FreeCAD.Console.PrintError(
                    f"CargoStowagePlan failed to load: {e2}\n")

    def GetResources(self):
        MenuText = QT_TRANSLATE_NOOP(
            'Ship_Read_Packinglist',
            'Read Packing List')
        ToolTip = QT_TRANSLATE_NOOP(
            'Ship_Read_Packinglist',
            'Import cargo from Excel spreadsheet')
        return {'Pixmap': 'ship_cargo',
                'MenuText': MenuText,
                'ToolTip': ToolTip}


class SinkAndTrim:
    def IsActive(self):
        return FreeCAD.ActiveDocument is not None

    def Activated(self):
        try:
            from .shipSinkAndTrim.TaskPanel import createTask
            panel = createTask()
            if panel:
                FreeCADGui.Control.showDialog(panel)
        except Exception as e:
            FreeCAD.Console.PrintError(f"SinkAndTrim error: {e}\n")
            import traceback
            traceback.print_exc()

    def GetResources(self):
        return {
            'Pixmap':   'Ship_SinkAndTrim',
            'MenuText': 'Sink and Trim',
            'ToolTip':  'Calculate ship equilibrium',
        }


class GZ:
    def IsActive(self):
        return FreeCAD.ActiveDocument is not None

    def Activated(self):
        from . import shipGZ
        shipGZ.load()

    def GetResources(self):
        MenuText = QT_TRANSLATE_NOOP(
            'Ship_GZ',
            'GZ curve computation')
        ToolTip = QT_TRANSLATE_NOOP(
            'Ship_GZ',
            'Plot the GZ curve')
        return {'Pixmap': 'Ship_GZ',
                'MenuText': MenuText,
                'ToolTip': ToolTip}


class Amadeo:
    def IsActive(self):
        return True

    def Activated(self):
        from . import resistanceAmadeo
        resistanceAmadeo.load()

    def GetResources(self):
        MenuText = QT_TRANSLATE_NOOP(
            'Ship_ResistanceAmadeo',
            'Resistance Amadeo prediction')
        ToolTip = QT_TRANSLATE_NOOP(
            'Ship_ResistanceAmadeo',
            'Compute the resistance by Amadeo method')
        return {'Pixmap': 'Resistance_Amadeo',
                'MenuText': MenuText,
                'ToolTip': ToolTip}


class BlountFox:
    def IsActive(self):
        return True

    def Activated(self):
        from . import resistanceBlountFox
        resistanceBlountFox.load()

    def GetResources(self):
        MenuText = QT_TRANSLATE_NOOP(
            'Ship_ResistanceBlountFox',
            'Resistance Blount and Fox prediction')
        ToolTip = QT_TRANSLATE_NOOP(
            'Ship_ResistanceBlountFox',
            'Compute the resistance by Blount and Fox method')
        return {'Pixmap': 'Resistance_BlountFox',
                'MenuText': MenuText,
                'ToolTip': ToolTip}


class Holtrop:
    def IsActive(self):
        return True

    def Activated(self):
        from . import resistanceHoltrop
        resistanceHoltrop.load()

    def GetResources(self):
        MenuText = QT_TRANSLATE_NOOP(
            'Ship_ResistanceHoltrop',
            'Resistance Holtrop prediction')
        ToolTip = QT_TRANSLATE_NOOP(
            'Ship_ResistanceHoltrop',
            'Compute the resistance by Holtrop method')
        return {'Pixmap': 'Resistance_Holtrop',
                'MenuText': MenuText,
                'ToolTip': ToolTip}


class Savitsky:
    def IsActive(self):
        return True

    def Activated(self):
        from . import resistanceSavitsky
        resistanceSavitsky.load()

    def GetResources(self):
        MenuText = QT_TRANSLATE_NOOP(
            'Ship_ResistanceSavitsky',
            'Resistance Savitsky prediction')
        ToolTip = QT_TRANSLATE_NOOP(
            'Ship_ResistanceSavitsky',
            'Compute the resistance by Savitsky method')
        return {'Pixmap': 'Resistance_Savitsky',
                'MenuText': MenuText,
                'ToolTip': ToolTip}


class SetMesh:
    def IsActive(self):
        return FreeCAD.ActiveDocument is not None

    def Activated(self):
        from . import seakeepingSetMesh
        seakeepingSetMesh.load()

    def GetResources(self):
        MenuText = QT_TRANSLATE_NOOP(
            'Ship_SeakeepingSetMesh',
            'Set ship surface mesh')
        ToolTip = QT_TRANSLATE_NOOP(
            'Ship_SeakeepingSetMesh',
            'Associate the surface mesh to the ship')
        return {'Pixmap': 'Seakeeping_SetMesh',
                'MenuText': MenuText,
                'ToolTip': ToolTip}


class RAOs:
    def IsActive(self):
        return FreeCAD.ActiveDocument is not None

    def Activated(self):
        try:
            from . import seakeepingRAOs
            panel = seakeepingRAOs.load()
            if panel:
                FreeCADGui.Control.showDialog(panel)
            else:
                FreeCAD.Console.PrintError("seakeepingRAOs.load() returned None\n")
        except Exception as e:
            FreeCAD.Console.PrintError(f"RAOs error: {e}\n")
            import traceback
            traceback.print_exc()

    def GetResources(self):
        MenuText = QT_TRANSLATE_NOOP(
            'Ship_SeakeepingRAOs',
            'Plot RAOs')
        ToolTip = QT_TRANSLATE_NOOP(
            'Ship_SeakeepingRAOs',
            'Compute and plot the RAOs')
        return {'Pixmap': 'Seakeeping_RAOs',
                'MenuText': MenuText,
                'ToolTip': ToolTip}


class CreateCapytaineMesh:
    """Erstellt ein BEM-Oberflächenmesh für Capytaine Seakeeping-Analyse."""

    def IsActive(self):
        if FreeCAD.ActiveDocument is None:
            return False
        for obj in FreeCAD.ActiveDocument.Objects:
            if hasattr(obj, 'Shape') and not obj.Shape.isNull():
                return True
        return False

    def Activated(self):
        try:
            from .seakeepingRAOs.TaskPanel_CreateCapytaineMesh import createTask
            createTask()
        except Exception as e:
            FreeCAD.Console.PrintError(
                f"CreateCapytaineMesh error: {e}\n")
            import traceback
            traceback.print_exc()

    def GetResources(self):
        MenuText = QT_TRANSLATE_NOOP(
            'Ship_CreateCapytaineMesh',
            'Create Capytaine Mesh')
        ToolTip = QT_TRANSLATE_NOOP(
            'Ship_CreateCapytaineMesh',
            'Create a hull surface mesh for Capytaine BEM seakeeping analysis')
        return {
            'Pixmap':   'ship_mesh',
            'MenuText': MenuText,
            'ToolTip':  ToolTip,
        }


# ===========================================================================
# NEU: Kran-Commands
# ===========================================================================

class CreateCrane:
    def IsActive(self):
        return FreeCAD.ActiveDocument is not None

    def Activated(self):
        try:
            from .shipCraneLoadout.TaskCreateCrane import ShipCraneDialog
            dlg = ShipCraneDialog(FreeCADGui.getMainWindow())
            dlg.exec_()
        except Exception as e:
            FreeCAD.Console.PrintError(f"CreateCrane error: {e}\n")
            import traceback
            traceback.print_exc()

    def GetResources(self):
        MenuText = QT_TRANSLATE_NOOP('Ship_CreateCrane', 'Create Crane')
        ToolTip  = QT_TRANSLATE_NOOP('Ship_CreateCrane', 'Create a new ship crane')
        return {'Pixmap': 'Ship_CreateCrane', 'MenuText': MenuText, 'ToolTip': ToolTip}


class CoupleCrane:
    def IsActive(self):
        return FreeCAD.ActiveDocument is not None

    def Activated(self):
        try:
            from .shipCraneLoadout.TaskCreateCrane import couple_crane_to_ship
            sel    = FreeCADGui.Selection.getSelection()
            cranes = [o for o in sel
                      if getattr(getattr(o, 'Proxy', None), 'Type', '') == 'ShipCrane']
            ships  = [o for o in sel if o not in cranes]
            if cranes and ships:
                couple_crane_to_ship(cranes[0], ships[0])
            else:
                FreeCAD.Console.PrintWarning("Bitte Kran und Schiff auswählen.\n")
        except Exception as e:
            FreeCAD.Console.PrintError(f"CoupleCrane error: {e}\n")

    def GetResources(self):
        MenuText = QT_TRANSLATE_NOOP('Ship_CoupleCrane', 'Couple Crane')
        ToolTip  = QT_TRANSLATE_NOOP('Ship_CoupleCrane', 'Couple selected crane to ship')
        return {'Pixmap': 'Ship_CoupleCrane', 'MenuText': MenuText, 'ToolTip': ToolTip}


class DecoupleCrane:
    def IsActive(self):
        return FreeCAD.ActiveDocument is not None

    def Activated(self):
        try:
            from .shipCraneLoadout.TaskCreateCrane import decouple_crane
            sel    = FreeCADGui.Selection.getSelection()
            cranes = [o for o in sel
                      if getattr(getattr(o, 'Proxy', None), 'Type', '') == 'ShipCrane']
            if cranes:
                decouple_crane(cranes[0])
            else:
                FreeCAD.Console.PrintWarning("Bitte einen Kran auswählen.\n")
        except Exception as e:
            FreeCAD.Console.PrintError(f"DecoupleCrane error: {e}\n")

    def GetResources(self):
        MenuText = QT_TRANSLATE_NOOP('Ship_DecoupleCrane', 'Decouple Crane')
        ToolTip  = QT_TRANSLATE_NOOP('Ship_DecoupleCrane', 'Decouple crane from ship')
        return {'Pixmap': 'Ship_DecoupleCrane', 'MenuText': MenuText, 'ToolTip': ToolTip}


class SingleHookLift:
    def IsActive(self):
        return FreeCAD.ActiveDocument is not None

    def Activated(self):
        try:
            from .shipCraneLoadout.TaskLiftOperation import SingleHookLiftDialog
            dlg = SingleHookLiftDialog(FreeCADGui.getMainWindow())
            dlg.exec_()
        except Exception as e:
            FreeCAD.Console.PrintError(f"SingleHookLift error: {e}\n")
            import traceback
            traceback.print_exc()

    def GetResources(self):
        MenuText = QT_TRANSLATE_NOOP('Ship_SingleHookLift', 'Single Hook Lift')
        ToolTip  = QT_TRANSLATE_NOOP('Ship_SingleHookLift', 'Single hook lift operation')
        return {'Pixmap': 'Ship_SingleHookLift', 'MenuText': MenuText, 'ToolTip': ToolTip}


class TandemLift:
    def IsActive(self):
        return FreeCAD.ActiveDocument is not None

    def Activated(self):
        try:
            from .shipCraneLoadout.TandemLift import show_tandem_lift_dialog
            show_tandem_lift_dialog()
        except Exception as e:
            FreeCAD.Console.PrintError(f"TandemLift error: {e}\n")
            import traceback
            traceback.print_exc()

    def GetResources(self):
        MenuText = QT_TRANSLATE_NOOP('Ship_TandemLift', 'Tandem Lift')
        ToolTip  = QT_TRANSLATE_NOOP('Ship_TandemLift', 'Tandem lift swing simulation')
        return {'Pixmap': 'Ship_TandemLift', 'MenuText': MenuText, 'ToolTip': ToolTip}


class StabilityMonitorCmd:
    """Öffnet schwebenden Stabilitätsmonitor für Kran-Operationen."""
    _monitor_instance = None

    def IsActive(self):
        return FreeCAD.ActiveDocument is not None

    def Activated(self):
        try:
            from .shipSinkAndTrim.StabilityMonitor import show_stability_monitor
            StabilityMonitorCmd._monitor_instance = show_stability_monitor()
        except Exception as e:
            FreeCAD.Console.PrintError(f"StabilityMonitor error: {e}\n")
            import traceback
            traceback.print_exc()

    def GetResources(self):
        MenuText = QT_TRANSLATE_NOOP('Ship_StabilityMonitor', 'Stability Monitor')
        ToolTip  = QT_TRANSLATE_NOOP('Ship_StabilityMonitor',
                                     'Open floating stability monitor for crane operations')
        return {'Pixmap': 'Ship_Monitor', 'MenuText': MenuText, 'ToolTip': ToolTip}



class StandaloneRigging:
    def IsActive(self):
        return True   # kein Dokument nötig – standalone

    def Activated(self):
        try:
            from .shipCraneLoadout.lifting_arrangement_standalone import show
            show()
        except Exception as e:
            FreeCAD.Console.PrintError(f"StandaloneRigging error: {e}\n")
            import traceback
            traceback.print_exc()

    def GetResources(self):
        import os
        icon_path = os.path.join(os.path.dirname(__file__),
                                 'shipCraneLoadout', 'rigging_icon.svg')
        MenuText = QT_TRANSLATE_NOOP('Ship_StandaloneRigging', 'Lifting Arrangement')
        ToolTip  = QT_TRANSLATE_NOOP('Ship_StandaloneRigging', 'Standalone rigging design without ship context')
        return {
            'Pixmap':   'rigging_icon',
            'MenuText': MenuText,
            'ToolTip':  ToolTip,
        }

# ===========================================================================
# Command-Registrierung
# ===========================================================================

FreeCADGui.addCommand('Ship_Read_Packinglist',          CargoStowagePlan())
#FreeCADGui.addCommand('Ship_LoadExample',               LoadExample())
FreeCADGui.addCommand('Ship_CreateShip',                CreateShip())
FreeCADGui.addCommand('Ship_AreasCurve',                AreasCurve())
FreeCADGui.addCommand('Ship_Hydrostatics',              Hydrostatics())
FreeCADGui.addCommand('Ship_Weight',                    CreateWeight())
FreeCADGui.addCommand('Ship_Tank',                      CreateTank())
FreeCADGui.addCommand('Ship_Capacity',                  TankCapacity())
FreeCADGui.addCommand('Ship_LoadCondition',             LoadCondition())
FreeCADGui.addCommand('Ship_CalculateLoadCondition',    CalculateLoadCondition())
FreeCADGui.addCommand('Ship_SinkAndTrim',               SinkAndTrim())
FreeCADGui.addCommand('Ship_GZ',                        GZ())
FreeCADGui.addCommand('Ship_ResistanceAmadeo',          Amadeo())
FreeCADGui.addCommand('Ship_ResistanceBlountFox',       BlountFox())
FreeCADGui.addCommand('Ship_ResistanceHoltrop',         Holtrop())
FreeCADGui.addCommand('Ship_ResistanceSavitsky',        Savitsky())
FreeCADGui.addCommand('Ship_SeakeepingSetMesh',         SetMesh())
FreeCADGui.addCommand('Ship_SeakeepingRAOs',            RAOs())
FreeCADGui.addCommand('Ship_CreateCapytaineMesh',       CreateCapytaineMesh())
FreeCADGui.addCommand('Ship_CreateCrane',               CreateCrane())
FreeCADGui.addCommand('Ship_CoupleCrane',               CoupleCrane())
FreeCADGui.addCommand('Ship_DecoupleCrane',             DecoupleCrane())
FreeCADGui.addCommand('Ship_SingleHookLift',            SingleHookLift())
FreeCADGui.addCommand('Ship_TandemLift',                TandemLift())
FreeCADGui.addCommand('Ship_StabilityMonitor',          StabilityMonitorCmd())
FreeCADGui.addCommand('Ship_StandaloneRigging', StandaloneRigging())
