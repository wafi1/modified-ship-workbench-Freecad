#***************************************************************************
#*   GeometryConverter.py - WASSERDICHTE Solid-Erzeugung                    *
#***************************************************************************/

import FreeCAD as App
import Part
import Mesh
import MeshPart

class GeometryConverter:
    """Konvertiert Mesh zu wasserdichtem Solid"""
    
    def __init__(self):
        self.debug = True
        self.tolerance = 0.1
        
    def convert_mesh_to_solid(self, mesh_object):
        """Konvertiert Mesh zu wasserdichtem Solid"""
        
        if self.debug:
            App.Console.PrintMessage("=== GeometryConverter: Mesh→Solid (wasserdicht) ===\n")
        
        mesh = self._get_mesh_copy(mesh_object)
        
        # WICHTIG: Mesh muss geschlossen sein für gültiges Solid!
        if not self._is_mesh_closed(mesh):
            App.Console.PrintWarning("⚠ Mesh ist nicht geschlossen! Versuche zu schließen...\n")
            mesh = self._close_mesh(mesh)
        
        # VERSUCH 1: MeshPart.meshToShape (robuster als makeShapeFromMesh)
        if self.debug:
            App.Console.PrintMessage("→ Versuch 1: MeshPart.meshToShape...\n")
        solid = self._try_meshpart_conversion(mesh)
        if solid:
            return solid
        
        # VERSUCH 2: Mit höherer Toleranz
        if self.debug:
            App.Console.PrintMessage("→ Versuch 2: Höhere Toleranz...\n")
        solid = self._try_high_tolerance(mesh)
        if solid:
            return solid
        
        # VERSUCH 3: Manueller Shell-Aufbau mit Füllung
        if self.debug:
            App.Console.PrintMessage("→ Versuch 3: Manueller Aufbau...\n")
        solid = self._try_manual_shell(mesh)
        if solid:
            return solid
        
        App.Console.PrintError("=== KONVERTIERUNG FEHLGESCHLAGEN ===\n")
        return None
    
    def _is_mesh_closed(self, mesh):
        """Prüft ob Mesh geschlossen ist"""
        try:
            # Ein geschlossenes Mesh hat keine freien Kanten
            # MeshPart kann das prüfen
            return mesh.isSolid()
        except:
            # Fallback: Prüfe auf Boundary-Faces
            try:
                shape = Part.Shape()
                shape.makeShapeFromMesh(mesh.Topology, 0.1)
                # Wenn es ein Solid wird, war es geschlossen
                return len(shape.Solids) > 0
            except:
                return False
    
    def _close_mesh(self, mesh):
        """Versucht Mesh zu schließen"""
        try:
            # Füge fehlende Facets hinzu wo möglich
            mesh.fillupHoles()
            # Entferne doppelte Punkte die zu Lücken führen
            mesh.removeDuplicatedPoints()
            # Harmonisiere Normalen (wichtig für Richtung!)
            mesh.harmonizeNormals()
            return mesh
        except Exception as e:
            App.Console.PrintWarning(f"  Konnte Mesh nicht schließen: {e}\n")
            return mesh
    
    def _try_meshpart_conversion(self, mesh):
        """Verwendet MeshPart (robusteste Methode)"""
        try:
            # MeshPart.meshToShape erzeugt direkt eine Shell
            shape = MeshPart.meshToShape(mesh)
            
            if not shape or not shape.Faces:
                return None
            
            if self.debug:
                App.Console.PrintMessage(f"  → {len(shape.Faces)} Faces erzeugt\n")
            
            # Versuche geschlossene Shell zu machen
            shell = Part.Shell(shape.Faces)
            
            if not shell.isValid():
                # Versuche Shell zu reparieren
                shell = shell.sewShape()
            
            if shell.isValid():
                try:
                    solid = Part.Solid(shell)
                    if solid.isValid():
                        if self.debug:
                            App.Console.PrintMessage("  ✓ Wasserdichtes Solid erzeugt\n")
                        return self._create_feature(solid, "Ship_Hull_MeshPart")
                except:
                    pass
            
            # Wenn nicht geschlossen, versuche zu füllen
            return self._try_close_shell(shell)
            
        except Exception as e:
            if self.debug:
                App.Console.PrintMessage(f"  ✗ MeshPart: {e}\n")
            return None
    
    def _try_high_tolerance(self, mesh):
        """Versucht mit höherer Toleranz für problematische Meshes"""
        for tol in [0.5, 1.0, 2.0]:
            try:
                shape = Part.Shape()
                shape.makeShapeFromMesh(mesh.Topology, tol)
                
                if shape.Solids and shape.Solids[0].isValid():
                    if self.debug:
                        App.Console.PrintMessage(f"  ✓ Mit Toleranz {tol}m erfolgreich\n")
                    return self._create_feature(shape.Solids[0], f"Ship_Hull_Tol{tol}")
                
                # Versuche aus Shell Solid zu machen
                if shape.Shells:
                    solid = Part.Solid(shape.Shells[0])
                    if solid.isValid():
                        return self._create_feature(solid, f"Ship_Hull_Tol{tol}")
                        
            except Exception as e:
                continue
        
        return None
    
    def _try_manual_shell(self, mesh):
        """Manueller Aufbau mit individueller Face-Prüfung"""
        try:
            # Erzeuge Shape mit niedriger Toleranz
            shape = Part.Shape()
            shape.makeShapeFromMesh(mesh.Topology, 0.01)
            
            if not shape.Faces:
                return None
            
            # Prüfe jedes Face auf Validität
            valid_faces = []
            for i, face in enumerate(shape.Faces):
                try:
                    if face.isValid() and face.Area > 1e-6:
                        valid_faces.append(face)
                except:
                    pass
            
            if self.debug:
                App.Console.PrintMessage(f"  → {len(valid_faces)}/{len(shape.Faces)} Faces valide\n")
            
            if len(valid_faces) < 4:
                return None
            
            # Baue Shell aus validen Faces
            shell = Part.Shell(valid_faces)
            
            if not shell.isValid():
                # Versuche zu nähen
                try:
                    shell.sewShape()
                except:
                    pass
            
            if shell.isValid():
                try:
                    solid = Part.Solid(shell)
                    if solid.isValid():
                        return self._create_feature(solid, "Ship_Hull_Manual")
                except:
                    pass
            
            return self._try_close_shell(shell)
            
        except Exception as e:
            if self.debug:
                App.Console.PrintMessage(f"  ✗ Manuell: {e}\n")
            return None
    
    def _try_close_shell(self, shell):
        """Versucht eine offene Shell zu schließen"""
        try:
            # Finde freie Kanten
            free_edges = []
            for edge in shell.Edges:
                # Zähle wie oft die Kante in Faces vorkommt
                count = sum(1 for f in shell.Faces if edge in f.Edges)
                if count == 1:
                    free_edges.append(edge)
            
            if not free_edges:
                # Schon geschlossen?
                try:
                    solid = Part.Solid(shell)
                    if solid.isValid():
                        return self._create_feature(solid, "Ship_Hull_Closed")
                except:
                    pass
                return None
            
            if self.debug:
                App.Console.PrintMessage(f"  → {len(free_edges)} freie Kanten gefunden\n")
            
            # Versuche Löcher zu füllen (vereinfacht)
            # Für Schiffe: Meistens Deck oder Boden offen
            # Wir akzeptieren das Shell-Solid für die Hydrostatik
            # wenn es "fast" geschlossen ist
            
            if len(free_edges) < len(shell.Edges) * 0.1:  # < 10% offen
                App.Console.PrintWarning("  ⚠ Shell ist fast geschlossen, verwende trotzdem\n")
                # Erstelle ein "fettes" Solid durch Offset
                try:
                    # Versuche mit kleinem Offset zu schließen
                    offset = shell.makeOffsetShape(0.1, 0.01, fill=True)
                    if offset.Solids:
                        return self._create_feature(offset.Solids[0], "Ship_Hull_Patched")
                except:
                    pass
            
            return None
            
        except Exception as e:
            if self.debug:
                App.Console.PrintMessage(f"  ✗ Close shell: {e}\n")
            return None
    
    def _create_feature(self, shape, name):
        """Erstellt Part::Feature aus Shape"""
        try:
            doc = App.ActiveDocument
            obj = doc.addObject("Part::Feature", name)
            obj.Shape = shape
            
            # WICHTIG: Prüfe Bounding Box
            if not obj.Shape.BoundBox.isValid():
                App.Console.PrintError("  ✗ Bounding Box ungültig!\n")
                doc.removeObject(obj.Name)
                return None
            
            doc.recompute()
            
            if self.debug:
                bbox = obj.Shape.BoundBox
                App.Console.PrintMessage(f"  ✓ {name} erstellt\n")
                App.Console.PrintMessage(f"    BBox: {bbox.XLength:.1f} x {bbox.YLength:.1f} x {bbox.ZLength:.1f}\n")
            
            return obj
            
        except Exception as e:
            App.Console.PrintError(f"  ✗ Feature erstellen: {e}\n")
            return None
    
    def _get_mesh_copy(self, mesh_object):
        """Holt Mesh als Kopie"""
        if hasattr(mesh_object, 'Mesh'):
            return mesh_object.Mesh.copy()
        else:
            return mesh_object.copy()


# Hilfsfunktionen
def mesh_to_solid(mesh_object):
    """Einfache Hilfsfunktion"""
    converter = GeometryConverter()
    return converter.convert_mesh_to_solid(mesh_object)


def check_solid_validity(solid_obj):
    """Prüft ob Solid für Hydrostatik geeignet ist"""
    if not solid_obj or not hasattr(solid_obj, 'Shape'):
        return False, "Kein Objekt"
    
    shape = solid_obj.Shape
    
    checks = {
        "isValid": shape.isValid(),
        "hasBBox": shape.BoundBox.isValid() if hasattr(shape, 'BoundBox') else False,
        "isSolid": len(shape.Solids) > 0,
        "volume": shape.Volume if hasattr(shape, 'Volume') else 0,
    }
    
    errors = [k for k, v in checks.items() if not v]
    
    if errors:
        return False, f"Fehler: {', '.join(errors)}"
    
    return True, f"OK: Vol={checks['volume']:.2f}m³"
