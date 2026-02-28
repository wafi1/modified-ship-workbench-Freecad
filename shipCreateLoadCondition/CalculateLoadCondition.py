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
        cleaned = re.sub(r'[^\d\.\-]', '', str(text))
        return float(cleaned) if cleaned else default
    except:
        return default

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
            width_m  = bb.YLength / 1000.0
            i_m4     = (length_m * width_m ** 3) / 12.0
            density_t_m3 = density / 1000.0
            fsm = i_m4 * density_t_m3

        return mass_kg, cog_x/1000.0, cog_y/1000.0, cog_z/1000.0, fsm
    except:
        return None


def find_ship_instance(doc):
    """Find the ship instance in the document."""
    for obj in doc.Objects:
        if hasattr(obj, 'TypeId') and 'Ship' in obj.TypeId:
            if hasattr(obj, 'Group') and obj.Group:
                for child in obj.Group:
                    if hasattr(child, 'TypeId') and child.TypeId == 'Spreadsheet::Sheet':
                        if 'LoadCondition' in child.Label:
                            return obj, child
            for child_obj in doc.Objects:
                if (hasattr(child_obj, 'TypeId') and
                    child_obj.TypeId == 'Spreadsheet::Sheet' and
                    'LoadCondition' in child_obj.Label):
                    if hasattr(obj, 'Group') and child_obj in obj.Group:
                        return obj, child_obj
    return None, None


def find_loadcondition_spreadsheet(doc):
    """Find the LoadCondition spreadsheet - first in ship instance, then in root."""
    ship_obj, lc = find_ship_instance(doc)
    if lc:
        App.Console.PrintMessage(
            f"✓ Found LoadCondition in ship instance: {ship_obj.Label}\n")
        return lc

    App.Console.PrintWarning(
        "⚠ LoadCondition not found in ship instance, searching in root...\n")
    for obj in doc.Objects:
        if obj.TypeId == 'Spreadsheet::Sheet' and 'LoadCondition' in obj.Label:
            App.Console.PrintMessage(
                f"✓ Found LoadCondition in document root: {obj.Label}\n")
            return obj
    return None


# ============================================================================
# MAIN CLASS - GUARANTEED NO DOUBLE COUNTING
# ============================================================================
class CalculateLoadCondition:
    def GetResources(self):
        return {
            'Pixmap':   _icon_path,
            'MenuText': "Calculate Load Case",
            'ToolTip':  "Calculate load condition (no double counting)",
            'CmdType':  "ForEdit"
        }

    def Activated(self):
        self.recalculate_current()

    def recalculate_current(self):
        """
        Main function - ALWAYS starts fresh.

        Responsibility: mass / COG / FSM only.
        Hydrostatics (draft, KM, GM) are the exclusive domain of
        ShipSinkAndTrim – this function never writes E4/F4/G4/H5/D6.
        """
        doc = App.activeDocument()
        if not doc:
            return

        lc = find_loadcondition_spreadsheet(doc)
        if not lc:
            App.Console.PrintError("❌ No LoadCondition spreadsheet found!\n")
            App.Console.PrintError("   Please check:\n")
            App.Console.PrintError("   1. That a Ship instance exists\n")
            App.Console.PrintError(
                "   2. That the LoadCondition spreadsheet is inside "
                "the Ship instance\n")
            return

        App.Console.PrintMessage(f"\n{'='*60}\n")
        App.Console.PrintMessage("🔄 CALCULATION START (Fresh)\n")
        App.Console.PrintMessage(f"{'='*60}\n")

        # ALWAYS reset state before calculation
        reset_calculation_state()

        try:
            result = self.calculate_all_items(lc, doc)

            if result:
                App.Console.PrintMessage("\n✅ FINAL RESULTS:\n")
                App.Console.PrintMessage(
                    f"  Total Mass : {result['mass']:,.0f} kg\n")
                App.Console.PrintMessage(
                    f"  COG X (LCG): {result['cog'][0]:.3f} m\n")
                App.Console.PrintMessage(
                    f"  COG Y (TCG): {result['cog'][1]:.3f} m\n")
                App.Console.PrintMessage(
                    f"  COG Z (VCG): {result['cog'][2]:.3f} m\n")
                App.Console.PrintMessage(
                    f"  Total FSM  : {result['fsm']:.3f} t·m²\n")
                App.Console.PrintMessage(
                    "  Hydrostatics (draft/KM/GM) → computed by "
                    "ShipSinkAndTrim.\n")
            else:
                App.Console.PrintWarning("  No items found or total mass = 0\n")

            # Propagate spreadsheet formulas before SinkAndTrim reads them
            doc.recompute()
            App.Console.PrintMessage("  ✓ doc.recompute() done\n")

        except Exception as e:
            App.Console.PrintError(f"❌ Error: {e}\n")
            import traceback
            traceback.print_exc()

    def calculate_all_items(self, lc, doc):
        """Calculate ALL items in the spreadsheet - simple and reliable."""
        total_mass  = 0.0
        total_mom_x = 0.0
        total_mom_y = 0.0
        total_mom_z = 0.0
        total_fsm   = 0.0

        tank_count   = 0
        weight_count = 0
        cargo_count  = 0

        App.Console.PrintMessage("📊 Processing ALL items:\n")

        for row in range(1, 300):
            cell_a = get_cell(lc, f'A{row}')
            if not cell_a:
                continue

            cell_a_str = str(cell_a).strip()

            # ----------------------------------------------------------------
            # TANKS  →  [TankName] in column A
            # ----------------------------------------------------------------
            if '[' in cell_a_str and ']' in cell_a_str:
                match = re.search(r'\[([A-Za-z0-9_]+)\]', cell_a_str)
                if match:
                    tank_name = match.group(1)
                    tank_obj  = doc.getObject(tank_name)
                    if tank_obj:
                        try:
                            density      = to_float(get_cell(lc, f'B{row}', "1025"), 1025)
                            fill_percent = to_float(get_cell(lc, f'C{row}', "50"),   50)

                            result = calculate_tank(tank_obj, fill_percent, density)
                            if result:
                                mass, cog_x, cog_y, cog_z, fsm = result

                                mom_x = mass * cog_x
                                mom_y = mass * cog_y
                                mom_z = mass * cog_z

                                lc.set(f'D{row}', f"{mass:.1f}")
                                lc.set(f'E{row}', f"{cog_x:.3f}")
                                lc.set(f'F{row}', f"{cog_y:.3f}")
                                lc.set(f'G{row}', f"{cog_z:.3f}")
                                lc.set(f'H{row}', f"{mom_x:.1f}")
                                lc.set(f'I{row}', f"{mom_y:.1f}")
                                lc.set(f'J{row}', f"{mom_z:.1f}")
                                lc.set(f'K{row}', f"{fsm:.3f}")

                                total_mass  += mass
                                total_mom_x += mom_x
                                total_mom_y += mom_y
                                total_mom_z += mom_z
                                total_fsm   += fsm

                                tank_count += 1
                                App.Console.PrintMessage(
                                    f"  Tank [{tank_name:15s}] = {mass:8,.0f} kg\n")

                        except Exception as e:
                            App.Console.PrintWarning(
                                f"  Tank {tank_name} error: {e}\n")

                continue  # Next row

            # ----------------------------------------------------------------
            # WEIGHTS / CARGO  →  TYPE keyword in column B
            # ----------------------------------------------------------------
            if cell_a_str.upper() in ["NAME", "TYPE", "TOTAL", "",
                                       "WEIGHTS", "CARGO", "TANKS", "CRANES",
                                       "END"]:
                continue

            cell_b     = get_cell(lc, f'B{row}')
            cell_b_str = str(cell_b).strip().upper()

            if cell_b_str in ["WEIGHT", "CARGO", "STATIC", "ITEM",
                               "KRANBAUM", "LAST AM HAKEN"]:
                mass_str = get_cell(lc, f'D{row}', "0")
                mass     = to_float(mass_str)

                if mass <= 0:
                    obj_name = cell_a_str
                    for obj in doc.Objects:
                        if hasattr(obj, 'Label') and obj.Label == obj_name:
                            if hasattr(obj, 'Mass'):
                                mass = float(obj.Mass)
                                lc.set(f'D{row}', f"{mass:.1f}")
                                break

                if mass <= 0:
                    continue

                cog_x = to_float(get_cell(lc, f'E{row}', "0"))
                cog_y = to_float(get_cell(lc, f'F{row}', "0"))
                cog_z = to_float(get_cell(lc, f'G{row}', "0"))

                if cog_x == 0 and cog_y == 0 and cog_z == 0:
                    for obj in doc.Objects:
                        if hasattr(obj, 'Label') and obj.Label == cell_a_str:
                            if hasattr(obj, 'COG'):
                                cog_x = float(obj.COG.x) / 1000.0
                                cog_y = float(obj.COG.y) / 1000.0
                                cog_z = float(obj.COG.z) / 1000.0
                                lc.set(f'E{row}', f"{cog_x:.3f}")
                                lc.set(f'F{row}', f"{cog_y:.3f}")
                                lc.set(f'G{row}', f"{cog_z:.3f}")
                            break

                mom_x = mass * cog_x
                mom_y = mass * cog_y
                mom_z = mass * cog_z
                fsm   = to_float(get_cell(lc, f'K{row}', "0"))

                lc.set(f'H{row}', f"{mom_x:.2f}")
                lc.set(f'I{row}', f"{mom_y:.2f}")
                lc.set(f'J{row}', f"{mom_z:.2f}")
                lc.set(f'K{row}', f"{fsm:.3f}")

                total_mass  += mass
                total_mom_x += mom_x
                total_mom_y += mom_y
                total_mom_z += mom_z
                total_fsm   += fsm

                if cell_b_str in ("WEIGHT", "STATIC", "KRANBAUM",
                                  "LAST AM HAKEN"):
                    weight_count += 1
                    item_type = "Weight"
                else:
                    cargo_count += 1
                    item_type = "Cargo"

                App.Console.PrintMessage(
                    f"  {item_type:6s} {cell_a_str[:20]:20s} = {mass:8,.0f} kg\n")

            # ----------------------------------------------------------------
            # FALLBACK  →  column D has mass, no TYPE in B
            # ----------------------------------------------------------------
            else:
                mass_str = get_cell(lc, f'D{row}', "0")
                mass     = to_float(mass_str)

                if mass > 0:
                    cog_x = to_float(get_cell(lc, f'E{row}', "0"))
                    cog_y = to_float(get_cell(lc, f'F{row}', "0"))
                    cog_z = to_float(get_cell(lc, f'G{row}', "0"))

                    mom_x = mass * cog_x
                    mom_y = mass * cog_y
                    mom_z = mass * cog_z
                    fsm   = to_float(get_cell(lc, f'K{row}', "0"))

                    # Only write moments if not already set
                    current_mom_x = to_float(get_cell(lc, f'H{row}', "0"))
                    if current_mom_x == 0:
                        lc.set(f'H{row}', f"{mom_x:.2f}")
                        lc.set(f'I{row}', f"{mom_y:.2f}")
                        lc.set(f'J{row}', f"{mom_z:.2f}")
                        lc.set(f'K{row}', f"{fsm:.3f}")

                    total_mass  += mass
                    total_mom_x += mom_x
                    total_mom_y += mom_y
                    total_mom_z += mom_z
                    total_fsm   += fsm

                    cargo_count += 1
                    App.Console.PrintMessage(
                        f"  Cargo? {cell_a_str[:20]:20s} = {mass:8,.0f} kg\n")

        # --------------------------------------------------------------------
        # WRITE SUMMARY TOTALS
        # --------------------------------------------------------------------
        App.Console.PrintMessage(f"\n📊 Summary of processed items:\n")
        App.Console.PrintMessage(f"  Tanks:   {tank_count}\n")
        App.Console.PrintMessage(f"  Weights: {weight_count}\n")
        App.Console.PrintMessage(f"  Cargo:   {cargo_count}\n")
        App.Console.PrintMessage(
            f"  Total:   {tank_count + weight_count + cargo_count}\n")

        if total_mass > 0:
            cog_x = total_mom_x / total_mass
            cog_y = total_mom_y / total_mass
            cog_z = total_mom_z / total_mass

            _calculation_state['total_mass'] = total_mass

            # Write mass / COG / FSM  ← ONLY these cells!
            # Hydrostatic cells (E4, F4, G4, H5, D6) are owned by SinkAndTrim.
            lc.set('D4', f"{total_mass:.2f}")   # Total Mass [kg]
            lc.set('E5', f"{cog_x:.3f}")        # LCG [m]
            lc.set('F5', f"{cog_y:.3f}")        # TCG [m]
            lc.set('G5', f"{cog_z:.3f}")        # VCG / KG [m]
            lc.set('H4', f"{total_fsm:.4f}")    # Free Surface Moment [t·m²]
            lc.set('I6', f"{total_mom_x:.2f}")  # Moment X
            lc.set('J6', f"{total_mom_y:.2f}")  # Moment Y
            lc.set('K6', f"{total_mom_z:.2f}")  # Moment Z

            App.Console.PrintMessage(f"\n📈 SPREADSHEET UPDATED:\n")
            App.Console.PrintMessage(f"  D4 Total Mass : {total_mass:,.0f} kg\n")
            App.Console.PrintMessage(f"  E5 LCG        : {cog_x:.3f} m\n")
            App.Console.PrintMessage(f"  F5 TCG        : {cog_y:.3f} m\n")
            App.Console.PrintMessage(f"  G5 VCG/KG     : {cog_z:.3f} m\n")
            App.Console.PrintMessage(f"  H4 FSM        : {total_fsm:.4f} t·m²\n")
            App.Console.PrintMessage(
                "  E4/F4/G4/H5/D6 → not touched (SinkAndTrim owns these)\n")

            return {
                'mass':    total_mass,
                'cog':     (cog_x, cog_y, cog_z),
                'fsm':     total_fsm,
                'moments': (total_mom_x, total_mom_y, total_mom_z),
            }
        else:
            App.Console.PrintWarning("  No mass found – resetting summary\n")
            lc.set('D4', "0.00")
            lc.set('E5', "0.000")
            lc.set('F5', "0.000")
            lc.set('G5', "0.000")
            lc.set('H4', "0.0000")
            lc.set('I6', "0.00")
            lc.set('J6', "0.00")
            lc.set('K6', "0.00")
            return None

    def IsActive(self):
        return App.ActiveDocument is not None


# Register command
Gui.addCommand('Ship_CalculateLoadCondition', CalculateLoadCondition())
