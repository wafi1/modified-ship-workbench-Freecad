#***************************************************************************
#*                                                                         *
#*   LoadCondition Tools für Ship Workbench                                *
#*   Mit 3D-Cargo-Box Integration und bidirektionaler Verknüpfung          *
#*                                                                         *
#***************************************************************************

import os
import re
import math
import FreeCAD as App
import FreeCADGui as Gui
from FreeCAD import Vector, Units, Matrix, Placement, Rotation
import Part
import Spreadsheet
from datetime import datetime

# Farbdefinitionen
READ_ONLY_FOREGROUND = (0.5, 0.5, 0.5)
READ_ONLY_BACKGROUND = (0.9, 0.9, 0.9)
HEADER_BACKGROUND = (0.8, 0.8, 1.0)
TOTAL_BACKGROUND = (0.9, 1.0, 0.9)
WEIGHT_ROW_COLOR = (0.95, 0.95, 0.95)
TANK_ROW_COLOR = (0.95, 0.95, 1.0)
CARGO_ROW_COLOR = (0.95, 1.0, 0.95)
HYDRO_BACKGROUND = (1.0, 0.95, 0.9)

# Hafen-Farben für Visualisierung
PORT_COLORS = {
    "DEHAM": (1.0, 0.0, 0.0),      # Hamburg - Rot
    "NLRTM": (0.0, 1.0, 0.0),      # Rotterdam - Grün  
    "BEANR": (0.0, 0.0, 1.0),      # Antwerpen - Blau
    "SGSIN": (1.0, 0.5, 0.0),      # Singapur - Orange
    "CNHKG": (1.0, 0.0, 1.0),      # Hong Kong - Magenta
    "BUNKER": (0.5, 0.5, 0.5),     # Bunkern - Grau
    "INT": (0.0, 0.8, 0.8),        # Internal (Ballast) - Cyan
    "LOAD": (0.8, 0.4, 0.0),       # Generisch Laden
    "DISCH": (0.4, 0.4, 0.4),      # Generisch Löschen
}

PORT_BG_COLORS = {
    "DEHAM": (1.0, 0.8, 0.8),
    "NLRTM": (0.8, 1.0, 0.8),
    "BEANR": (0.8, 0.8, 1.0),
    "SGSIN": (1.0, 0.9, 0.8),
    "CNHKG": (1.0, 0.8, 1.0),
    "BUNKER": (0.9, 0.9, 0.9),
    "INT": (0.8, 0.95, 0.95),
    "LOAD": (0.95, 0.9, 0.8),
    "DISCH": (0.9, 0.9, 0.9),
}

# Globaler Speicher für Cargo-Box-Verknüpfungen (für Bidirektionalität)
_cargo_links = {}

# =============================================================================
# TEIL 1: HAUPTFUNKTION - LoadCondition erstellen
# =============================================================================

def createLoadCondition(ship):
    """Create a comprehensive loading condition with 3D Cargo integration"""
    
    # Cleanup existing cargo visualization
    _cleanupCargoVisualization()
    
    # Create the spreadsheet
    lc = App.activeDocument().addObject('Spreadsheet::Sheet', 'LoadCondition')
    
    # Set column widths
    _setupColumnWidths(lc)
    
    # Create header section
    current_row = _createHeaderSection(lc, ship)
    if current_row is None:
        current_row = 5  # Fallback
    
    # Create fixed result positions (for Sink&Trim compatibility)
    _createFixedResultFields(lc)
    
    # Create tanks section
    current_row = 10  # Start nach Header
    result = _createTanksSection(lc, current_row, ship)
    if result is not None:
        current_row = result
    else:
        print("Warning: _createTanksSection returned None, using fallback")
        current_row = 15
    
    # Create cargo section with 3D integration
    current_row += 1
    result = _createCargoSection(lc, current_row, ship)
    if result is not None:
        current_row = result
    else:
        print("Warning: _createCargoSection returned None, using fallback")
        current_row += 10
    
    # Create totals and hydrostatics
    current_row += 2
    _createTotalsSection(lc, current_row)
    
    # Initial calculation
    try:
        recalculateLoadCondition(lc, ship)
    except Exception as e:
        print("Error in initial calculation: " + str(e))
    
    # Add to ship
    if not hasattr(ship, 'LoadConditions'):
        ship.addProperty("App::PropertyStringList", "LoadConditions", "Ship", 
                        "List of loading conditions")
    
    lcs = ship.LoadConditions[:] if hasattr(ship, 'LoadConditions') else []
    lcs.append(lc.Name)
    ship.LoadConditions = lcs
    
    App.activeDocument().recompute()
    return lc


# =============================================================================
# TEIL 2: HILFSFUNKTIONEN FÜR SPREADSHEET-AUFBAU
# =============================================================================

def _setupColumnWidths(lc):
    """Setze Spaltenbreiten"""
    widths = {
        'A': 200,  # Name (erweitert für Hafencodes)
        'B': 100,  # Density
        'C': 80,   # Fill %
        'D': 120,  # Mass
        'E': 90,   # X
        'F': 90,   # Y
        'G': 90,   # Z
        'H': 110,  # Moment X
        'I': 110,  # Moment Y
        'J': 110,  # Moment Z
        'K': 140,  # Free Surface Moment
    }
    for col, width in widths.items():
        lc.setColumnWidth(col, width)


def _createHeaderSection(lc, ship):
    """Erstelle Header-Bereich"""
    # Titel
    lc.set("A1", "SHIP LOAD CONDITION ANALYSIS")
    lc.mergeCells('A1:K1')
    lc.setAlignment('A1', 'center', 'keep')  # KORREKTUR
    lc.setStyle('A1', 'bold', 'add')
    lc.setStyle('A1', 'underline', 'add')
    lc.setBackground('A1', HEADER_BACKGROUND)
    
    # Schiffsinfo
    lc.set("A2", "Ship:")
    lc.set("B2", ship.Label if hasattr(ship, 'Label') and ship.Label else ship.Name)
    lc.set("A3", "Created:")
    from datetime import datetime
    lc.set("B3", datetime.now().strftime("%Y-%m-%d %H:%M"))
    lc.set("A4", "Status:")
    lc.set("B4", "DRAFT")
    
    for row_num in ['2', '3', '4']:
        lc.setStyle('A' + row_num, 'bold', 'add')
        lc.setForeground('A' + row_num, READ_ONLY_FOREGROUND)
        lc.setBackground('A' + row_num + ':B' + row_num, READ_ONLY_BACKGROUND)
    
    return 5


def _createFixedResultFields(lc):
    """Fixe Positionen für Ergebnisse (Sink&Trim Kompatibilität)"""
    
    # Zeile 5: Total Mass und Free Surface
    lc.set("A5", "Total mass (kg)")
    lc.setAlignment("A5", "right", "keep")
    lc.setStyle("A5", "bold", "add")
    lc.setBackground("A5:D5", TOTAL_BACKGROUND)
    # D5 wird berechnet
    
    lc.set("J5", "Free surface moment (kg·m)")
    lc.setAlignment("J5", "right", "keep")
    lc.setStyle("J5", "bold", "add")
    lc.setBackground("J5:K5", TOTAL_BACKGROUND)
    # K5 wird berechnet
    
    # Zeile 6: COG
    lc.set("A6", "COG X (m)")
    lc.setAlignment("A6", "right", "keep")
    lc.setStyle("A6", "bold", "add")
    lc.setBackground("A6", TOTAL_BACKGROUND)
    
    lc.set("C6", "COG Y (m)")
    lc.setAlignment("C6", "right", "keep")
    lc.setStyle("C6", "bold", "add")
    lc.setBackground("C6", TOTAL_BACKGROUND)
    
    lc.set("E6", "COG Z (m)")
    lc.setAlignment("E6", "right", "keep")
    lc.setStyle("E6", "bold", "add")
    lc.setBackground("E6", TOTAL_BACKGROUND)
    
    # G6, H6, I6 sind die Werte
    lc.setBackground("G6", TOTAL_BACKGROUND)
    lc.setBackground("H6", TOTAL_BACKGROUND)
    lc.setBackground("I6", TOTAL_BACKGROUND)


def _createTanksSection(lc, start_row, ship):
    """Erstelle Tank-Sektion mit automatischer Einbindung"""
    row = start_row  # WICHTIG: row initialisieren!
    
    # Sektionsheader
    lc.mergeCells('A' + str(row) + ':K' + str(row))
    lc.set('A' + str(row), "TANKS (Ballast & Fuel)")
    lc.setAlignment('A' + str(row), 'center', 'keep')
    lc.setStyle('A' + str(row), 'bold', 'add')
    lc.setStyle('A' + str(row), 'underline', 'add')
    lc.setBackground('A' + str(row), TANK_ROW_COLOR)
    row += 1
    
    # Spaltenheader
    headers = ["[Load→Disch] Name", "Density", "Fill %", "Mass (kg)", 
               "LCG (m)", "TCG (m)", "VCG (m)", 
               "Mom X", "Mom Y", "Mom Z", "FS Moment"]
    
    for i, header in enumerate(headers):
        cell = chr(ord('A') + i) + str(row)
        lc.set(cell, header)
        lc.setAlignment(cell, 'center', 'keep')
        lc.setStyle(cell, 'bold', 'add')
        lc.setBackground(cell, HEADER_BACKGROUND)
    row += 1
    
    # Tanks einfügen
    doc = App.activeDocument()
    tank_count = 0
    
    if hasattr(ship, 'Tanks') and ship.Tanks:
        for tank_ref in ship.Tanks:
            try:
                tank = doc.getObject(tank_ref)
                if tank and hasattr(tank, 'Proxy'):
                    # Bestimme Hafen je nach Fluid-Typ
                    is_fuel = False
                    if hasattr(tank, 'FluidType'):
                        is_fuel = tank.FluidType in ["Fuel Oil", "Diesel"]
                    
                    load_port = "BUNKER" if is_fuel else "INT"
                    discharge_port = "BUNKER" if is_fuel else "INT"
                    
                    _addTankRow(lc, row, tank, load_port, discharge_port)
                    row += 1
                    tank_count += 1
            except Exception as e:
                print("Error processing tank " + str(tank_ref) + ": " + str(e))
                continue
    
    print("Added " + str(tank_count) + " tanks to spreadsheet")
    
    return row  # WICHTIG: Rückgabe der aktuellen Zeile!


def _addTankRow(lc, row, tank, load_port, discharge_port):
    """Füge einzelne Tank-Zeile hinzu"""
    tank_name = tank.Label if tank.Label else tank.Name
    
    # Name mit Hafencode
    display_name = f"[{load_port}→{discharge_port}] TANK: {tank_name}"
    lc.set(f'A{row}', display_name)
    
    # Dichte
    density = 1025  # Default Seewasser
    if hasattr(tank, 'FluidType'):
        densities = {
            "Fresh Water": 1000,
            "Sea Water": 1025,
            "Fuel Oil": 850,
            "Diesel": 830,
            "LNG": 450,
            "LPG": 510
        }
        density = densities.get(tank.FluidType, 1025)
    elif hasattr(tank, 'Density'):
        try:
            density = tank.Density.getValueAs("kg/m^3")
        except:
            pass
    
    lc.set(f'B{row}', str(density))
    
    # Fill % (aus Tank-Objekt wenn vorhanden)
    fill = 0.0
    if hasattr(tank, 'FillPercentage'):
        fill = tank.FillPercentage
    lc.set(f'C{row}', f"{fill:.1f}")
    
    # Farbe
    bg_color = PORT_BG_COLORS.get(load_port, TANK_ROW_COLOR)
    for col in ['A','B','C','D','E','F','G','H','I','J','K']:
        lc.setBackground(f'{col}{row}', bg_color)


# =============================================================================
# TEIL 3: CARGO-SEKTION MIT 3D-BOX-INTEGRATION
# =============================================================================

def _createCargoSection(lc, start_row, ship):
    """Erstelle Cargo-Sektion mit 3D-Visualisierung"""
    row = start_row  # WICHTIG: row initialisieren!
    
    # Sektionsheader
    lc.mergeCells('A' + str(row) + ':K' + str(row))
    lc.set('A' + str(row), "GENERAL CARGO (3D Visualization Enabled)")
    lc.setAlignment('A' + str(row), 'center', 'keep')
    lc.setStyle('A' + str(row), 'bold', 'add')
    lc.setStyle('A' + str(row), 'underline', 'add')
    lc.setBackground('A' + str(row), CARGO_ROW_COLOR)
    row += 1
    
    # Anleitung
    lc.mergeCells('A' + str(row) + ':K' + str(row))
    lc.set('A' + str(row), "Format: [LOADPORT→DISCHPORT] Name | Fill Mass, LCG, TCG, VCG")
    lc.setStyle('A' + str(row), 'italic', 'add')
    lc.setForeground('A' + str(row), (0.4, 0.4, 0.4))
    row += 1
    
    # Spaltenheader
    headers = ["[Load→Disch] Cargo Name", "Type", "Dim (L×W×H)", "Mass (kg)", 
               "LCG (m)", "TCG (m)", "VCG (m)", 
               "Mom X", "Mom Y", "Mom Z", "Notes"]
    
    for i, header in enumerate(headers):
        cell = chr(ord('A') + i) + str(row)
        lc.set(cell, header)
        lc.setAlignment(cell, 'center', 'keep')
        lc.setStyle(cell, 'bold', 'add')
        lc.setBackground(cell, HEADER_BACKGROUND)
    row += 1
    
    # Beispieleinträge
    examples = [
        ("[DEHAM→SGSIN] Container 20ft", "Cont20", "6.06×2.44×2.59", 24000, 60.0, 0.0, 15.0, "High cube"),
        ("[DEHAM→SGSIN] Container 40ft", "Cont40", "12.19×2.44×2.89", 28000, 55.0, 2.0, 15.0, ""),
        ("[NLRTM→CNHKG] Heavy Lift", "Project", "8.0×4.0×3.0", 85000, 40.0, -1.5, 18.0, "OOG"),
    ]
    
    for name, ctype, dims, mass, lcg, tcg, vcg, notes in examples:
        _addCargoRow(lc, row, name, ctype, dims, mass, lcg, tcg, vcg, notes)
        row += 1
    
    # Leere Zeilen für manuelle Eingabe
    for i in range(5):
        _addEmptyCargoRow(lc, row)
        row += 1
    
    # Button/Info für 3D-Update
    row += 1
    lc.mergeCells('A' + str(row) + ':K' + str(row))
    lc.set('A' + str(row), ">>> Run 'Update Cargo 3D' to visualize <<<")
    lc.setAlignment('A' + str(row), 'center', 'keep')
    lc.setStyle('A' + str(row), 'bold', 'add')
    lc.setBackground('A' + str(row), (1.0, 0.9, 0.7))
    
    return row  # WICHTIG: Rückgabe der aktuellen Zeile!

def _createTotalsSection(lc, start_row):
    """Erstelle Totals-Sektion (Summary)"""
    row = start_row
    
    # Leerzeile
    row += 1
    
    # Totals Header
    lc.mergeCells('A' + str(row) + ':K' + str(row))
    lc.set('A' + str(row), "SUMMARY / TOTALS")
    lc.setAlignment('A' + str(row), 'center', 'keep')
    lc.setStyle('A' + str(row), 'bold', 'add')
    lc.setStyle('A' + str(row), 'underline', 'add')
    lc.setBackground('A' + str(row), TOTAL_BACKGROUND)
    row += 1
    
    # Total Mass Zeile
    lc.set('A' + str(row), "Total Mass:")
    lc.setAlignment('A' + str(row), 'right', 'keep')
    lc.setStyle('A' + str(row), 'bold', 'add')
    lc.set('D' + str(row), "0.00")  # Wird berechnet
    lc.set('E' + str(row), "kg")
    row += 1
    
    # Total Moment Zeilen
    lc.set('A' + str(row), "Total Moments:")
    lc.setStyle('A' + str(row), 'bold', 'add')
    row += 1
    
    lc.set('B' + str(row), "X:")
    lc.set('C' + str(row), "0.00")
    lc.set('D' + str(row), "Y:")
    lc.set('E' + str(row), "0.00")
    lc.set('F' + str(row), "Z:")
    lc.set('G' + str(row), "0.00")
    row += 1
    
    # COG Zeile
    lc.set('A' + str(row), "Center of Gravity (COG):")
    lc.setStyle('A' + str(row), 'bold', 'add')
    row += 1
    
    lc.set('B' + str(row), "LCG:")
    lc.set('C' + str(row), "0.000")
    lc.set('D' + str(row), "m")
    lc.set('E' + str(row), "TCG:")
    lc.set('F' + str(row), "0.000")
    lc.set('G' + str(row), "m")
    lc.set('H' + str(row), "VCG:")
    lc.set('I' + str(row), "0.000")
    lc.set('J' + str(row), "m")
    row += 1
    
    # Hydrostatik Hinweis
    row += 1
    lc.mergeCells('A' + str(row) + ':K' + str(row))
    lc.set('A' + str(row), "(Run 'Recalculate' to update totals and hydrostatics)")
    lc.setAlignment('A' + str(row), 'center', 'keep')
    lc.setStyle('A' + str(row), 'italic', 'add')
    lc.setForeground('A' + str(row), (0.5, 0.5, 0.5))
    
    return row


def _addCargoRow(lc, row, name, ctype, dims, mass, lcg, tcg, vcg, notes=""):
    """Füge Cargo-Zeile hinzu"""
    lc.set(f'A{row}', name)
    lc.set(f'B{row}', ctype)
    lc.set(f'C{row}', dims)
    lc.set(f'D{row}', str(mass))
    lc.set(f'E{row}', f"{lcg:.2f}")
    lc.set(f'F{row}', f"{tcg:.2f}")
    lc.set(f'G{row}', f"{vcg:.2f}")
    
    # Momente (werden berechnet)
    lc.set(f'H{row}', f"=D{row}*E{row}")
    lc.set(f'I{row}', f"=D{row}*F{row}")
    lc.set(f'J{row}', f"=D{row}*G{row}")
    lc.set(f'K{row}', notes)
    
    # Parse Hafen für Farbe
    match = re.match(r'\[([A-Z]+)→([A-Z]+)\]', name)
    if match:
        load_port = match.group(1)
        bg_color = PORT_BG_COLORS.get(load_port, CARGO_ROW_COLOR)
    else:
        bg_color = CARGO_ROW_COLOR
    
    for col in ['A','B','C','D','E','F','G','H','I','J','K']:
        lc.setBackground(f'{col}{row}', bg_color)


def _addEmptyCargoRow(lc, row):
    """Leere Zeile für manuelle Eingabe"""
    for col in ['A','B','C','D','E','F','G','H','I','J','K']:
        lc.setBackground(f'{col}{row}', CARGO_ROW_COLOR)


# =============================================================================
# TEIL 4: 3D-CARGO-BOX KLASSE (BIDIREKTIONAL)
# =============================================================================

class CargoBox3D:
    """Bidirektionale 3D-Cargo-Box mit Spreadsheet-Verknüpfung"""
    
    def __init__(self, doc, name, mass, position, dimensions, 
                 load_port, discharge_port, cargo_type, notes,
                 spreadsheet, row):
        """
        Erstelle 3D-Cargo-Box mit Verknüpfung zum Spreadsheet
        
        Arguments:
            doc -- FreeCAD Document
            name -- Cargo-Name
            mass -- Masse in kg
            position -- (lcg, tcg, vcg) in Metern
            dimensions -- (length, width, height) in Metern
            load_port, discharge_port -- Hafencodes
            cargo_type -- Container-Typ o.ä.
            notes -- Notizen
            spreadsheet -- Spreadsheet-Objekt
            row -- Zeilennummer im Spreadsheet
        """
        self.doc = doc
        self.spreadsheet = spreadsheet
        self.row = row
        self.name = name
        self.mass = mass
        self.load_port = load_port
        self.discharge_port = discharge_port
        
        # Eindeutiger Name
        safe_name = re.sub(r'[^\w]', '_', name)[:30]
        self.obj_name = f"Cargo3D_{safe_name}_{row}"
        
        # Erstelle Part-Box (nicht nur Mesh, damit man sie verschieben kann)
        self.box = doc.addObject("Part::Box", self.obj_name)
        self.box.Length = dimensions[0] * 1000  # mm
        self.box.Width = dimensions[1] * 1000
        self.box.Height = dimensions[2] * 1000
        
        # Position (mm)
        self.box.Placement.Base = Vector(
            position[0] * 1000,
            position[1] * 1000, 
            position[2] * 1000
        )
        
        # Erstelle zugehöriges Gewicht-Objekt für Stabilität
        self.weight = self._createWeightObject()
        
        # Setze Farbe nach Ladehafen
        self._setColor()
        
        # Erstelle Label
        self.label = self._createLabel(dimensions)
        
        # Registriere Observer für Positionsänderungen
        self.box.Proxy = self
        
        # Speichere Verknüpfung global
        _cargo_links[self.obj_name] = self
        
        print(f"CargoBox3D created: {name} at {position}, linked to row {row}")
    
    def _createWeightObject(self):
        """Erstelle Gewicht-Objekt für Stabilitätsberechnung"""
        weight = self.doc.addObject("App::FeaturePython", f"Weight_{self.obj_name}")
        
        # Properties
        weight.addProperty("App::PropertyFloat", "Mass", "Cargo", "Mass in kg")
        weight.addProperty("App::PropertyVector", "COG", "Cargo", "Center of gravity")
        weight.addProperty("App::PropertyString", "CargoName", "Cargo", "Name")
        weight.addProperty("App::PropertyString", "LoadPort", "Cargo", "Port of loading")
        weight.addProperty("App::PropertyString", "DischargePort", "Cargo", "Port of discharge")
        weight.addProperty("App::PropertyInteger", "SpreadsheetRow", "Link", "Row in spreadsheet")
        weight.addProperty("App::PropertyString", "BoxObject", "Link", "Linked 3D box name")
        
        weight.Mass = self.mass
        weight.COG = Vector(
            self.box.Placement.Base.x / 1000,
            self.box.Placement.Base.y / 1000,
            self.box.Placement.Base.z / 1000
        )
        weight.CargoName = self.name
        weight.LoadPort = self.load_port
        weight.DischargePort = self.discharge_port
        weight.SpreadsheetRow = self.row
        weight.BoxObject = self.obj_name
        
        return weight
    
    def _setColor(self):
        """Setze Farbe nach Ladehafen"""
        color = PORT_COLORS.get(self.load_port, (0.8, 0.4, 0.0))
        
        # Für Part-Objekte über ViewObject
        if hasattr(self.box, 'ViewObject') and self.box.ViewObject:
            self.box.ViewObject.ShapeColor = color
            # Transparenz für bessere Sichtbarkeit
            self.box.ViewObject.Transparency = 30
    
    def _createLabel(self, dimensions):
        """Erstelle Text-Label über der Box"""
        try:
            import Draft
            
            label_text = f"{self.name}\n{self.mass/1000:.1f}t\n{self.load_port}→{self.discharge_port}"
            
            # Position über der Box
            label_pos = Vector(
                self.box.Placement.Base.x,
                self.box.Placement.Base.y,
                self.box.Placement.Base.z + self.box.Height + 500  # 500mm über Box
            )
            
            label = Draft.makeText([label_text], label_pos)
            label.ViewObject.FontSize = 200  # mm
            label.ViewObject.TextColor = (0, 0, 0)
            label.Label = f"Label_{self.obj_name}"
            
            return label
            
        except Exception as e:
            print(f"Could not create label: {e}")
            return None
    
    def onChanged(self, fp, prop):
        """Wird aufgerufen wenn sich die Box verschiebt (Observer)"""
        if prop == "Placement":
            new_pos = fp.Placement.Base
            
            # Konvertiere zu Metern
            new_lcg = new_pos.x / 1000.0
            new_tcg = new_pos.y / 1000.0
            new_vcg = new_pos.z / 1000.0
            
            # Update Weight-Objekt
            self.weight.COG = Vector(new_lcg, new_tcg, new_vcg)
            
            # Update Spreadsheet (wenn nicht gerade dabei es zu laden)
            if self.spreadsheet and self.row:
                try:
                    # Prüfe ob Werte sich wirklich geändert haben (Endlosschleife vermeiden)
                    current_lcg = float(self.spreadsheet.get(f'E{self.row}') or 0)
                    if abs(current_lcg - new_lcg) > 0.001:
                        self.spreadsheet.set(f'E{self.row}', f"{new_lcg:.3f}")
                        self.spreadsheet.set(f'F{self.row}', f"{new_tcg:.3f}")
                        self.spreadsheet.set(f'G{self.row}', f"{new_vcg:.3f}")
                        
                        # Trigger Recalc
                        App.activeDocument().recompute()
                        
                        print(f"Updated spreadsheet row {self.row}: LCG={new_lcg:.2f}, TCG={new_tcg:.2f}, VCG={new_vcg:.2f}")
                        
                except Exception as e:
                    print(f"Error updating spreadsheet: {e}")
            
            # Update Label-Position
            if self.label:
                try:
                    self.label.Placement.Base = Vector(
                        new_pos.x,
                        new_pos.y,
                        new_pos.z + self.box.Height + 500
                    )
                except:
                    pass
    
    def updateFromSpreadsheet(self, position=None):
        """Update Box-Position von Spreadsheet (umgekehrte Richtung)"""
        if position:
            self.box.Placement.Base = Vector(
                position[0] * 1000,
                position[1] * 1000,
                position[2] * 1000
            )
            self.weight.COG = Vector(position[0], position[1], position[2])
    
    def delete(self):
        """Lösche Box und alle zugehörigen Objekte"""
        doc = self.doc
        
        if self.label:
            try:
                doc.removeObject(self.label.Name)
            except:
                pass
        
        try:
            doc.removeObject(self.weight.Name)
        except:
            pass
        
        try:
            doc.removeObject(self.box.Name)
        except:
            pass
        
        if self.obj_name in _cargo_links:
            del _cargo_links[self.obj_name]


# =============================================================================
# TEIL 5: 3D-VISUALISIERUNGS-FUNKTIONEN
# =============================================================================

def updateCargo3DVisualization(spreadsheet=None):
    """
    Aktualisiere 3D-Visualisierung aller Cargo-Einträge
    
    Wenn spreadsheet=None, wird das aktive Spreadsheet verwendet
    """
    doc = App.activeDocument()
    
    # Cleanup existing
    _cleanupCargoVisualization()
    
    # Finde LoadCondition-Spreadsheet
    if spreadsheet is None:
        for obj in doc.Objects:
            if obj.TypeId == 'Spreadsheet::Sheet' and 'LoadCondition' in obj.Name:
                spreadsheet = obj
                break
    
    if not spreadsheet:
        print("No LoadCondition spreadsheet found")
        return
    
    # Parse alle Zeilen
    cargo_count = 0
    for row in range(10, 200):  # Suche in erweitertem Bereich
        try:
            cell_a = spreadsheet.get(f'A{row}')
            if not cell_a:
                continue
            
            # Prüfe ob Cargo-Eintrag (nicht Tank, nicht Header)
            if 'TANK:' in cell_a or 'Name' in cell_a or 'CARGO' in cell_a.upper():
                continue
            
            # Parse Hafencode und Name
            match = re.match(r'\[([A-Z]+)→([A-Z]+)\]\s*(.+)', cell_a)
            if not match:
                continue
            
            load_port, discharge_port, name = match.groups()
            
            # Lese Daten aus Spreadsheet
            try:
                cargo_type = spreadsheet.get(f'B{row}') or "General"
                dims_str = spreadsheet.get(f'C{row}') or "1×1×1"
                mass = float(spreadsheet.get(f'D{row}') or 0)
                lcg = float(spreadsheet.get(f'E{row}') or 0)
                tcg = float(spreadsheet.get(f'F{row}') or 0)
                vcg = float(spreadsheet.get(f'G{row}') or 0)
                notes = spreadsheet.get(f'K{row}') or ""
                
                # Parse Dimensionen (Format: "12.19×2.44×2.89")
                dims = _parseDimensions(dims_str)
                
                # Erstelle 3D-Box
                box = CargoBox3D(
                    doc, name, mass, (lcg, tcg, vcg), dims,
                    load_port, discharge_port, cargo_type, notes,
                    spreadsheet, row
                )
                
                cargo_count += 1
                
            except Exception as e:
                print(f"Error parsing cargo row {row}: {e}")
                continue
                
        except Exception as e:
            continue
    
    doc.recompute()
    print(f"Created {cargo_count} cargo boxes")
    return cargo_count


def _parseDimensions(dims_str):
    """Parse Dimensions-String (Format: '12.19×2.44×2.89' oder '12.19x2.44x2.89')"""
    try:
        # Ersetze verschiedene Multiplikationszeichen
        clean = dims_str.replace('×', 'x').replace('*', 'x').replace('X', 'x')
        parts = clean.split('x')
        if len(parts) == 3:
            return (float(parts[0]), float(parts[1]), float(parts[2]))
    except:
        pass
    
    # Default
    return (2.0, 2.0, 2.0)


def _cleanupCargoVisualization():
    """Lösche alle bestehenden Cargo-3D-Objekte"""
    doc = App.activeDocument()
    to_delete = []
    
    for obj in doc.Objects:
        if (obj.Name.startswith('Cargo3D_') or 
            obj.Name.startswith('Weight_Cargo3D_') or
            obj.Name.startswith('Label_Cargo3D_')):
            to_delete.append(obj.Name)
    
    for name in to_delete:
        try:
            doc.removeObject(name)
        except:
            pass
    
    # Clear global links
    _cargo_links.clear()
    
    if to_delete:
        print(f"Cleaned up {len(to_delete)} cargo objects")


def _setupDocumentCleanup(spreadsheet):
    """Setup cleanup handler when document closes"""
    # In FreeCAD können wir das Proxy-Objekt nutzen
    # oder einen Observer registrieren
    pass


# =============================================================================
# TEIL 6: BERECHNUNGSFUNKTIONEN
# =============================================================================

def recalculateLoadCondition(lc, ship):
    """Aktualisiere alle Berechnungen im Load Case"""
    
    # 1. Tanks updaten
    _updateTanks(lc, ship)
    
    # 2. Cargo-Summen (Formeln im Spreadsheet berechnen das automatisch)
    
    # 3. Lese Totale aus Spreadsheet
    totals = _calculateTotals(lc)
    
    # 4. Update fixe Ergebnisfelder
    _updateFixedResults(lc, totals)
    
    # 5. Hydrostatik (wenn verfügbar)
    _updateHydrostatics(lc, ship, totals)
    
    App.activeDocument().recompute()


def _updateTanks(lc, ship):
    """Update Tank-Berechnungen (verwendet shipTank.Tools)"""
    try:
        from ..shipTank import Tools as TankTools
    except ImportError:
        print("Warning: shipTank.Tools not available")
        return
    
    doc = App.activeDocument()
    
    for row in range(10, 100):
        try:
            cell_a = lc.get(f'A{row}')
            if not cell_a or 'TANK:' not in cell_a:
                continue
            
            # Parse Tank-Name (entferne Hafencode)
            tank_name = cell_a.split('TANK:')[-1].strip()
            if ']' in tank_name:
                tank_name = tank_name.split(']')[-1].strip()
            
            # Lese Fill %
            try:
                fill_percent = float(lc.get(f'C{row}') or 0)
            except:
                fill_percent = 0
            
            # Finde Tank
            tank = None
            if hasattr(ship, 'Tanks'):
                for ref in ship.Tanks:
                    t = doc.getObject(ref)
                    if t and (t.Name == tank_name or t.Label == tank_name):
                        tank = t
                        break
            
            if not tank or not hasattr(tank, 'Proxy'):
                continue
            
            # Berechne mit offizieller API
            fill_height, fluid_volume = TankTools.compute_capacity(tank, fill_percent/100.0)
            
            # Konvertiere Volumen
            if isinstance(fluid_volume, Units.Quantity):
                vol_m3 = fluid_volume.getValueAs('m^3')
            elif hasattr(fluid_volume, 'Volume'):
                vol_m3 = fluid_volume.Volume / 1e9
            else:
                vol_m3 = float(fluid_volume)
            
            # Dichte und Masse
            density = 1025
            if hasattr(tank, 'FluidType'):
                densities = {"Fresh Water": 1000, "Sea Water": 1025, 
                           "Fuel Oil": 850, "Diesel": 830}
                density = densities.get(tank.FluidType, 1025)
            
            mass = vol_m3 * density
            
            # COG
            cog = tank.Proxy.getCoG(tank, Units.Quantity(f"{vol_m3} m^3"),
                                   Units.parseQuantity("0 deg"),
                                   Units.parseQuantity("0 deg"))
            
            # Update Spreadsheet (nur wenn sich was geändert hat)
            old_mass = lc.get(f'D{row}')
            new_mass_str = f"{mass:.2f}"
            if old_mass != new_mass_str:
                lc.set(f'D{row}', new_mass_str)
                lc.set(f'E{row}', f"{cog.x/1000:.3f}")
                lc.set(f'F{row}', f"{cog.y/1000:.3f}")
                lc.set(f'G{row}', f"{cog.z/1000:.3f}")
                
        except Exception as e:
            continue


def _calculateTotals(lc):
    """Berechne Summen aus Spreadsheet"""
    totals = {
        'mass': 0.0,
        'mom_x': 0.0,
        'mom_y': 0.0,
        'mom_z': 0.0,
        'fs': 0.0
    }
    
    for row in range(10, 200):
        try:
            mass = float(lc.get(f'D{row}') or 0)
            if mass <= 0:
                continue
            
            # Lese oder berechne Momente
            mom_x_str = lc.get(f'H{row}')
            if mom_x_str and not mom_x_str.startswith('='):
                mom_x = float(mom_x_str)
                mom_y = float(lc.get(f'I{row}') or 0)
                mom_z = float(lc.get(f'J{row}') or 0)
            else:
                # Berechne aus Position
                lcg = float(lc.get(f'E{row}') or 0)
                tcg = float(lc.get(f'F{row}') or 0)
                vcg = float(lc.get(f'G{row}') or 0)
                mom_x = mass * lcg
                mom_y = mass * tcg
                mom_z = mass * vcg
            
            fs = float(lc.get(f'K{row}') or 0)
            
            totals['mass'] += mass
            totals['mom_x'] += mom_x
            totals['mom_y'] += mom_y
            totals['mom_z'] += mom_z
            totals['fs'] += fs
            
        except:
            continue
    
    return totals


def _updateFixedResults(lc, totals):
    """Update die fixen Ergebnisfelder (D4, E5, F5, G5, K4)"""
    
    if totals['mass'] > 0:
        cog_x = totals['mom_x'] / totals['mass']
        cog_y = totals['mom_y'] / totals['mass']
        cog_z = totals['mom_z'] / totals['mass']
        
        lc.set('D4', f"{totals['mass']:.2f}")
        lc.set('E5', f"{cog_x:.3f}")  # COG X
        lc.set('F5', f"{cog_y:.3f}")  # COG Y (war H6, jetzt F5)
        lc.set('G5', f"{cog_z:.3f}")  # COG Z (war I6, jetzt G5)
        lc.set('K4', f"{totals['fs']:.2f}")
    else:
        lc.set('D4', "0.00")
        lc.set('E5', "0.000")
        lc.set('F5', "0.000")
        lc.set('G5', "0.000")
        lc.set('K4', "0.00")


def _updateHydrostatics(lc, ship, totals):
    """Update Hydrostatik-Berechnung (vereinfacht)"""
    # Hier könnte Ihre bestehende calculateHydrostatics Funktion eingebunden werden
    pass


# =============================================================================
# TEIL 7: WEITERE HILFSFUNKTIONEN
# =============================================================================

def cog_from_spreadsheet(lc_spreadsheet):
    """Compute COG from fixed spreadsheet positions (für externe Tools)"""
    try:
        total_mass = float(lc_spreadsheet.get('D4') or 0)
        cog_x = float(lc_spreadsheet.get('E5') or 0)
        cog_y = float(lc_spreadsheet.get('F5') or 0)
        cog_z = float(lc_spreadsheet.get('G5') or 0)
        
        if total_mass > 0:
            total_weight = total_mass * 9.81
            return Vector(cog_x, cog_y, cog_z), Units.Quantity(f"{total_weight} N")
        
    except Exception as e:
        print(f"Error getting COG: {e}")
    
    return Vector(0, 0, 0), Units.Quantity("0 N")


def syncSpreadsheetTo3D(lc, ship=None):
    """Synchronisiere Spreadsheet-Daten mit 3D-Visualisierung (manueller Aufruf)"""
    return updateCargo3DVisualization(lc)


def addCargoToExistingLoadCondition(lc, name, mass, lcg, tcg, vcg, 
                                    load_port="LOAD", discharge_port="DISCH",
                                    cargo_type="General", dimensions="2×2×2",
                                    notes=""):
    """Füge neues Cargo zu bestehendem Load Condition hinzu"""
    
    # Finde nächste freie Zeile in Cargo-Bereich
    row = 20  # Start nach Beispielen
    while lc.get(f'A{row}') and row < 200:
        row += 1
    
    # Format: [LOAD→DISCH] Name
    display_name = f"[{load_port}→{discharge_port}] {name}"
    
    _addCargoRow(lc, row, display_name, cargo_type, dimensions, mass, 
                lcg, tcg, vcg, notes)
    
    # Optional: Direkt 3D-Box erstellen
    doc = App.activeDocument()
    dims = _parseDimensions(dimensions)
    
    box = CargoBox3D(
        doc, name, mass, (lcg, tcg, vcg), dims,
        load_port, discharge_port, cargo_type, notes,
        lc, row
    )
    
    doc.recompute()
    return row


# Exportiere alle wichtigen Funktionen
__all__ = [
    'createLoadCondition',
    'recalculateLoadCondition',
    'updateCargo3DVisualization',
    'syncSpreadsheetTo3D',
    'addCargoToExistingLoadCondition',
    'cog_from_spreadsheet',
    'CargoBox3D',
]
