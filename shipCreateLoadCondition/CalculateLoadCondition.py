# shipCreateLoadCondition/CalculateLoadCondition.py - ULTIMATE NO-DOUBLE-COUNTING
import FreeCAD as App
import FreeCADGui as Gui
import os
import re
from PySide import QtCore, QtGui

_resource_dir = os.path.join(os.path.dirname(__file__), "..", "resources")
_icon_path    = os.path.join(_resource_dir, "icons", "ship_calc.svg")

# ============================================================================
# STATE TRACKING
# ============================================================================
_calculation_state = {
    'last_calculation_time': 0,
    'processed_rows':        set(),
    'total_mass':            0.0,
}

def reset_calculation_state():
    _calculation_state['last_calculation_time'] = 0
    _calculation_state['processed_rows']        = set()
    _calculation_state['total_mass']            = 0.0

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================
def get_cell(lc, cell, default=""):
    try:
        val = lc.get(cell)
        return str(val).strip() if val is not None else default
    except Exception:
        return default

def to_float(text, default=0.0):
    if not text:
        return default
    try:
        cleaned = re.sub(r'[^\d\.\-]', '', str(text))
        return float(cleaned) if cleaned else default
    except Exception:
        return default

# ============================================================================
# TANK CALCULATION
# ============================================================================
def calculate_tank(tank_obj, fill_percent, density):
    try:
        if not hasattr(tank_obj, 'Shape'):
            return None

        fill_ratio = fill_percent / 100.0
        bb         = tank_obj.Shape.BoundBox

        volume_m3     = (bb.XLength * bb.YLength * bb.ZLength) / 1e9
        filled_volume = volume_m3 * fill_ratio
        mass_kg       = filled_volume * density

        cog_x = bb.Center.x
        cog_y = bb.Center.y
        cog_z = bb.ZMin + (bb.ZLength * fill_ratio / 2)

        fsm = 0.0
        if 0 < fill_percent < 100:
            length_m     = bb.XLength / 1000.0
            width_m      = bb.YLength / 1000.0
            i_m4         = (length_m * width_m ** 3) / 12.0
            density_t_m3 = density / 1000.0
            fsm          = i_m4 * density_t_m3

        return mass_kg, cog_x / 1000.0, cog_y / 1000.0, cog_z / 1000.0, fsm
    except Exception:
        return None


# ============================================================================
# SHIP / SPREADSHEET FINDER
# ============================================================================
def find_ship_instance(doc):
    for obj in doc.Objects:
        if hasattr(obj, 'TypeId') and 'Ship' in obj.TypeId:
            if hasattr(obj, 'Group') and obj.Group:
                for child in obj.Group:
                    if (hasattr(child, 'TypeId') and
                            child.TypeId == 'Spreadsheet::Sheet' and
                            'LoadCondition' in child.Label):
                        return obj, child
            for child_obj in doc.Objects:
                if (hasattr(child_obj, 'TypeId') and
                        child_obj.TypeId == 'Spreadsheet::Sheet' and
                        'LoadCondition' in child_obj.Label):
                    if hasattr(obj, 'Group') and child_obj in obj.Group:
                        return obj, child_obj
    return None, None


def find_loadcondition_spreadsheet(doc):
    ship_obj, lc = find_ship_instance(doc)
    if lc:
        App.Console.PrintMessage(
            f"  ✓ LoadCondition in Ship-Instanz: {ship_obj.Label}\n")
        return lc

    App.Console.PrintWarning(
        "  ⚠ LoadCondition nicht in Ship-Instanz – suche im Root...\n")
    for obj in doc.Objects:
        if obj.TypeId == 'Spreadsheet::Sheet' and 'LoadCondition' in obj.Label:
            App.Console.PrintMessage(
                f"  ✓ LoadCondition im Root: {obj.Label}\n")
            return obj
    return None


def find_ship_object(doc):
    """Findet das Schiffsobjekt (geometrisches Shape) für SinkAndTrim."""
    for obj in doc.Objects:
        if 'Ship' in obj.Label and hasattr(obj, 'Shape'):
            return obj
    for obj in doc.Objects:
        if hasattr(obj, 'Shape') and obj.Shape:
            try:
                bbox = obj.Shape.BoundBox
                if bbox.XLength > bbox.YLength * 2 and bbox.XLength > 1000:
                    return obj
            except Exception:
                continue
    return None


# ============================================================================
# SINKTRIM – ohne UI
# ============================================================================
def _run_sink_and_trim(doc, lc):
    """
    Ruft shipSinkAndTrim.Tools.compute() ohne UI auf.
    SinkAndTrim ist der alleinige Eigentümer von E4/F4/G4/H5/D6.
    Gibt das result-dict zurück oder None bei Fehler.
    """
    import_paths = [
        'freecad.ship.shipSinkAndTrim.Tools',
        'ship.shipSinkAndTrim.Tools',
        'shipSinkAndTrim.Tools',
    ]

    compute_func = None
    for path in import_paths:
        try:
            module       = __import__(path, fromlist=['compute'])
            compute_func = getattr(module, 'compute', None)
            if compute_func:
                App.Console.PrintMessage(
                    f"  SinkAndTrim importiert von: {path}\n")
                break
        except ImportError:
            continue

    if not compute_func:
        App.Console.PrintWarning(
            "  ⚠ shipSinkAndTrim.Tools.compute nicht gefunden –"
            " Hydrostatik übersprungen.\n")
        return None

    ship_obj = find_ship_object(doc)
    if not ship_obj:
        App.Console.PrintWarning(
            "  ⚠ Kein Schiffsobjekt gefunden –"
            " Hydrostatik übersprungen.\n")
        return None

    App.Console.PrintMessage(
        "  SinkAndTrim liest jetzt:\n"
        f"    D4 (Masse) = {get_cell(lc, 'D4')} kg\n"
        f"    G5 (KG)    = {get_cell(lc, 'G5')} m\n"
        f"    H4 (FSM)   = {get_cell(lc, 'H4')} t·m²\n")

    try:
        result_tuple = compute_func(lc, fs_ref=True,
                                    ship_obj=ship_obj, doc=doc)
    except Exception as e:
        App.Console.PrintError(f"  ❌ SinkAndTrim Fehler: {e}\n")
        import traceback
        traceback.print_exc()
        return None

    if not result_tuple or len(result_tuple) < 6:
        App.Console.PrintWarning("  ⚠ SinkAndTrim lieferte kein Ergebnis.\n")
        return None

    _group, draft, trim, displacement, _vis, result_dict = result_tuple[:6]

    # Tiefgang sicher in Meter
    if hasattr(draft, 'getValueAs'):
        draft_m = float(draft.getValueAs('m'))
    elif hasattr(draft, 'Value'):
        raw     = draft.Value
        draft_m = raw / 1000.0 if raw > 100 else raw
    elif draft is not None:
        raw     = float(draft)
        draft_m = raw / 1000.0 if raw > 100 else raw
    else:
        draft_m = 0.0

    trim_val = 0.0
    if trim is not None:
        trim_val = trim.Value if hasattr(trim, 'Value') else float(trim)

    if isinstance(result_dict, dict):
        gm  = result_dict.get('gm',  0.0)
        kmt = result_dict.get('kmt', 0.0)
    else:
        gm  = 0.0
        kmt = 0.0

    gm_val  = gm.Value  if hasattr(gm,  'Value') else float(gm  or 0.0)
    kmt_val = kmt.Value if hasattr(kmt, 'Value') else float(kmt or 0.0)

    App.Console.PrintMessage(
        f"\n{'='*60}\n"
        f"  HYDROSTATIK ERGEBNIS:\n"
        f"    Tiefgang : {draft_m:.3f} m\n"
        f"    Trim     : {trim_val:.2f}°\n"
        f"    KMt      : {kmt_val:.3f} m\n"
        f"    GMt      : {gm_val:.3f} m\n")

    if gm_val > 0.5:
        App.Console.PrintMessage("    Stabilität: ✓ GUT (GM > 0.5 m)\n")
    elif gm_val > 0.15:
        App.Console.PrintMessage("    Stabilität: ⚠ AKZEPTABEL\n")
    elif gm_val > 0:
        App.Console.PrintMessage("    Stabilität: ⚠ KRITISCH\n")
    else:
        App.Console.PrintMessage("    Stabilität: ✗ INSTABIL!\n")

    App.Console.PrintMessage(f"{'='*60}\n")

    return result_dict


# ============================================================================
# MAIN CLASS
# ============================================================================
class CalculateLoadCondition:

    def GetResources(self):
        return {
            'Pixmap':   _icon_path,
            'MenuText': "Calculate Load Case",
            'ToolTip':  ("Berechnet Masse/COG/FSM und ruft danach automatisch "
                         "SinkAndTrim (Tiefgang/KM/GM) auf."),
            'CmdType':  "ForEdit",
        }

    def Activated(self):
        self.recalculate_current()

    def recalculate_current(self):
        """
        REIHENFOLGE (kritisch – nie ändern!):
          1. calculate_all_items()  → D4 / E5 / F5 / G5 / H4
          2. doc.recompute()        → Formeln propagieren
          3. _run_sink_and_trim()   → E4 / F4 / G4 / H5 / D6
        """
        doc = App.activeDocument()
        if not doc:
            return

        lc = find_loadcondition_spreadsheet(doc)
        if not lc:
            App.Console.PrintError("❌ Kein LoadCondition-Spreadsheet!\n")
            return

        App.Console.PrintMessage(f"\n{'='*60}\n")
        App.Console.PrintMessage("🔄 BERECHNUNG START\n")
        App.Console.PrintMessage(f"{'='*60}\n")

        reset_calculation_state()

        try:
            # ── 1. Masse / COG / FSM ──────────────────────────────────────
            result = self.calculate_all_items(lc, doc)
            if not result:
                App.Console.PrintWarning("  Keine Massen – Abbruch.\n")
                return

            App.Console.PrintMessage(
                f"\n✅ GEWICHTSRECHNUNG ABGESCHLOSSEN:\n"
                f"  Masse : {result['mass']:,.0f} kg\n"
                f"  LCG   : {result['cog'][0]:.3f} m\n"
                f"  TCG   : {result['cog'][1]:.3f} m\n"
                f"  KG    : {result['cog'][2]:.3f} m\n"
                f"  FSM   : {result['fsm']:.4f} t·m²\n")

            # ── 2. Propagieren ────────────────────────────────────────────
            doc.recompute()
            App.Console.PrintMessage(
                "  ✓ doc.recompute() – Spreadsheet-Formeln aktualisiert\n")

            # ── 3. SinkAndTrim ohne UI ────────────────────────────────────
            App.Console.PrintMessage(
                f"\n{'='*60}\n"
                "🌊 STARTE SINKTRIM (ohne UI)\n"
                f"{'='*60}\n")

            _run_sink_and_trim(doc, lc)

        except Exception as e:
            App.Console.PrintError(f"❌ Fehler: {e}\n")
            import traceback
            traceback.print_exc()

    # -------------------------------------------------------------------------
    def calculate_all_items(self, lc, doc):
        """Verarbeitet alle Zeilen und schreibt Summen nach D4/E5/F5/G5/H4."""

        total_mass  = 0.0
        total_mom_x = 0.0
        total_mom_y = 0.0
        total_mom_z = 0.0
        total_fsm   = 0.0
        tank_count  = weight_count = cargo_count = 0

        App.Console.PrintMessage("📊 Verarbeite alle Einträge:\n")

        for row in range(1, 300):
            cell_a     = get_cell(lc, f'A{row}')
            cell_a_str = str(cell_a).strip()
            if not cell_a_str:
                continue

            # ── TANKS ──────────────────────────────────────────────────────
            if '[' in cell_a_str and ']' in cell_a_str:
                match = re.search(r'\[([A-Za-z0-9_]+)\]', cell_a_str)
                if match:
                    tank_name = match.group(1)
                    tank_obj  = doc.getObject(tank_name)
                    if tank_obj:
                        try:
                            density = to_float(
                                get_cell(lc, f'B{row}', "1025"), 1025)
                            fill    = to_float(
                                get_cell(lc, f'C{row}', "50"), 50)
                            res = calculate_tank(tank_obj, fill, density)
                            if res:
                                mass, cx, cy, cz, fsm = res
                                mx, my, mz = mass*cx, mass*cy, mass*cz
                                lc.set(f'D{row}', f"{mass:.1f}")
                                lc.set(f'E{row}', f"{cx:.3f}")
                                lc.set(f'F{row}', f"{cy:.3f}")
                                lc.set(f'G{row}', f"{cz:.3f}")
                                lc.set(f'H{row}', f"{mx:.1f}")
                                lc.set(f'I{row}', f"{my:.1f}")
                                lc.set(f'J{row}', f"{mz:.1f}")
                                lc.set(f'K{row}', f"{fsm:.3f}")
                                total_mass  += mass
                                total_mom_x += mx
                                total_mom_y += my
                                total_mom_z += mz
                                total_fsm   += fsm
                                tank_count  += 1
                                App.Console.PrintMessage(
                                    f"  Tank  [{tank_name:15s}]"
                                    f" = {mass:10,.0f} kg\n")
                        except Exception as e:
                            App.Console.PrintWarning(
                                f"  Tank {tank_name}: {e}\n")
                continue

            # ── Header überspringen ────────────────────────────────────────
            if cell_a_str.upper() in ("NAME", "TYPE", "TOTAL", "",
                                       "WEIGHTS", "CARGO", "TANKS",
                                       "CRANES", "END"):
                continue

            cell_b_str = get_cell(lc, f'B{row}').strip().upper()

            # ── GEWICHTE / KRANE mit TYPE ──────────────────────────────────
            if cell_b_str in ("WEIGHT", "CARGO", "STATIC", "ITEM",
                               "KRANBAUM", "LAST AM HAKEN"):
                mass = to_float(get_cell(lc, f'D{row}', "0"))
                if mass <= 0:
                    for obj in doc.Objects:
                        if (hasattr(obj, 'Label') and
                                obj.Label == cell_a_str and
                                hasattr(obj, 'Mass')):
                            mass = float(obj.Mass)
                            lc.set(f'D{row}', f"{mass:.1f}")
                            break
                if mass <= 0:
                    continue

                cx = to_float(get_cell(lc, f'E{row}', "0"))
                cy = to_float(get_cell(lc, f'F{row}', "0"))
                cz = to_float(get_cell(lc, f'G{row}', "0"))

                if cx == 0 and cy == 0 and cz == 0:
                    for obj in doc.Objects:
                        if (hasattr(obj, 'Label') and
                                obj.Label == cell_a_str and
                                hasattr(obj, 'COG')):
                            cx = float(obj.COG.x) / 1000.0
                            cy = float(obj.COG.y) / 1000.0
                            cz = float(obj.COG.z) / 1000.0
                            lc.set(f'E{row}', f"{cx:.3f}")
                            lc.set(f'F{row}', f"{cy:.3f}")
                            lc.set(f'G{row}', f"{cz:.3f}")
                            break

                mx  = mass * cx
                my  = mass * cy
                mz  = mass * cz
                fsm = to_float(get_cell(lc, f'K{row}', "0"))

                lc.set(f'H{row}', f"{mx:.2f}")
                lc.set(f'I{row}', f"{my:.2f}")
                lc.set(f'J{row}', f"{mz:.2f}")
                lc.set(f'K{row}', f"{fsm:.3f}")

                total_mass  += mass
                total_mom_x += mx
                total_mom_y += my
                total_mom_z += mz
                total_fsm   += fsm

                itype = ("Gewicht" if cell_b_str in
                         ("WEIGHT", "STATIC", "KRANBAUM", "LAST AM HAKEN")
                         else "Cargo")
                if itype == "Gewicht":
                    weight_count += 1
                else:
                    cargo_count += 1

                App.Console.PrintMessage(
                    f"  {itype:7s} {cell_a_str[:22]:22s}"
                    f" = {mass:10,.0f} kg\n")

            # ── FALLBACK ───────────────────────────────────────────────────
            else:
                mass = to_float(get_cell(lc, f'D{row}', "0"))
                if mass <= 0:
                    continue

                cx  = to_float(get_cell(lc, f'E{row}', "0"))
                cy  = to_float(get_cell(lc, f'F{row}', "0"))
                cz  = to_float(get_cell(lc, f'G{row}', "0"))
                mx  = mass * cx
                my  = mass * cy
                mz  = mass * cz
                fsm = to_float(get_cell(lc, f'K{row}', "0"))

                if to_float(get_cell(lc, f'H{row}', "0")) == 0:
                    lc.set(f'H{row}', f"{mx:.2f}")
                    lc.set(f'I{row}', f"{my:.2f}")
                    lc.set(f'J{row}', f"{mz:.2f}")
                    lc.set(f'K{row}', f"{fsm:.3f}")

                total_mass  += mass
                total_mom_x += mx
                total_mom_y += my
                total_mom_z += mz
                total_fsm   += fsm
                cargo_count += 1

                App.Console.PrintMessage(
                    f"  Fallbck  {cell_a_str[:22]:22s}"
                    f" = {mass:10,.0f} kg\n")

        # ── Summen schreiben ───────────────────────────────────────────────
        App.Console.PrintMessage(
            f"\n  Tanks:{tank_count}  Gewichte:{weight_count}  "
            f"Cargo:{cargo_count}  "
            f"Gesamt:{tank_count+weight_count+cargo_count}\n")

        if total_mass <= 0:
            App.Console.PrintWarning("  Keine Masse – Reset Summen.\n")
            for c, v in (('D4',"0.00"),('E5',"0.000"),('F5',"0.000"),
                         ('G5',"0.000"),('H4',"0.0000"),
                         ('I6',"0.00"),('J6',"0.00"),('K6',"0.00")):
                lc.set(c, v)
            return None

        cog_x = total_mom_x / total_mass
        cog_y = total_mom_y / total_mass
        cog_z = total_mom_z / total_mass

        _calculation_state['total_mass'] = total_mass

        # Masse/COG/FSM – NUR diese Zellen!
        # E4/F4/G4/H5/D6 gehören ausschließlich SinkAndTrim.
        lc.set('D4', f"{total_mass:.2f}")
        lc.set('E5', f"{cog_x:.3f}")
        lc.set('F5', f"{cog_y:.3f}")
        lc.set('G5', f"{cog_z:.3f}")
        lc.set('H4', f"{total_fsm:.4f}")
        lc.set('I6', f"{total_mom_x:.2f}")
        lc.set('J6', f"{total_mom_y:.2f}")
        lc.set('K6', f"{total_mom_z:.2f}")

        App.Console.PrintMessage(
            f"\n  → D4={total_mass:,.0f} kg | "
            f"G5(KG)={cog_z:.3f} m | "
            f"H4(FSM)={total_fsm:.4f} t·m²\n")

        return {
            'mass':    total_mass,
            'cog':     (cog_x, cog_y, cog_z),
            'fsm':     total_fsm,
            'moments': (total_mom_x, total_mom_y, total_mom_z),
        }

    def IsActive(self):
        return App.ActiveDocument is not None


# Register command
Gui.addCommand('Ship_CalculateLoadCondition', CalculateLoadCondition())
