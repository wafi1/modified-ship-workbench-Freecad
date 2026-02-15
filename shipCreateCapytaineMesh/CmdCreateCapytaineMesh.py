#***************************************************************************
#*                                                                         *
#*   CmdCreateCapytaineMesh.py                                             *
#*                                                                         *
#*   FreeCAD-Command um das Capytaine Mesh Tool in der                     *
#*   Seakeeping-Workbench zu registrieren.                                 *
#*                                                                         *
#*   Verwendung in InitGui.py / __init__.py der Workbench:                 *
#*                                                                         *
#*     from .seakeepingRAOs import CmdCreateCapytaineMesh                  *
#*     FreeCADGui.addCommand('Seakeeping_CreateCapytaineMesh',             *
#*                           CmdCreateCapytaineMesh.CreateCapytaineMesh()) *
#*                                                                         *
#*   Dann in der Toolbar/Menu:                                             *
#*     self.appendToolbar("Seakeeping",                                    *
#*         ['Seakeeping_CreateCapytaineMesh'])                             *
#*                                                                         *
#*   GNU LGPL — see LICENCE text file for details.                        *
#*                                                                         *
#***************************************************************************

import FreeCAD as App
import FreeCADGui as Gui
from . import TaskPanel_CreateCapytaineMesh as TaskPanelModule


class CreateCapytaineMesh:
    """FreeCAD Command: Capytaine BEM Mesh erstellen."""

    def GetResources(self):
        return {
            'Pixmap':   'Ship_MeshCreate',           # Icon (aus Ressourcen)
            'MenuText': 'Create Capytaine Mesh',
            'ToolTip':  (
                'Creates a boundary element mesh from the ship hull shape\n'
                'suitable for Capytaine BEM seakeeping analysis.\n\n'
                'Steps:\n'
                '  1. Select ship object\n'
                '  2. Set draft and mesh density\n'
                '  3. Choose half-model (recommended) or full model\n'
                '  4. Click OK to create mesh'
            ),
            'Accel':    ''
        }

    def IsActive(self):
        """Tool ist aktiv wenn ein FreeCAD-Dokument geöffnet ist."""
        return App.ActiveDocument is not None

    def Activated(self):
        """Tool starten."""
        TaskPanelModule.createTask()


# Registrierung (wird beim Import ausgeführt wenn direkt aufgerufen)
if __name__ != '__main__':
    try:
        Gui.addCommand('Seakeeping_CreateCapytaineMesh', CreateCapytaineMesh())
    except Exception as e:
        App.Console.PrintWarning(
            f"CmdCreateCapytaineMesh: Konnte Command nicht registrieren: {e}\n")
