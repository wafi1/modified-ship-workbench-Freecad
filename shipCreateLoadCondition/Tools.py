#***************************************************************************
#*  LoadCondition Tools - AUTO-DELETE v16                                 *
#*  LÖSCHT IMMER alte, erstellt NEU mit ALLEN Sektionen!                 *
#***************************************************************************

import FreeCAD as App
from FreeCAD import Units, Vector
from datetime import datetime
import re

HEADER_BG = (0.8, 0.8, 1.0)
TANK_BG   = (0.95, 0.95, 1.0)
CARGO_BG  = (0.95, 1.0, 0.95)
WEIGHT_BG = (0.95, 0.95, 0.95)
TOTAL_BG  = (0.9,  1.0,  0.9)

def _get_obj(doc, ref):
    if ref is None:
        return None
    if hasattr(ref, 'Name'):
        return ref
    if isinstance(ref, str):
        return doc.getObject(ref)
    return None

def _get_obj_name(ref):
    if isinstance(ref, str):
        return ref
    if hasattr(ref, 'Name'):
        return ref.Name
    return str(ref)

def _get_object_type(obj):
    """Bestimme Objekttyp."""
    if not obj:
        return "unknown"
    
    # Prüfe zuerst auf Tank
    if hasattr(obj, 'Proxy') and hasattr(obj.Proxy, 'getVolume'):
        return "tank"
    
    # Dann auf Mass-Eigenschaft
    if hasattr(obj, 'Mass'):
        label = getattr(obj, 'Label', '').upper()
        name = getattr(obj, 'Name', '').upper()
        
        # Cargo Patterns
        if any(pattern in label for pattern in ['BD00', 'GT', 'SEF']):
            return "cargo"
        if name.startswith('CARGO') or 'CARGO' in label:
            return "cargo"
        
        return "weight"
    
    return "unknown"

def createLoadCondition(ship, delete_existing=True):  # DEFAULT TRUE!
    """Erstellt LoadCondition - LÖSCHT IMMER alte!"""
    doc = App.activeDocument()
    if not doc:
        print("❌ Error: No active document")
        return None

    print(f"\n{'='*60}")
    print(f"🔄 LOAD CONDITION - AUTO DELETE & CREATE")
    print(f"Ship: {ship.Label}")
    print(f"{'='*60}")

    # ── PHASE 1: IMMER LÖSCHEN ──────────────────────────────────────
    print(f"\n🔍 Phase 1: Deleting ALL existing LoadConditions...")
    
    deleted_count = 0
    # Über Dokument suchen
    for obj in doc.Objects:
        if obj.TypeId == 'Spreadsheet::Sheet' and ('LoadCondition' in obj.Label or 'LoadCondition' in obj.Name):
            print(f"🗑️ Deleting: {obj.Name} ('{obj.Label}')")
            try:
                doc.removeObject(obj.Name)
                deleted_count += 1
            except:
                print(f"     ⚠ Could not delete {obj.Name}")
    
    # Property zurücksetzen
    if hasattr(ship, 'LoadConditions'):
        ship.LoadConditions = []
    
    print(f"✅ Deleted {deleted_count} LoadCondition(s)")

    # ── PHASE 2: NEUES ERSTELLEN ────────────────────────────────────
    print(f"\n🔧 Phase 2: Creating new LoadCondition with ALL sections...")
    
    lc = doc.addObject('Spreadsheet::Sheet', 'LoadCondition')
    lc.Label = "LoadCondition"
    
    print(f"✅ Created: {lc.Name}")

    # Spaltenbreiten
    for col, w in [('A',200),('B',100),('C',80),('D',120),('E',90),
                   ('F',90),('G',90),('H',110),('I',110),('J',110),('K',140)]:
        lc.setColumnWidth(col, w)

    # Header
    lc.set("A1", "SHIP LOAD CONDITION")
    lc.mergeCells('A1:K1')
    lc.setAlignment('A1', 'center', 'keep')
    lc.setStyle('A1', 'bold', 'add')
    lc.setBackground('A1', HEADER_BG)

    lc.set("A2", "Ship:");  
    lc.set("B2", getattr(ship, 'Label', ship.Name))
    lc.set("A3", "Date:");  
    lc.set("B3", datetime.now().strftime("%Y-%m-%d %H:%M"))

    lc.set("D3", "Total mass [kg]");       lc.setBackground('D3', TOTAL_BG)
    lc.set("E3", "Draft [m]");       lc.setBackground('E3', TOTAL_BG)
    lc.set("F3", "KM [m]");       lc.setBackground('F3', TOTAL_BG)
    lc.set("G3", "GM` [m]");       lc.setBackground('G3', TOTAL_BG)

    # Result rows
    lc.set("A4", "Total mass [kg]");       lc.setBackground('A4', TOTAL_BG)
    lc.set("D4", "0.00")
    lc.set("F4", "Free Surface [t·m]");    lc.setBackground('F4', TOTAL_BG)
    lc.set("H4", "0.00")
    lc.set("E6", "COG X [m]");             lc.setBackground('E6', TOTAL_BG)
    lc.set("E5", "0.000")
    lc.set("F6", "COG Y [m]");             lc.setBackground('F6', TOTAL_BG)
    lc.set("F5", "0.000")
    lc.set("G6", "COG Z [m]");             lc.setBackground('G6', TOTAL_BG)
    lc.set("G5", "0.000")
    lc.set("I3", "Sum Mom X [kg·m]");      lc.setBackground('I3', TOTAL_BG)
    lc.set("I6", "0.00")
    lc.set("J3", "Sum Mom Y [kg·m]");      lc.setBackground('J3', TOTAL_BG)
    lc.set("J6", "0.00")
    lc.set("K3", "Sum Mom Z [kg·m]");      lc.setBackground('K3', TOTAL_BG)
    lc.set("K6", "0.00")
    lc.set("H3", "Sum FSM [t·m]");         lc.setBackground('H3', TOTAL_BG)
    lc.set("H6", "0.00")

    # ── TANKS section ───────────────────────────────────────────────
    print(f"\n⛽ Adding TANKS section...")
    
    row = 12
    lc.mergeCells(f'A{row}:K{row}')
    lc.set(f'A{row}', "TANKS")
    lc.setAlignment(f'A{row}', 'center', 'keep')
    lc.setStyle(f'A{row}', 'bold', 'add')
    lc.setBackground(f'A{row}', TANK_BG)
    row += 1

    # TANK HEADER
    for i, h in enumerate(["Name","Density","Fill%","Mass[kg]","LCG[m]",
                           "TCG[m]","VCG[m]","MomX","MomY","MomZ","FSM[t·m]"]):
        cell = chr(ord('A') + i) + str(row)
        lc.set(cell, h)
        lc.setStyle(cell, 'bold', 'add')
        lc.setBackground(cell, HEADER_BG)
    row += 1

    # TANK DATA ROWS
    tank_count = 0
    if hasattr(ship, 'Tanks') and ship.Tanks:
        print(f"Found {len(ship.Tanks)} tanks in ship.Tanks")
        
        for ref in ship.Tanks:
            tank = _get_obj(doc, ref)
            if not tank or not hasattr(tank, 'Shape'):
                continue
            
            # Check if it's a valid tank object
            is_valid_tank = hasattr(tank, 'Proxy') and hasattr(tank.Proxy, 'getVolume')
            
            if not is_valid_tank:
                print(f"  ⚠ {tank.Name} is not a valid tank (no getVolume method)")
                continue

            label = getattr(tank, 'Label', tank.Name)
            display = f"{label} [{tank.Name}]"
            lc.set(f'A{row}', display)

            # Density
            density = 1025
            if hasattr(tank, 'FluidType'):
                density = {"Fresh Water":1000,"Sea Water":1025,"Fuel Oil":850,
                          "Diesel":830,"Bunker":900,"Oil":900,"Water":1000
                          }.get(tank.FluidType, 1025)
            lc.set(f'B{row}', str(density))

            # Fill percentage
            fill = getattr(tank, 'FillPercentage', 50)
            lc.set(f'C{row}', str(fill))

            # Placeholder for calculated values
            for col in ['D','E','F','G','H','I','J','K']:
                lc.set(f'{col}{row}', "-")
            
            # Background for tank rows
            for col in ['A','B','C']:
                lc.setBackground(f'{col}{row}', TANK_BG)

            row += 1
            tank_count += 1
            print(f"  ✓ Added tank: {label}")
    else:
        print("ℹ️ No tanks found in ship.Tanks")

    # ── WEIGHTS section ─────────────────────────────────────────────
    print(f"\n⚖️ Adding WEIGHTS section...")
    
    row += 1  # Leerzeile vor Weights
    lc.mergeCells(f'A{row}:K{row}')
    lc.set(f'A{row}', "WEIGHTS")
    lc.setAlignment(f'A{row}', 'center', 'keep')
    lc.setStyle(f'A{row}', 'bold', 'add')
    lc.setBackground(f'A{row}', WEIGHT_BG)
    row += 1

    # WEIGHT HEADER
    for i, h in enumerate(["Name","Type","-","Mass[kg]","LCG[m]",
                           "TCG[m]","VCG[m]","MomX","MomY","MomZ","Note"]):
        cell = chr(ord('A') + i) + str(row)
        lc.set(cell, h)
        lc.setStyle(cell, 'bold', 'add')
        lc.setBackground(cell, HEADER_BG)
    row += 1

    # ALLE GEWICHTE aus ship.Weights
    weight_count = 0
    cargo_objects = []
    
    if hasattr(ship, 'Weights') and ship.Weights:
        print(f"Processing {len(ship.Weights)} objects from ship.Weights:")
        
        for ref in ship.Weights:
            obj = _get_obj(doc, ref)
            if not obj:
                print(f"  ⚠ Could not resolve: {ref}")
                continue
            
            obj_type = _get_object_type(obj)
            label = getattr(obj, 'Label', obj.Name)
            
            if obj_type == "cargo":
                cargo_objects.append(obj)
                print(f"  📦 Identified as CARGO: {label}")
                continue  # Später in CARGO section
            
            print(f"  ⚖️ Adding as WEIGHT: {label}")
            
            lc.set(f'A{row}', label)
            lc.set(f'B{row}', "Weight")
            lc.set(f'C{row}', "-")
            
            # Mass
            if hasattr(obj, 'Mass'):
                mass = float(obj.Mass)
                lc.set(f'D{row}', str(mass))
                print(f"     Mass: {mass:,.0f} kg")
            else:
                lc.set(f'D{row}', "0")
                print(f"     ⚠ No Mass property")
            
            # COG
            if hasattr(obj, 'COG'):
                lc.set(f'E{row}', str(float(obj.COG.x) / 1000))
                lc.set(f'F{row}', str(float(obj.COG.y) / 1000))
                lc.set(f'G{row}', str(float(obj.COG.z) / 1000))
            elif hasattr(obj, 'Shape') and obj.Shape:
                bb = obj.Shape.BoundBox
                lc.set(f'E{row}', str(bb.Center.x / 1000))
                lc.set(f'F{row}', str(bb.Center.y / 1000))
                lc.set(f'G{row}', str(bb.Center.z / 1000))
            else:
                lc.set(f'E{row}', "0.000"); lc.set(f'F{row}', "0.000"); lc.set(f'G{row}', "0.000")
            
            # Placeholder moments
            lc.set(f'H{row}', "0.00")
            lc.set(f'I{row}', "0.00")
            lc.set(f'J{row}', "0.00")
            lc.set(f'K{row}', "-")
            
            # Background
            for col in ['A','B','C','D','E','F','G']:
                lc.setBackground(f'{col}{row}', WEIGHT_BG)
            
            row += 1
            weight_count += 1
    else:
        print("ℹ️ No weights found in ship.Weights")

    # ── CRANES section ─────────────────────────────────────────────
    cranes = [o for o in doc.Objects
              if getattr(getattr(o, "Proxy", None), "Type", "") == "ShipCrane"]
    
    if cranes:
        print(f"\n🏗️ Adding CRANES section ({len(cranes)} cranes)...")
        
        row += 1  # Leerzeile
        lc.mergeCells(f'A{row}:K{row}')
        lc.set(f'A{row}', "CRANES")
        lc.setAlignment(f'A{row}', 'center', 'keep')
        lc.setStyle(f'A{row}', 'bold', 'add')
        lc.setBackground(f'A{row}', (0.95, 0.90, 0.80))
        row += 1

        # CRANE HEADER
        for i, h in enumerate(["Name", "Component", "-", "Mass[kg]", "LCG[m]",
                               "TCG[m]", "VCG[m]", "MomX", "MomY", "MomZ", "Note"]):
            cell = chr(ord('A') + i) + str(row)
            lc.set(cell, h)
            lc.setStyle(cell, 'bold', 'add')
            lc.setBackground(cell, HEADER_BG)
        row += 1

        crane_bg = (0.95, 0.90, 0.80)
        crane_count = 0

        for crane in cranes:
            label = getattr(crane, 'Label', crane.Name)
            pos   = crane.Placement.Base
            lcg_m = pos.x / 1000.0
            tcg_m = pos.y / 1000.0

            # Schwerpunkt Boom-Z: BoomCGPosition falls vorhanden
            if hasattr(crane, 'BoomCGPosition'):
                vcg_boom_m = float(crane.BoomCGPosition.z) / 1000.0
            else:
                vcg_boom_m = (pos.z + float(getattr(crane, 'BoomPivotHeight', 0))) / 1000.0

            # Kranfuss-VCG: Mitte Turm
            base_h  = float(getattr(crane, 'BaseHeight',  0))
            tower_h = float(getattr(crane, 'TowerHeight', 0))
            vcg_base_m = (pos.z + (base_h + tower_h) / 2.0) / 1000.0

            # ── Zeile 1: Kranbaum ──────────────────────────────────
            boom_kg = float(getattr(crane, 'BoomWeight', 0.0)) * 1000.0
            lc.set(f'A{row}', label)
            lc.set(f'B{row}', "Kranbaum")
            lc.set(f'C{row}', "-")
            lc.set(f'D{row}', str(boom_kg))
            lc.set(f'E{row}', f"{lcg_m:.3f}")
            lc.set(f'F{row}', f"{tcg_m:.3f}")
            lc.set(f'G{row}', f"{vcg_boom_m:.3f}")
            lc.set(f'H{row}', "0.00")
            lc.set(f'I{row}', "0.00")
            lc.set(f'J{row}', "0.00")
            lc.set(f'K{row}', "Boom")
            for col in ['A','B','C','D','E','F','G']:
                lc.setBackground(f'{col}{row}', crane_bg)
            row += 1

            # ── Zeile 2: Last am Haken (Platzhalter = 0) ──────────
            lc.set(f'A{row}', label)
            lc.set(f'B{row}', "Last am Haken")
            lc.set(f'C{row}', "-")
            lc.set(f'D{row}', "0")      # wird manuell eingetragen
            lc.set(f'E{row}', f"{lcg_m:.3f}")
            lc.set(f'F{row}', f"{tcg_m:.3f}")
            lc.set(f'G{row}', f"{vcg_boom_m:.3f}")
            lc.set(f'H{row}', "0.00")
            lc.set(f'I{row}', "0.00")
            lc.set(f'J{row}', "0.00")
            lc.set(f'K{row}', "Hook load")
            for col in ['A','B','C','D','E','F','G']:
                lc.setBackground(f'{col}{row}', crane_bg)
            row += 1

            crane_count += 1
            print(f"  ✓ {label}: Boom={boom_kg:.0f}kg, Hook=0kg (Platzhalter)")

        print(f"  {crane_count} Kräne eingetragen")

    

    # ── CARGO section ───────────────────────────────────────────────
    if cargo_objects:
        print(f"\n📦 Adding CARGO section ({len(cargo_objects)} objects)...")
        
        row += 1  # Leerzeile vor Cargo
        lc.mergeCells(f'A{row}:K{row}')
        lc.set(f'A{row}', "CARGO")
        lc.setAlignment(f'A{row}', 'center', 'keep')
        lc.setStyle(f'A{row}', 'bold', 'add')
        lc.setBackground(f'A{row}', CARGO_BG)
        row += 1

        # CARGO HEADER
        for i, h in enumerate(["Name","Type","Dims","Mass[kg]","LCG[m]",
                               "TCG[m]","VCG[m]","MomX","MomY","MomZ","Ports"]):
            cell = chr(ord('A') + i) + str(row)
            lc.set(cell, h)
            lc.setStyle(cell, 'bold', 'add')
            lc.setBackground(cell, HEADER_BG)
        row += 1

        # CARGO OBJECTS
        cargo_count = 0
        for obj in cargo_objects:
            label = getattr(obj, 'Label', obj.Name)
            print(f"  Adding CARGO: {label}")
            
            lc.set(f'A{row}', label)
            lc.set(f'B{row}', "Cargo")
            lc.set(f'C{row}', "-")
            
            # Mass
            if hasattr(obj, 'Mass'):
                mass = float(obj.Mass)
                lc.set(f'D{row}', str(mass))
                print(f"     Mass: {mass:,.1f} kg")
            else:
                lc.set(f'D{row}', "0")
                print(f"     ⚠ No Mass property")
            
            # COG
            if hasattr(obj, 'COG'):
                lc.set(f'E{row}', str(float(obj.COG.x) / 1000))
                lc.set(f'F{row}', str(float(obj.COG.y) / 1000))
                lc.set(f'G{row}', str(float(obj.COG.z) / 1000))
            elif hasattr(obj, 'Shape') and obj.Shape:
                bb = obj.Shape.BoundBox
                lc.set(f'E{row}', str(bb.Center.x / 1000))
                lc.set(f'F{row}', str(bb.Center.y / 1000))
                lc.set(f'G{row}', str(bb.Center.z / 1000))
            else:
                lc.set(f'E{row}', "0.000"); lc.set(f'F{row}', "0.000"); lc.set(f'G{row}', "0.000")
            
            # Placeholder moments
            lc.set(f'H{row}', "0.00")
            lc.set(f'I{row}', "0.00")
            lc.set(f'J{row}', "0.00")
            lc.set(f'K{row}', "-")
            
            # Background
            for col in ['A','B','C','D','E','F','G']:
                lc.setBackground(f'{col}{row}', CARGO_BG)
            
            row += 1
            cargo_count += 1

    # ── Mit Ship verknüpfen ────────────────────────────────────────
    if not hasattr(ship, 'LoadConditions'):
        ship.addProperty("App::PropertyStringList", "LoadConditions", "Ship",
                        "List of load condition spreadsheets")
    
    ship.LoadConditions = [lc.Name]
    
    doc.recompute()

    print(f"\n{'='*60}")
    print(f"✅ LOAD CONDITION CREATED SUCCESSFULLY")
    print(f"{'='*60}")
    print(f"Spreadsheet: {lc.Name}")
    print(f"Tanks       : {tank_count} rows")
    print(f"Weights     : {weight_count} rows")
    if cargo_objects:
        print(f"Cargo       : {len(cargo_objects)} rows")
    print(f"{'='*60}")
    print(f"🚀 Next: Run 'Calculate Load Case' for calculations")
    print(f"{'='*60}")
    if cranes:
        print(f"Cranes      : {len(cranes) * 2} rows ({len(cranes)} Kräne × 2)")
    
    return lc

def delete_all_loadconditions(ship):
    """Delete all LoadCondition spreadsheets."""
    doc = App.activeDocument()
    if not doc:
        return 0
    
    deleted_count = 0
    for obj in doc.Objects:
        if obj.TypeId == 'Spreadsheet::Sheet' and ('LoadCondition' in obj.Label or 'LoadCondition' in obj.Name):
            doc.removeObject(obj.Name)
            deleted_count += 1
    
    if hasattr(ship, 'LoadConditions'):
        ship.LoadConditions = []
    
    print(f"🗑️ Deleted {deleted_count} LoadCondition(s)")
    return deleted_count

def show_loadcondition_status(ship):
    """Show LoadCondition status."""
    doc = App.activeDocument()
    if not doc:
        return
    
    print(f"\n{'='*70}")
    print(f"LoadCondition status for: {ship.Label}")
    print(f"{'='*70}")
    
    if hasattr(ship, 'LoadConditions'):
        print(f"ship.LoadConditions: {ship.LoadConditions}")
    else:
        print("ship.LoadConditions: property does not exist")
    
    # Alle LoadConditions im Dokument
    all_lc = [o for o in doc.Objects 
              if o.TypeId == 'Spreadsheet::Sheet' 
              and ('LoadCondition' in o.Label or 'LoadCondition' in o.Name)]
    
    print(f"\nFound in document: {len(all_lc)} LoadCondition(s)")
    for lc in all_lc:
        print(f"  - {lc.Name}: '{lc.Label}'")
    
    print(f"{'='*70}\n")

__all__ = ['createLoadCondition', 'delete_all_loadconditions', 'show_loadcondition_status']
