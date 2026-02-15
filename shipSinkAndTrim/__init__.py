# shipSinkAndTrim/__init__.py
#***************************************************************************
#*                                                                         *
#*   Ship Sink and Trim Workbench Command                                  *
#*                                                                         *
#***************************************************************************

import FreeCAD as App
import FreeCADGui as Gui


class ShipSinkAndTrim:
    """Command to run Ship Sink and Trim analysis"""
    
    def GetResources(self):
        return {
            'Pixmap': ":/icons/Ship_SinkAndTrim.svg",  # HIER :/ EINFÜGEN
            'MenuText': "Sink and Trim",
            'ToolTip': "Calculate ship equilibrium position (draft and trim)"
        }
    
    def Activated(self):
        """Run when command is activated"""
        try:
            # Import and create task panel
            from .TaskPanel import createTask
            panel = createTask()
            
            if panel:
                Gui.Control.showDialog(panel)
            else:
                from PySide import QtGui
                QtGui.QMessageBox.critical(
                    None,
                    "Error",
                    "Could not create Sink and Trim task panel"
                )
                
        except Exception as e:
            print(f"Error in ShipSinkAndTrim command: {e}")
            import traceback
            traceback.print_exc()
    
    def IsActive(self):
        """Determine if command should be active"""
        return App.ActiveDocument is not None


# Add command to FreeCAD
Gui.addCommand('Ship_SinkAndTrim', ShipSinkAndTrim())
