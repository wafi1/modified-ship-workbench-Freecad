#***************************************************************************
#*   GF_Parser_Safe.py - SICHERE Version mit Debug-Output                   *
#***************************************************************************

import FreeCAD as App
import Part


class GF_Parser_Safe:
    """Sichere Version - nur Parsing, kein Loft"""
    
    def __init__(self):
        self.stations = []
        self.unit = "ft"
        self.name = "HULL"
        
    def parse_file(self, file_path):
        """Parst GF-Datei - SICHER"""
        App.Console.PrintMessage(f"\n{'='*70}\n")
        App.Console.PrintMessage(f"GF PARSER SAFE: START\n")
        App.Console.PrintMessage(f"Datei: {file_path}\n")
        App.Console.PrintMessage(f"{'='*70}\n")
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
            
            App.Console.PrintMessage(f"✓ Datei gelesen: {len(lines)} Zeilen\n")
        except Exception as e:
            App.Console.PrintError(f"✗ Lesen fehlgeschlagen: {e}\n")
            return False
        
        i = 0
        max_iterations = len(lines) * 2  # Sicherheit gegen Endlosschleife
        iteration_count = 0
        
        while i < len(lines):
            iteration_count += 1
            
            # SICHERHEIT: Verhindere Endlosschleife
            if iteration_count > max_iterations:
                App.Console.PrintError(f"✗ ABBRUCH: Zu viele Iterationen ({iteration_count})\n")
                break
            
            line = lines[i].strip()
            
            # Debug alle 100 Zeilen
            if i % 100 == 0:
                App.Console.PrintMessage(f"  Zeile {i}/{len(lines)}...\n")
            
            # Leere Zeilen / Kommentare
            if not line or line.startswith('*') or line.startswith('#'):
                i += 1
                continue
            
            # Header
            if 'New Geometry File' in line or 'P:M' in line:
                App.Console.PrintMessage(f"  Header: {line}\n")
                i += 1
                continue
            
            # Rumpf-Name
            if any(word in line.upper() for word in ['HULL', 'RUMPF']):
                parts = line.split()
                if parts:
                    self.name = parts[0]
                App.Console.PrintMessage(f"→ Rumpf: {self.name}\n")
                i += 1
                continue
            
            # Anzahl Spanten
            try:
                n_stations = int(line.strip())
                if 10 <= n_stations <= 200:
                    App.Console.PrintMessage(f"→ Anzahl Spanten: {n_stations}\n")
                    i += 1
                    continue
            except ValueError:
                pass
            
            # Spant-Definition: X, N_Points
            if ',' in line:
                parts = line.split(',')
                if len(parts) == 2:
                    try:
                        x_pos = float(parts[0].strip())
                        n_points = int(parts[1].strip())
                        
                        App.Console.PrintMessage(f"  → Spant bei X={x_pos:.2f}, {n_points} Punkte\n")
                        
                        # Lese Punkte
                        points = []
                        for j in range(n_points):
                            i += 1
                            if i >= len(lines):
                                App.Console.PrintWarning(f"    ⚠ Dateiende erreicht\n")
                                break
                            
                            point_line = lines[i].strip()
                            if not point_line or point_line.startswith('*'):
                                continue
                            
                            point_parts = point_line.split(',')
                            if len(point_parts) >= 2:
                                y = float(point_parts[0].strip())
                                z = float(point_parts[1].strip())
                                points.append((y, z))
                        
                        if points:
                            self.stations.append({
                                'x': x_pos,
                                'points': points
                            })
                            App.Console.PrintMessage(
                                f"    ✓ Spant {len(self.stations)}: {len(points)} Punkte geladen\n")
                        
                    except (ValueError, IndexError) as e:
                        App.Console.PrintWarning(f"    ⚠ Parse-Fehler: {e}\n")
            
            i += 1
        
        App.Console.PrintMessage(f"\n{'='*70}\n")
        App.Console.PrintMessage(f"PARSING ABGESCHLOSSEN\n")
        App.Console.PrintMessage(f"  {len(self.stations)} Spanten geladen\n")
        App.Console.PrintMessage(f"  {iteration_count} Zeilen verarbeitet\n")
        App.Console.PrintMessage(f"{'='*70}\n\n")
        
        if not self.stations:
            App.Console.PrintError(f"✗ Keine Spanten gefunden!\n")
            return False
        
        self._detect_unit()
        return True
    
    def _detect_unit(self):
        """Erkennt Einheit"""
        if not self.stations:
            return
        
        max_y = 0
        for station in self.stations:
            for y, z in station['points']:
                max_y = max(max_y, abs(y))
        
        if max_y > 50:
            self.unit = "ft"
            App.Console.PrintMessage(f"→ Einheit: FOOT (max Y={max_y:.1f}ft)\n")
        else:
            self.unit = "m"
            App.Console.PrintMessage(f"→ Einheit: METER (max Y={max_y:.1f}m)\n")
    
    def convert_to_meter(self):
        """Konvertiert zu Meter"""
        if self.unit != "ft":
            return
        
        App.Console.PrintMessage(f"→ Konvertiere Foot → Meter...\n")
        
        for station in self.stations:
            station['x'] *= 0.3048
            station['points'] = [(y * 0.3048, z * 0.3048) for y, z in station['points']]
        
        self.unit = "m"
        App.Console.PrintMessage(f"  ✓ Konvertierung abgeschlossen\n")
    
    def create_wires_only(self, doc):
        """Erstellt NUR Wires - KEIN LOFT (kann nicht hängen)"""
        App.Console.PrintMessage(f"\n{'='*70}\n")
        App.Console.PrintMessage(f"ERSTELLE WIRES (kein Loft)\n")
        App.Console.PrintMessage(f"{'='*70}\n")
        
        self.convert_to_meter()
        
        wires = []
        
        for i, station in enumerate(self.stations):
            if i % 10 == 0:
                App.Console.PrintMessage(f"  Wire {i+1}/{len(self.stations)}...\n")
            
            x = station['x'] * 1000  # m → mm
            points = station['points']
            
            if len(points) < 2:
                App.Console.PrintWarning(f"  ⚠ Spant {i+1}: Zu wenig Punkte ({len(points)})\n")
                continue
            
            profile_points = []
            
            # Backbord (gespiegelt)
            for y, z in reversed(points):
                if abs(y) > 0.001:
                    profile_points.append(App.Vector(x, -y * 1000, z * 1000))
            
            # Steuerbord
            for y, z in points:
                profile_points.append(App.Vector(x, y * 1000, z * 1000))
            
            # Schließen
            if profile_points:
                profile_points.append(profile_points[0])
                
                try:
                    edges = []
                    for j in range(len(profile_points) - 1):
                        edge = Part.makeLine(profile_points[j], profile_points[j+1])
                        edges.append(edge)
                    
                    wire = Part.Wire(edges)
                    wires.append(wire)
                    
                except Exception as e:
                    App.Console.PrintWarning(f"  ⚠ Spant {i+1}: Wire-Fehler: {e}\n")
        
        App.Console.PrintMessage(f"\n✓ {len(wires)} Wires erstellt\n")
        
        if not wires:
            raise Exception("Keine Wires erstellt")
        
        # Erstelle Compound (NUR Wires, kein Loft!)
        compound = Part.makeCompound(wires)
        
        wire_obj = doc.addObject("Part::Feature", "GF_Frames")
        wire_obj.Shape = compound
        wire_obj.Label = f"{self.name}_Frames"
        
        doc.recompute()
        
        App.Console.PrintMessage(f"✓ Wire-Objekt '{wire_obj.Label}' erstellt\n")
        App.Console.PrintMessage(f"\n⚠ WICHTIG: Nur Wires - KEIN Solid!\n")
        App.Console.PrintMessage(f"→ Für Solid: Manuell Loft in Part Workbench\n\n")
        
        return wire_obj
    
    def get_dimensions(self):
        """Dimensionen"""
        if not self.stations:
            return 0, 0, 0
        
        self.convert_to_meter()
        
        x_min = min(s['x'] for s in self.stations)
        x_max = max(s['x'] for s in self.stations)
        length = x_max - x_min
        
        breadth = 0
        depth = 0
        
        for station in self.stations:
            for y, z in station['points']:
                breadth = max(breadth, abs(y))
                depth = max(depth, z)
        
        breadth *= 2  # Beide Seiten
        
        return length, breadth, depth


def parse_gf_file(file_path, doc):
    """
    SICHERE Haupt-Funktion
    Erstellt NUR Wires - KEIN automatisches Loft!
    """
    App.Console.PrintMessage(f"\n" + "="*70 + "\n")
    App.Console.PrintMessage(f"GF-IMPORT SAFE MODE\n")
    App.Console.PrintMessage(f"="*70 + "\n\n")
    
    parser = GF_Parser_Safe()
    
    try:
        # Schritt 1: Parse
        App.Console.PrintMessage(f"SCHRITT 1: PARSING\n")
        if not parser.parse_file(file_path):
            App.Console.PrintError(f"✗ Parsing fehlgeschlagen\n")
            return None, 0, 0, 0
        
        # Schritt 2: Wires (OHNE Loft!)
        App.Console.PrintMessage(f"\nSCHRITT 2: WIRES ERSTELLEN\n")
        wire_obj = parser.create_wires_only(doc)
        
        # Schritt 3: Dimensionen
        App.Console.PrintMessage(f"\nSCHRITT 3: DIMENSIONEN\n")
        length, breadth, depth = parser.get_dimensions()
        
        App.Console.PrintMessage(f"\n{'='*70}\n")
        App.Console.PrintMessage(f"ERGEBNIS:\n")
        App.Console.PrintMessage(f"  Länge:  {length:.2f} m\n")
        App.Console.PrintMessage(f"  Breite: {breadth:.2f} m\n")
        App.Console.PrintMessage(f"  Höhe:   {depth:.2f} m\n")
        App.Console.PrintMessage(f"\n  ⚠ NUR WIRES - für Solid: Part → Loft\n")
        App.Console.PrintMessage(f"{'='*70}\n\n")
        
        return wire_obj, length, breadth, depth
        
    except Exception as e:
        App.Console.PrintError(f"\n✗ FEHLER: {e}\n")
        import traceback
        traceback.print_exc()
        return None, 0, 0, 0
