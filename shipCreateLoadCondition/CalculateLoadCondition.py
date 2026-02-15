# shipCreateLoadCondition/CalculateLoadCondition.py - ULTIMATE NO-DOUBLE-COUNTING
import FreeCAD as App
import FreeCADGui as Gui
import os
import re
from PySide import QtCore, QtGui

_resource_dir = os.path.join(os.path.dirname(__file__), "..", "resources")
_icon_path = os.path.join(_resource_dir, "icons", "ship_calc.svg")

# ============================================================================
# STATE TRACKING - Verhindert Doppelberechnung
# ============================================================================
_calculation_state = {
    'last_calculation_time': 0,
    'processed_rows': set(),
    'total_mass': 0.0
}

def reset_calculation_state():
    """Reset calculation state before each run."""
    _calculation_state['last_calculation_time'] = 0
    _calculation_state['processed_rows'] = set()
    _calculation_state['total_mass'] = 0.0

# ============================================================================
# SIMPLE HELPER FUNCTIONS
# ============================================================================
def get_cell(lc, cell, default=""):
    try:
        val = lc.get(cell)
        return str(val).strip() if val is not None else default
    except:
        return default

def to_float(text, default=0.0):
    if not text:
        return default
    try:
        # Remove non-numeric characters
        cleaned = re.sub(r'[^\d\.\-]', '', str(text))
        return float(cleaned) if cleaned else default
    except:
        return default

# ============================================================================
# NEU: HYDROSTATISCHE BERECHNUNG
# ============================================================================
def calculate_hydrostatics(ship_obj, total_mass, cog_z, total_fsm):
    """Berechnet hydrostatische Werte für das Schiff."""
    try:
        # Annahmen für vereinfachte Hydrostatik
        RHO = 1025.0  # kg/m³ - Seewasser
        G = 9.81      # m/s²
        
        # Schiffsabmessungen aus dem Ship-Objekt
        L = ship_obj.Length.getValueAs('m').Value if hasattr(ship_obj.Length, 'getValueAs') else float(ship_obj.Length)
        B = ship_obj.Beam.getValueAs('m').Value if hasattr(ship_obj.Beam, 'getValueAs') else float(ship_obj.Beam)
        
        # Verdrängtes Volumen
        displacement_vol = total_mass / RHO  # m³
        
        # Annäherung Tiefgang (vereinfacht: T = V / (L * B * Cb))
        # Angenommener Blockkoeffizient Cb = 0.7 für typische Frachtschiffe
        Cb = 0.7
        T = displacement_vol / (L * B * Cb)
        
        # Wasserlinienfläche (vereinfacht)
        Aw = L * B * 0.85  # 85% des Rechtecks
        
        # Metazentrische Höhen (vereinfacht)
        # KB (Schwerpunkt Verdrängung) ≈ T/2
        KB = T * 0.5
        
        # BM (Metazentrisches Radius) = I / V
        # I = L * B³ / 12 für Rechteckwasserlinie
        I = (L * B**3) / 12.0
        BM = I / displacement_vol
        
        # KM (Metazentrische Höhe über Basis)
        KM = KB + BM
        
        # GM (Metazentrische Höhe) = KM - KG
        # KG = cog_z (Schwerpunkt über Basis)
        GM = KM - cog_z
        
        # GM korrigiert um FSM (freie Flüssigkeitsoberflächen)
        # FSM ist in t·m² = 1000 kg·m², umrechnen in m Hebelarm
        if total_fsm > 0:
            fsm_correction = total_fsm * 1000 / total_mass  # m
            GM_corrected = GM - fsm_correction
        else:
            fsm_correction = 0.0
            GM_corrected = GM
        
        return {
            'draft': T,
            'KM': KM,
            'GM': GM,
            'GM_corrected': GM_corrected,
            'fsm_correction': fsm_correction,
            'displacement_vol': displacement_vol,
            'waterplane_area': Aw
        }
        
    except Exception as e:
        App.Console.PrintWarning(f"Hydrostatic calculation failed: {e}\n")
        return None

# ============================================================================
# TANK CALCULATION
# ============================================================================
def calculate_tank(tank_obj, fill_percent, density):
    """Calculate tank values - returns NEW values only."""
    try:
        if not hasattr(tank_obj, 'Shape'):
            return None
        
        fill_ratio = fill_percent / 100.0
        bb = tank_obj.Shape.BoundBox
        
        # ALWAYS calculate fresh - never read from spreadsheet
        volume_m3 = (bb.XLength * bb.YLength * bb.ZLength) / 1e9
        filled_volume = volume_m3 * fill_ratio
        mass_kg = filled_volume * density
        
        # COG
        cog_x = bb.Center.x
        cog_y = bb.Center.y
        cog_z = bb.ZMin + (bb.ZLength * fill_ratio / 2)
        
        # FSM
        fsm = 0.0
        if 0 < fill_percent < 100:
            length_m = bb.XLength / 1000.0
            width_m = bb.YLength / 1000.0
            i_m4 = (length_m * width_m ** 3) / 12.0
            density_t_m3 = density / 1000.0
            fsm = i_m4 * density_t_m3
        
        return mass_kg, cog_x/1000.0, cog_y/1000.0, cog_z/1000.0, fsm
    except:
        return None

def find_ship_instance(doc):
    """Find the ship instance in the document."""
    for obj in doc.Objects:
        # Look for ship instance (usually has TypeId starting with 'Ship')
        if hasattr(obj, 'TypeId') and 'Ship' in obj.TypeId:
            # Check if it has a LoadCondition spreadsheet inside
            if hasattr(obj, 'Group') and obj.Group:
                for child in obj.Group:
                    if hasattr(child, 'TypeId') and child.TypeId == 'Spreadsheet::Sheet':
                        if 'LoadCondition' in child.Label:
                            return obj, child
            # Also check directly for LoadCondition
            for child_obj in doc.Objects:
                if (hasattr(child_obj, 'TypeId') and 
                    child_obj.TypeId == 'Spreadsheet::Sheet' and 
                    'LoadCondition' in child_obj.Label):
                    # Check if it's in the ship's group
                    if hasattr(obj, 'Group') and child_obj in obj.Group:
                        return obj, child_obj
    return None, None

def find_loadcondition_spreadsheet(doc):
    """Find the LoadCondition spreadsheet - first in ship instance, then in root."""
    # First try to find ship instance with LoadCondition
    ship_obj, lc = find_ship_instance(doc)
    if lc:
        App.Console.PrintMessage(f"✓ Found LoadCondition in ship instance: {ship_obj.Label}\n")
        return lc
    
    # Fallback: look in document root
    App.Console.PrintWarning("⚠ LoadCondition not found in ship instance, searching in root...\n")
    for obj in doc.Objects:
        if obj.TypeId == 'Spreadsheet::Sheet' and 'LoadCondition' in obj.Label:
            App.Console.PrintMessage(f"✓ Found LoadCondition in document root: {obj.Label}\n")
            return obj
    
    return None

# ============================================================================
# MAIN CLASS - GUARANTEED NO DOUBLE COUNTING
# ============================================================================
class CalculateLoadCondition:
    def GetResources(self):
        return {
            'Pixmap': _icon_path,
            'MenuText': "Calculate Load Case",
            'ToolTip': "Calculate load condition (no double counting)",
            'CmdType': "ForEdit"
        }
    
    def Activated(self):
        self.recalculate_current()
    
    def recalculate_current(self):
        """Main function - ALWAYS starts fresh."""
        doc = App.activeDocument()
        if not doc:
            return
        
        # Find LoadCondition spreadsheet - CORRECTLY in ship instance
        lc = find_loadcondition_spreadsheet(doc)
        
        if not lc:
            App.Console.PrintError("❌ No LoadCondition spreadsheet found!\n")
            App.Console.PrintError("   Please check:\n")
            App.Console.PrintError("   1. That a Ship instance exists\n")
            App.Console.PrintError("   2. That the LoadCondition spreadsheet is inside the Ship instance\n")
            return
        
        # Find ship instance for hydrostatics
        ship_obj, _ = find_ship_instance(doc)
        if not ship_obj:
            App.Console.PrintWarning("⚠ No ship instance found - hydrostatics will be skipped\n")
        
        App.Console.PrintMessage(f"\n{'='*60}\n")
        App.Console.PrintMessage(f"🔄 CALCULATION START (Fresh)\n")
        App.Console.PrintMessage(f"{'='*60}\n")
        
        # ALWAYS reset state before calculation
        reset_calculation_state()
        
        try:
            result = self.calculate_all_items(lc, doc)
            
            # NEU: Hydrostatische Berechnung wenn Schiff vorhanden
            if result and ship_obj:
                App.Console.PrintMessage(f"\n{'='*60}\n")
                App.Console.PrintMessage(f"🌊 HYDROSTATIC CALCULATION\n")
                App.Console.PrintMessage(f"{'='*60}\n")
                
                hydro = calculate_hydrostatics(
                    ship_obj, 
                    result['mass'], 
                    result['cog'][2],  # cog_z
                    result['fsm']
                )
                
                if hydro:
                    # NEU: Schreibe hydrostatische Werte ins Spreadsheet
                    # E4: Tiefgang
                    lc.set('E4', f"{hydro['draft']:.3f}")
                    # F4: KM
                    lc.set('F4', f"{hydro['KM']:.3f}")
                    # G4: GM (korrigiert um FSM)
                    lc.set('G4', f"{hydro['GM_corrected']:.3f}")
                    # H5: HYDROSTATISCHER FSM HEBEL (aus FSM/mass)
                    lc.set('H5', f"{hydro['fsm_correction']:.6f}")
                    # D6: Tiefgang (duplikat für Kompatibilität)
                    lc.set('D6', f"{hydro['draft']:.3f}")
                    
                    App.Console.PrintMessage(f"📊 Hydrostatics written to spreadsheet:\n")
                    App.Console.PrintMessage(f"  E4 (Draft):      {hydro['draft']:.3f} m\n")
                    App.Console.PrintMessage(f"  F4 (KM):         {hydro['KM']:.3f} m\n")
                    App.Console.PrintMessage(f"  G4 (GM corr.):   {hydro['GM_corrected']:.3f} m\n")
                    App.Console.PrintMessage(f"  H5 (FSM lever):  {hydro['fsm_correction']:.6f} m\n")
                    App.Console.PrintMessage(f"  D6 (Draft dup.): {hydro['draft']:.3f} m\n")
                    
                    # Speichere auch im result dict
                    result['hydrostatics'] = hydro
            
            if result:
                App.Console.PrintMessage(f"\n✅ FINAL RESULTS:\n")
                App.Console.PrintMessage(f"Total Mass: {result['mass']:,.0f} kg\n")
                App.Console.PrintMessage(f"COG: ({result['cog'][0]:.2f}, {result['cog'][1]:.2f}, {result['cog'][2]:.2f}) m\n")
                if 'hydrostatics' in result:
                    h = result['hydrostatics']
                    App.Console.PrintMessage(f"Draft: {h['draft']:.2f} m\n")
                    App.Console.PrintMessage(f"GM (corrected): {h['GM_corrected']:.3f} m\n")
            
            doc.recompute()
            
        except Exception as e:
            App.Console.PrintError(f"❌ Error: {e}\n")
            import traceback
            traceback.print_exc()
    
    def calculate_all_items(self, lc, doc):
        """Calculate ALL items in the spreadsheet - simple and reliable."""
        # RESET totals
        total_mass = 0.0
        total_mom_x = 0.0
        total_mom_y = 0.0
        total_mom_z = 0.0
        total_fsm = 0.0
        
        tank_count = 0
        weight_count = 0
        cargo_count = 0
        
        App.Console.PrintMessage("📊 Processing ALL items:\n")
        
        # Process all rows from 1 to 300
        for row in range(1, 300):
            cell_a = get_cell(lc, f'A{row}')
            if not cell_a:
                continue
            
            cell_a_str = str(cell_a).strip()
            
            # ============================================================
            # CHECK 1: Is this a TANK? (contains [TankName])
            # ============================================================
            if '[' in cell_a_str and ']' in cell_a_str:
                # Extract tank name
                match = re.search(r'\[([A-Za-z0-9_]+)\]', cell_a_str)
                if match:
                    tank_name = match.group(1)
                    tank_obj = doc.getObject(tank_name)
                    if tank_obj:
                        try:
                            # Get parameters
                            density = to_float(get_cell(lc, f'B{row}', "1025"), 1025)
                            fill_percent = to_float(get_cell(lc, f'C{row}', "50"), 50)
                            
                            # CALCULATE TANK FRESH
                            result = calculate_tank(tank_obj, fill_percent, density)
                            if result:
                                mass, cog_x, cog_y, cog_z, fsm = result
                                
                                # Calculate moments
                                mom_x = mass * cog_x
                                mom_y = mass * cog_y
                                mom_z = mass * cog_z
                                
                                # WRITE ALL VALUES
                                lc.set(f'D{row}', f"{mass:.1f}")      # Mass
                                lc.set(f'E{row}', f"{cog_x:.3f}")     # LCG
                                lc.set(f'F{row}', f"{cog_y:.3f}")     # TCG
                                lc.set(f'G{row}', f"{cog_z:.3f}")     # VCG
                                lc.set(f'H{row}', f"{mom_x:.1f}")     # MomX
                                lc.set(f'I{row}', f"{mom_y:.1f}")     # MomY
                                lc.set(f'J{row}', f"{mom_z:.1f}")     # MomZ
                                lc.set(f'K{row}', f"{fsm:.3f}")       # FSM
                                
                                # Add to totals
                                total_mass += mass
                                total_mom_x += mom_x
                                total_mom_y += mom_y
                                total_mom_z += mom_z
                                total_fsm += fsm
                                
                                tank_count += 1
                                App.Console.PrintMessage(f"  Tank [{tank_name:15s}] = {mass:8,.0f} kg\n")
                        
                        except Exception as e:
                            App.Console.PrintWarning(f"  Tank {tank_name} error: {e}\n")
                
                continue  # Skip to next row after processing tank
            
            # ============================================================
            # CHECK 2: Is this a WEIGHT or CARGO item?
            # ============================================================
            # Skip headers and empty rows
            if cell_a_str.upper() in ["NAME", "TYPE", "TOTAL", "", "WEIGHTS", "CARGO", "TANKS"]:
                continue
            
            # Check if this row has a TYPE in column B (weight or cargo)
            cell_b = get_cell(lc, f'B{row}')
            cell_b_str = str(cell_b).strip().upper()
            
            if cell_b_str in ["WEIGHT", "CARGO", "STATIC", "ITEM"]:
                # This is a weight or cargo item
                
                # Try to get mass from various sources
                mass = 0.0
                
                # First: Try column D (mass column)
                mass_str = get_cell(lc, f'D{row}', "0")
                mass = to_float(mass_str)
                
                # Second: If no mass in D, try to find object by name
                if mass <= 0:
                    obj_name = cell_a_str
                    for obj in doc.Objects:
                        if hasattr(obj, 'Label') and obj.Label == obj_name:
                            if hasattr(obj, 'Mass'):
                                mass = float(obj.Mass)
                                # Update spreadsheet
                                lc.set(f'D{row}', f"{mass:.1f}")
                                break
                
                if mass <= 0:
                    continue  # Skip if no mass found
                
                # Get COG values
                cog_x = to_float(get_cell(lc, f'E{row}', "0"))
                cog_y = to_float(get_cell(lc, f'F{row}', "0"))
                cog_z = to_float(get_cell(lc, f'G{row}', "0"))
                
                # If COG is 0, try to get from object
                if cog_x == 0 and cog_y == 0 and cog_z == 0:
                    obj_name = cell_a_str
                    for obj in doc.Objects:
                        if hasattr(obj, 'Label') and obj.Label == obj_name:
                            if hasattr(obj, 'COG'):
                                cog_x = float(obj.COG.x) / 1000.0
                                cog_y = float(obj.COG.y) / 1000.0
                                cog_z = float(obj.COG.z) / 1000.0
                                # Update spreadsheet
                                lc.set(f'E{row}', f"{cog_x:.3f}")
                                lc.set(f'F{row}', f"{cog_y:.3f}")
                                lc.set(f'G{row}', f"{cog_z:.3f}")
                            break
                
                # Calculate moments
                mom_x = mass * cog_x
                mom_y = mass * cog_y
                mom_z = mass * cog_z
                
                # Get FSM (Free Surface Moment)
                fsm = to_float(get_cell(lc, f'K{row}', "0"))
                
                # Update moments and FSM in spreadsheet
                lc.set(f'H{row}', f"{mom_x:.2f}")
                lc.set(f'I{row}', f"{mom_y:.2f}")
                lc.set(f'J{row}', f"{mom_z:.2f}")
                lc.set(f'K{row}', f"{fsm:.3f}")
                
                # Add to totals
                total_mass += mass
                total_mom_x += mom_x
                total_mom_y += mom_y
                total_mom_z += mom_z
                total_fsm += fsm
                
                # Count item type
                if cell_b_str == "WEIGHT" or "WEIGHT" in cell_a_str.upper():
                    weight_count += 1
                    item_type = "Weight"
                else:
                    cargo_count += 1
                    item_type = "Cargo"
                
                App.Console.PrintMessage(f"  {item_type:6s} {cell_a_str[:20]:20s} = {mass:8,.0f} kg\n")
            
            # ============================================================
            # CHECK 3: Try to detect weight/cargo by checking if column D has mass
            # ============================================================
            else:
                # Check if column D has a mass value
                mass_str = get_cell(lc, f'D{row}', "0")
                mass = to_float(mass_str)
                
                if mass > 0:
                    # This might be a weight or cargo item without TYPE in column B
                    
                    # Get COG values
                    cog_x = to_float(get_cell(lc, f'E{row}', "0"))
                    cog_y = to_float(get_cell(lc, f'F{row}', "0"))
                    cog_z = to_float(get_cell(lc, f'G{row}', "0"))
                    
                    # Calculate moments
                    mom_x = mass * cog_x
                    mom_y = mass * cog_y
                    mom_z = mass * cog_z
                    
                    # Get FSM
                    fsm = to_float(get_cell(lc, f'K{row}', "0"))
                    
                    # Update moments if not already set
                    current_mom_x = to_float(get_cell(lc, f'H{row}', "0"))
                    if current_mom_x == 0:
                        lc.set(f'H{row}', f"{mom_x:.2f}")
                        lc.set(f'I{row}', f"{mom_y:.2f}")
                        lc.set(f'J{row}', f"{mom_z:.2f}")
                        lc.set(f'K{row}', f"{fsm:.3f}")
                    
                    # Add to totals
                    total_mass += mass
                    total_mom_x += mom_x
                    total_mom_y += mom_y
                    total_mom_z += mom_z
                    total_fsm += fsm
                    
                    cargo_count += 1  # Assume it's cargo if no type specified
                    App.Console.PrintMessage(f"  Cargo? {cell_a_str[:20]:20s} = {mass:8,.0f} kg\n")
        
        # ============================================================
        # UPDATE SUMMARY - ALWAYS AT THE ORIGINAL POSITIONS!
        # ============================================================
        App.Console.PrintMessage(f"\n📊 Summary of processed items:\n")
        App.Console.PrintMessage(f"  Tanks:   {tank_count}\n")
        App.Console.PrintMessage(f"  Weights: {weight_count}\n")
        App.Console.PrintMessage(f"  Cargo:   {cargo_count}\n")
        App.Console.PrintMessage(f"  Total:   {tank_count + weight_count + cargo_count}\n")
        
        if total_mass > 0:
            cog_x = total_mom_x / total_mass
            cog_y = total_mom_y / total_mass
            cog_z = total_mom_z / total_mass
            fsm_lever = total_fsm / total_mass 
            
            # Store in state
            _calculation_state['total_mass'] = total_mass
            
            # WRITE SUMS AT THE ORIGINAL POSITIONS - CRITICAL!
            lc.set('D4', f"{total_mass:.2f}")        # Total Mass
            lc.set('E5', f"{cog_x:.3f}")            # COG X (LCG)
            lc.set('F5', f"{cog_y:.3f}")            # COG Y (TCG)
            lc.set('G5', f"{cog_z:.3f}")            # COG Z (VCG)
            lc.set('H4', f"{total_fsm:.4f}")        # Free Surface Moment
            # H5 wird NICHT hier überschrieben - bleibt für hydrostatischen FSM Hebel!
            lc.set('I6', f"{total_mom_x:.2f}")      # Moment X
            lc.set('J6', f"{total_mom_y:.2f}")      # Moment Y
            lc.set('K6', f"{total_mom_z:.2f}")      # Moment Z
            
            App.Console.PrintMessage(f"\n📈 CALCULATION COMPLETE:\n")
            App.Console.PrintMessage(f"  Total Mass: {total_mass:,.0f} kg\n")
            App.Console.PrintMessage(f"  COG X (LCG): {cog_x:.3f} m\n")
            App.Console.PrintMessage(f"  COG Y (TCG): {cog_y:.3f} m\n")
            App.Console.PrintMessage(f"  COG Z (VCG): {cog_z:.3f} m\n")
            App.Console.PrintMessage(f"  Total FSM: {total_fsm:.3f} t·m²\n")
            
            return {
                'mass': total_mass,
                'cog': (cog_x, cog_y, cog_z),
                'fsm': total_fsm,
                'moments': (total_mom_x, total_mom_y, total_mom_z)
            }
        else:
            App.Console.PrintWarning("  No mass found - resetting summary\n")
            # Reset summary
            lc.set('D4', "0.00")
            lc.set('E5', "0.000")
            lc.set('F5', "0.000")
            lc.set('G5', "0.000")
            lc.set('H4', "0.0000")
            # H5 NICHT zurücksetzen - bleibt erhalten für hydrostatischen Wert
            lc.set('I6', "0.00")
            lc.set('J6', "0.00")
            lc.set('K6', "0.00")
            return None
    
    def IsActive(self):
        return App.ActiveDocument is not None

# Register command
Gui.addCommand('Ship_CalculateLoadCondition', CalculateLoadCondition())
