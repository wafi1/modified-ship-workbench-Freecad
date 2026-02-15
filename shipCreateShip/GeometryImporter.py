#***************************************************************************
#*   GeometryImporter.py - Lädt verschiedene Dateiformate                 *
#***************************************************************************

import os
import FreeCAD as App
import FreeCADGui as Gui
import Mesh
import Points
import Part
from PySide import QtGui

from .GeometryConverter import GeometryConverter

class GeometryImporter:
    """Importiert Geometrie aus verschiedenen Dateiformaten"""
    
    def __init__(self):
        self.converter = GeometryConverter()
        
    def import_file(self, file_path):
        """Hauptmethode - importiert eine Datei"""
        ext = os.path.splitext(file_path)[1].lower()
        
        App.Console.PrintMessage(f"\n=== Importiere {os.path.basename(file_path)} ===\n")
        
        if ext in ['.stl']:
            return self._import_stl(file_path)
        elif ext in ['.gf', '.gf1', '.txt']:
            return self._import_gf(file_path)
        elif ext in ['.iges', '.igs', '.step', '.stp']:
            return self._import_brep(file_path)
        else:
            raise Exception(f"Nicht unterstütztes Format: {ext}")
    
    def _import_stl(self, file_path):
        """Importiert STL und leitet Konvertierung ein"""
        doc = self._get_document()
        
        # STL als Mesh importieren
        mesh = Mesh.Mesh()
        mesh.read(file_path)
        
        mesh_obj = doc.addObject("Mesh::Feature", "Imported_STL")
        mesh_obj.Mesh = mesh
        mesh_obj.Label = f"STL_{os.path.basename(file_path)}"
        
        # Versuche zu konvertieren
        App.Console.PrintMessage("  Starte Konvertierung...\n")
        solid = self.converter.convert_mesh_to_solid(mesh_obj)
        
        if solid:
            # Konvertierung erfolgreich
            mesh_obj.ViewObject.Visibility = False
            App.Console.PrintMessage("  ✓ Konvertierung erfolgreich\n")
            return {
                'geometry': solid,
                'type': 'solid',
                'original': mesh_obj,
                'file': file_path
            }
        else:
            # Keine Konvertierung möglich
            App.Console.PrintMessage("  ⚠ Als Mesh behalten (keine Konvertierung)\n")
            return {
                'geometry': mesh_obj,
                'type': 'mesh',
                'original': None,
                'file': file_path
            }
    
    def _import_gf(self, file_path):
        """Importiert GF/GF1 Punktwolke"""
        doc = self._get_document()
        
        points = []
        with open(file_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    parts = line.split()
                    if len(parts) >= 3:
                        try:
                            points.append((
                                float(parts[0]), 
                                float(parts[1]), 
                                float(parts[2])
                            ))
                        except:
                            pass
        
        if not points:
            raise Exception("Keine gültigen Punkte gefunden")
        
        points_obj = doc.addObject("Points::Feature", "Imported_Points")
        points_obj.Points.addPoints(points)
        points_obj.Label = f"Points_{os.path.basename(file_path)}"
        
        App.Console.PrintMessage(f"  → {len(points)} Punkte importiert\n")
        
        # TODO: Punktwolken-Konvertierung
        return {
            'geometry': points_obj,
            'type': 'points',
            'original': None,
            'file': file_path,
            'point_count': len(points)
        }
    
    def _import_brep(self, file_path):
        """Importiert IGES/STEP"""
        doc = self._get_document()
        
        shape = Part.Shape()
        shape.read(file_path)
        
        if not shape.isValid():
            raise Exception("Ungültige Geometrie")
        
        if shape.Solids:
            solid = doc.addObject("Part::Feature", "Ship_Hull")
            solid.Shape = shape
            solid.Label = f"Hull_{os.path.basename(file_path)}"
            return {
                'geometry': solid,
                'type': 'solid',
                'original': None,
                'file': file_path
            }
        else:
            # Keine Solids - als Shape importieren
            feature = doc.addObject("Part::Feature", "Imported_Shape")
            feature.Shape = shape
            feature.Label = f"Shape_{os.path.basename(file_path)}"
            
            return {
                'geometry': feature,
                'type': 'shape',
                'original': None,
                'file': file_path
            }
    
    def _get_document(self):
        """Stellt sicher dass ein Dokument existiert"""
        if not App.ActiveDocument:
            App.newDocument("ShipDesign")
            App.Console.PrintMessage("✓ Neues Dokument 'ShipDesign' erstellt\n")
        return App.ActiveDocument
