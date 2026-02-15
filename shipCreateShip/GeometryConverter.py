#***************************************************************************
#*   GeometryConverter.py - KORRIGIERT: Keine Box mehr!                      *
#***************************************************************************/

import FreeCAD as App
import Part
import Mesh

class GeometryConverter:
    """Konvertiert Mesh zu Solid - korrekt ohne Box-Fallback"""
    
    def __init__(self):
        self.debug = True
        self.tolerance = 0.1
        
    def convert_mesh_to_solid(self, mesh_object):
        """Konvertiert Mesh zu Solid"""
        
        if self.debug:
            App.Console.PrintMessage("=== GeometryConverter: Mesh→Solid ===\n")
        
        # VERSUCH 1: Direkte Konvertierung
        if self.debug:
            App.Console.PrintMessage("→ Versuch 1: Direkte Konvertierung...\n")
        solid = self._try_direct_conversion(mesh_object)
        if solid:
            if self.debug:
                App.Console.PrintMessage("✓ Versuch 1 erfolgreich\n")
            return solid
        
        # VERSUCH 2: Mit Reparatur
        if self.debug:
            App.Console.PrintMessage("→ Versuch 2: Mit Reparatur...\n")
        solid = self._try_repair_conversion(mesh_object)
        if solid:
            if self.debug:
                App.Console.PrintMessage("✓ Versuch 2 erfolgreich\n")
            return solid
        
        # VERSUCH 3: Aus Faces bauen
        if self.debug:
            App.Console.PrintMessage("→ Versuch 3: Aus Faces...\n")
        solid = self._try_from_faces(mesh_object)
        if solid:
            if self.debug:
                App.Console.PrintMessage("✓ Versuch 3 erfolgreich\n")
            return solid
        
        App.Console.PrintWarning("=== ALLE VERSUCHE FEHLGESCHLAGEN ===\n")
        App.Console.PrintWarning("Bitte Mesh manuell reparieren (Mesh→Analyze→Evaluate & Repair)\n")
        return None
    
    def _get_mesh_copy(self, mesh_object):
        """Holt Mesh als Kopie"""
        if hasattr(mesh_object, 'Mesh'):
            return mesh_object.Mesh.copy()
        else:
            return mesh_object.copy()
    
    def _try_direct_conversion(self, mesh_object):
        """Direkte Konvertierung ohne Reparatur"""
        try:
            mesh = self._get_mesh_copy(mesh_object)
            
            shape = Part.Shape()
            shape.makeShapeFromMesh(mesh.Topology, self.tolerance)
            
            if not shape.isValid():
                return None
            
            # Direktes Solid?
            if shape.Solids:
                doc = App.ActiveDocument
                solid_obj = doc.addObject("Part::Feature", "Hull_Solid")
                solid_obj.Shape = shape.Solids[0]
                solid_obj.Label = "Ship_Hull_Direct"
                return solid_obj
            
            # Aus Shell
            if shape.Shells:
                shell = shape.Shells[0]
                solid_shape = Part.Solid(shell)
                if solid_shape.isValid():
                    doc = App.ActiveDocument
                    solid_obj = doc.addObject("Part::Feature", "Hull_Solid")
                    solid_obj.Shape = solid_shape
                    solid_obj.Label = "Ship_Hull_Shell"
                    return solid_obj
            
            return None
            
        except Exception as e:
            if self.debug:
                App.Console.PrintMessage(f"  ✗ Direkt: {e}\n")
            return None
    
    def _try_repair_conversion(self, mesh_object):
        """Konvertierung mit Mesh-Reparatur"""
        try:
            mesh = self._get_mesh_copy(mesh_object)
            
            if self.debug:
                App.Console.PrintMessage(f"  Vor Reparatur: {mesh.CountPoints} Punkte\n")
            
            # Reparatur
            mesh.fixDegenerations()
            mesh.removeDuplicatedPoints()
            mesh.removeDuplicatedFacets()
            
            if self.debug:
                App.Console.PrintMessage(f"  Nach Reparatur: {mesh.CountPoints} Punkte\n")
            
            # Versuche mit verschiedenen Toleranzen
            for tol in [0.1, 0.5, 1.0]:
                if self.debug:
                    App.Console.PrintMessage(f"  → Toleranz {tol}...\n")
                
                shape = Part.Shape()
                shape.makeShapeFromMesh(mesh.Topology, tol)
                
                if shape.isValid():
                    if self.debug:
                        App.Console.PrintMessage(f"    ✓ Shape valide mit Toleranz {tol}\n")
                    
                    if shape.Solids:
                        doc = App.ActiveDocument
                        solid_obj = doc.addObject("Part::Feature", "Hull_Solid")
                        solid_obj.Shape = shape.Solids[0]
                        solid_obj.Label = f"Ship_Hull_tol{tol}"
                        return solid_obj
                    
                    if shape.Shells:
                        try:
                            solid_shape = Part.Solid(shape.Shells[0])
                            if solid_shape.isValid():
                                doc = App.ActiveDocument
                                solid_obj = doc.addObject("Part::Feature", "Hull_Solid")
                                solid_obj.Shape = solid_shape
                                solid_obj.Label = f"Ship_Hull_Shell{tol}"
                                return solid_obj
                        except:
                            pass
            
            return None
            
        except Exception as e:
            if self.debug:
                App.Console.PrintMessage(f"  ✗ Reparatur: {e}\n")
            return None
    
    def _try_from_faces(self, mesh_object):
        """Versucht aus Faces ein Solid zu bauen"""
        try:
            mesh = self._get_mesh_copy(mesh_object)
            
            shape = Part.Shape()
            shape.makeShapeFromMesh(mesh.Topology, 0.1)
            
            if not shape.isValid() or not shape.Faces:
                return None
            
            if self.debug:
                App.Console.PrintMessage(f"  → {len(shape.Faces)} Faces gefunden\n")
            
            # Versuche alle Faces zu einer Shell zu verbinden
            try:
                shell = Part.Shell(shape.Faces)
                if shell.isValid():
                    if self.debug:
                        App.Console.PrintMessage("    ✓ Shell erstellt\n")
                    
                    solid_shape = Part.Solid(shell)
                    if solid_shape.isValid():
                        doc = App.ActiveDocument
                        solid_obj = doc.addObject("Part::Feature", "Hull_Solid")
                        solid_obj.Shape = solid_shape
                        solid_obj.Label = "Ship_Hull_Faces"
                        return solid_obj
            except Exception as e:
                if self.debug:
                    App.Console.PrintMessage(f"    ✗ Shell failed: {e}\n")
            
            return None
            
        except Exception as e:
            if self.debug:
                App.Console.PrintMessage(f"  ✗ Faces: {e}\n")
            return None


# Hilfsfunktion
def mesh_to_solid(mesh_object):
    """Einfache Hilfsfunktion"""
    converter = GeometryConverter()
    return converter.convert_mesh_to_solid(mesh_object)


def solidify_half_hull(mesh_object, center_plane='YZ'):
    """Spiegelt Hälfte und erzeugt Solid"""
    try:
        App.Console.PrintMessage("=== Spiegelung Hälfte → Ganzes ===\n")
        
        mesh = mesh_object.Mesh.copy() if hasattr(mesh_object, 'Mesh') else mesh_object.copy()
        
        # Spiegeln
        mirrored = mesh.copy()
        if center_plane == 'YZ':
            transform = App.Matrix()
            transform.A11 = -1
        else:
            transform = App.Matrix()
            transform.A22 = -1
        
        mirrored.transform(transform)
        
        # Kombinieren
        combined = Mesh.Mesh()
        combined.addMesh(mesh)
        combined.addMesh(mirrored)
        
        App.Console.PrintMessage(f"→ Kombiniert: {combined.CountPoints} Punkte\n")
        
        # Konvertieren
        shape = Part.Shape()
        shape.makeShapeFromMesh(combined.Topology, 0.1)
        
        if not shape.isValid():
            App.Console.PrintError("  ✗ Shape ungültig\n")
            return None
        
        if shape.Solids:
            solid_shape = shape.Solids[0]
        elif shape.Shells:
            solid_shape = Part.Solid(shape.Shells[0])
        else:
            App.Console.PrintError("  ✗ Kein Solid möglich\n")
            return None
        
        if solid_shape.isValid():
            doc = App.ActiveDocument
            solid = doc.addObject("Part::Feature", "Ship_Hull_Full")
            solid.Shape = solid_shape
            solid.Label = "Ship_Hull_Complete"
            return solid
        
        return None
        
    except Exception as e:
        App.Console.PrintError(f"  ✗ Fehler: {e}\n")
        return None
