# -*- coding: utf-8 -*-
"""
CraneSpreadsheetTools.py
Gemeinsame Hilfsfunktionen für den Export von Krandaten
in das LoadCondition-Spreadsheet.
Wird verwendet von MonopileSwing.py und TaskLiftOperation.py
Erweitert um automatische Stabilitätsberechnung.

KORREKTE REIHENFOLGE der Stabilitätskette:
  1. write_crane_to_loadcondition()   → Krangewichte ins Sheet
  2. doc.recompute()
  3. recalculate_current()            → Summen / COG / FSM neu
  4. doc.recompute()
  5. compute() / SinkAndTrim          → Tiefgang / KM / GM
"""
import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtGui, QtCore
import traceback


# =============================================================================
# HILFSFUNKTIONEN
# =============================================================================

def find_loadcondition(doc):
    """
    Sucht das LoadCondition-Spreadsheet im Dokument.
    Tolerant gegenüber Leerzeichen, Gross-/Kleinschreibung und Unterstrichen.
    """
    candidates = []

    for obj in doc.Objects:
        if obj.TypeId != "Spreadsheet::Sheet":
            continue

        label_norm = obj.Label.replace(" ", "").replace("_", "").lower()
        name_norm  = obj.Name.replace(" ", "").replace("_", "").lower()

        if label_norm == "loadcondition" or name_norm == "loadcondition":
            App.Console.PrintMessage(
                f"  find_loadcondition: exakter Treffer → {obj.Label!r}\n")
            return obj

        if "loadcondition" in label_norm or "loadcondition" in name_norm:
            candidates.append((0, obj))
            continue

        if label_norm.startswith("lc") or name_norm.startswith("lc"):
            candidates.append((1, obj))
            continue

    if candidates:
        candidates.sort(key=lambda x: x[0])
        chosen = candidates[0][1]
        App.Console.PrintMessage(
            f"  find_loadcondition: naher Treffer → {chosen.Label!r}\n")
        return chosen

    App.Console.PrintWarning(
        "  find_loadcondition: KEIN Spreadsheet gefunden!\n"
        "  Vorhandene Spreadsheets im Dokument:\n")
    for obj in doc.Objects:
        if obj.TypeId == "Spreadsheet::Sheet":
            App.Console.PrintWarning(
                f"    Name={obj.Name!r}  Label={obj.Label!r}\n")
    return None


def get_crane_positions(crane):
    """
    Gibt Boom-CG und Sheave-Position (Aufhängepunkt) in Metern zurück.
    SheavePosition = Umlenkrolle an der Auslegerspitze = korrekter Aufhängepunkt
    für frei hängende Lasten (Pendeleffekt).

    Returns: (boom_pos, hook_pos) jeweils als (lcg, tcg, vcg) in Metern
    """
    if hasattr(crane, 'BoomCGPosition'):
        bg   = crane.BoomCGPosition
        boom = (bg.x / 1000.0, bg.y / 1000.0, bg.z / 1000.0)
    else:
        p    = crane.Placement.Base
        boom = (p.x / 1000.0, p.y / 1000.0, p.z / 1000.0)

    # SheavePosition = Auslegerspitze = korrekter Angriffspunkt der Last
    if hasattr(crane, 'SheavePosition'):
        sp   = crane.SheavePosition
        hook = (sp.x / 1000.0, sp.y / 1000.0, sp.z / 1000.0)
        App.Console.PrintMessage(
            f"  Aufhängepunkt (SheavePosition): "
            f"({hook[0]:.2f}, {hook[1]:.2f}, {hook[2]:.2f}) m\n")
    else:
        hook = boom
        App.Console.PrintWarning(
            "  ⚠ SheavePosition nicht gefunden – Last an BoomCG angesetzt!\n")

    return boom, hook


def _safe_get(lc, cell):
    try:
        val = lc.get(cell)
        return str(val).strip() if val is not None else ""
    except Exception:
        return ""


def _reset_all_hook_loads_in_spreadsheet(lc):
    """Setzt NUR die Haken-Lasten in der CRANES-Sektion auf Null."""
    in_cranes    = False
    empty_streak = 0
    MAX_EMPTY    = 20
    reset_count  = 0

    App.Console.PrintMessage("  _reset_all_hook_loads: Setze Haken-Lasten auf Null...\n")

    for row in range(1, 300):
        a = _safe_get(lc, f'A{row}')
        b = _safe_get(lc, f'B{row}')

        if a == "" and b == "":
            empty_streak += 1
            if empty_streak >= MAX_EMPTY:
                break
            continue
        else:
            empty_streak = 0

        if a == "CRANES":
            in_cranes = True
            continue

        if in_cranes and a in ("TANKS", "WEIGHTS", "CARGO", "END"):
            if reset_count > 0:
                App.Console.PrintMessage(
                    f"    {reset_count} Haken-Lasten zurückgesetzt\n")
            break

        if not in_cranes:
            continue

        if b == "Last am Haken":
            try:
                lc.set(f'D{row}', "0.0")
                lc.set(f'K{row}', "")
                reset_count += 1
                App.Console.PrintMessage(
                    f"    Zeile {row}: {a!r} Haken-Last → 0 kg\n")
            except Exception as e:
                App.Console.PrintWarning(
                    f"    Zeile {row}: Reset fehlgeschlagen: {e}\n")

    return reset_count > 0


def write_crane_to_loadcondition(lc, crane_data, reset_existing=True):
    """
    Schreibt Kran-Daten in die CRANES-Sektion des LoadCondition-Spreadsheets.
    """
    if reset_existing:
        _reset_all_hook_loads_in_spreadsheet(lc)

    updated      = 0
    in_cranes    = False
    empty_streak = 0
    MAX_EMPTY    = 20

    App.Console.PrintMessage(
        f"  write_crane_to_loadcondition: Suche CRANES-Sektion...\n"
        f"  Erwartete Kran-Labels: {list(crane_data.keys())}\n")

    for row in range(1, 300):
        a = _safe_get(lc, f'A{row}')
        b = _safe_get(lc, f'B{row}')

        if a == "" and b == "":
            empty_streak += 1
            if empty_streak >= MAX_EMPTY:
                break
            continue
        else:
            empty_streak = 0

        if a == "CRANES":
            in_cranes = True
            App.Console.PrintMessage(f"    Zeile {row}: CRANES-Sektion gefunden ✓\n")
            continue

        if in_cranes and a in ("TANKS", "WEIGHTS", "CARGO", "END"):
            break

        if not in_cranes:
            continue

        if a not in crane_data:
            continue

        data = crane_data[a]

        if b == "Kranbaum":
            lc.set(f'D{row}', f"{data['boom_kg']:.1f}")
            lc.set(f'E{row}', f"{data['boom_pos'][0]:.3f}")
            lc.set(f'F{row}', f"{data['boom_pos'][1]:.3f}")
            lc.set(f'G{row}', f"{data['boom_pos'][2]:.3f}")
            App.Console.PrintMessage(
                f"    Zeile {row}: {a!r} Kranbaum → "
                f"{data['boom_kg']:.0f} kg  @ "
                f"({data['boom_pos'][0]:.2f}, "
                f"{data['boom_pos'][1]:.2f}, "
                f"{data['boom_pos'][2]:.2f}) m\n")
            updated += 1

        elif b == "Last am Haken":
            lc.set(f'D{row}', f"{data['hook_kg']:.1f}")
            lc.set(f'E{row}', f"{data['hook_pos'][0]:.3f}")
            lc.set(f'F{row}', f"{data['hook_pos'][1]:.3f}")
            lc.set(f'G{row}', f"{data['hook_pos'][2]:.3f}")
            lc.set(f'K{row}',
                   "Counterweight" if data['hook_kg'] == 0 else "Hook load")
            App.Console.PrintMessage(
                f"    Zeile {row}: {a!r} Haken → "
                f"{data['hook_kg']:.0f} kg  @ "
                f"({data['hook_pos'][0]:.2f}, "
                f"{data['hook_pos'][1]:.2f}, "
                f"{data['hook_pos'][2]:.2f}) m\n")
            updated += 1

    if updated == 0:
        App.Console.PrintWarning(
            "  ⚠ Keine Zeilen aktualisiert!\n"
            f"  crane_data-Keys: {list(crane_data.keys())}\n")
    else:
        App.Console.PrintMessage(f"  ✓ {updated} Zeile(n) aktualisiert\n")

    return updated > 0


# =============================================================================
# STABILITÄTSKETTE
# =============================================================================

def run_stability_chain_after_crane(doc=None, auto_run=True, show_dialog=True):
    """
    Führt die komplette Stabilitätskette aus.

    REIHENFOLGE (kritisch!):
      1. CalculateLoadCondition.recalculate_current()  → D4/E5/F5/G5/H4
      2. doc.recompute()
      3. SinkAndTrim.compute()                         → E4/F4/G4/H5/D6
    """
    if doc is None:
        doc = App.activeDocument()
        if doc is None:
            return False, "Kein aktives Dokument", None

    results_log   = []
    hydro_results = None

    # ── SCHRITT 1: LoadCondition Summen / COG / FSM ───────────────────────
    App.Console.PrintMessage("\n--- Schritt 1: CalculateLoadCondition ---\n")
    try:
        calc_class = _import_calculate_loadcondition()
        if calc_class:
            calc = calc_class()
            calc.recalculate_current()
            results_log.append("✓ LoadCondition neu berechnet (Summen/COG/FSM)")

            # Spreadsheet-Formeln propagieren BEVOR SinkAndTrim liest
            doc.recompute()
            App.Console.PrintMessage("  ✓ doc.recompute() nach CalculateLoadCondition\n")
        else:
            results_log.append("⚠ CalculateLoadCondition nicht verfügbar")

    except Exception as e:
        msg = f"⚠ LoadCondition-Berechnung fehlgeschlagen: {str(e)}"
        results_log.append(msg)
        App.Console.PrintWarning(msg + "\n")
        traceback.print_exc()
        if not auto_run:
            return False, "\n".join(results_log), None

    # ── SCHRITT 2: SinkAndTrim – liest jetzt aktualisierte Werte ─────────
    App.Console.PrintMessage("\n--- Schritt 2: SinkAndTrim ---\n")
    try:
        compute_func = _import_sink_and_trim()
        if not compute_func:
            raise ImportError("shipSinkAndTrim.Tools.compute nicht gefunden")

        lc = find_loadcondition(doc)
        if not lc:
            raise ValueError("Kein LoadCondition-Spreadsheet gefunden")

        ship_obj = _find_ship_object(doc)
        if not ship_obj:
            raise ValueError("Kein Schiffsobjekt gefunden")

        # Kontrollausgabe was SinkAndTrim jetzt liest
        App.Console.PrintMessage(
            "  SinkAndTrim liest jetzt:\n"
            f"    D4 (Masse) = {_safe_lc_get(lc, 'D4')} kg\n"
            f"    G5 (KG)    = {_safe_lc_get(lc, 'G5')} m\n"
            f"    H4 (FSM)   = {_safe_lc_get(lc, 'H4')} t·m²\n")

        result_tuple = compute_func(lc, fs_ref=True, ship_obj=ship_obj, doc=doc)

        if result_tuple and len(result_tuple) >= 6:
            hydro_results = _parse_hydro_results(result_tuple)
            _format_hydro_log(results_log, hydro_results)
        else:
            results_log.append("⚠ SinkAndTrim lieferte keine Ergebnisse")

    except Exception as e:
        msg = f"⚠ SinkAndTrim fehlgeschlagen: {str(e)}"
        results_log.append(msg)
        App.Console.PrintWarning(msg + "\n")
        traceback.print_exc()

    final_msg = "\n".join(results_log)
    if show_dialog and Gui.getMainWindow():
        _show_stability_results_dialog(results_log, hydro_results)

    success = any("✓" in line for line in results_log)
    return success, final_msg, hydro_results


def _safe_lc_get(lc, cell):
    try:
        return str(lc.get(cell))
    except Exception:
        return "?"


def _import_calculate_loadcondition():
    """Versucht CalculateLoadCondition-Klasse zu importieren."""
    import_paths = [
        'freecad.ship.shipCreateLoadCondition.CalculateLoadCondition',
        'ship.shipCreateLoadCondition.CalculateLoadCondition',
        'shipCreateLoadCondition.CalculateLoadCondition',
        'CalculateLoadCondition',
    ]
    for path in import_paths:
        try:
            module = __import__(path, fromlist=['CalculateLoadCondition'])
            cls = getattr(module, 'CalculateLoadCondition', None)
            if cls:
                App.Console.PrintMessage(
                    f"  CalculateLoadCondition importiert von: {path}\n")
                return cls
        except ImportError:
            continue
    App.Console.PrintWarning("  CalculateLoadCondition nicht importierbar!\n")
    return None


def _import_sink_and_trim():
    """Versucht compute-Funktion aus SinkAndTrim zu importieren."""
    import_paths = [
        'freecad.ship.shipSinkAndTrim.Tools',
        'ship.shipSinkAndTrim.Tools',
        'shipSinkAndTrim.Tools',
    ]
    for path in import_paths:
        try:
            module = __import__(path, fromlist=['compute'])
            func = getattr(module, 'compute', None)
            if func:
                App.Console.PrintMessage(
                    f"  SinkAndTrim importiert von: {path}\n")
                return func
        except ImportError:
            continue
    App.Console.PrintWarning("  SinkAndTrim.compute nicht importierbar!\n")
    return None


def _find_ship_object(doc):
    """Findet das Schiffsobjekt im Dokument."""
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


def _parse_hydro_results(result_tuple):
    """Extrahiert hydrostatische Ergebnisse aus dem Result-Tuple."""
    group, draft, trim, displacement, vis_objects, result_dict = result_tuple[:6]

    # ── Tiefgang: Einheit sicherstellen ──────────────────────────────────
    # FreeCAD-intern ist draft eine Units.Quantity in mm.
    # Falls als reiner Float übergeben: Wert > 100 → sicher mm → /1000
    draft_m = None
    if hasattr(draft, 'getValueAs'):
        draft_m = float(draft.getValueAs('m'))
    elif hasattr(draft, 'Value'):
        raw = draft.Value
        draft_m = raw / 1000.0 if raw > 100 else raw
    elif draft is not None:
        raw = float(draft)
        draft_m = raw / 1000.0 if raw > 100 else raw

    return {
        'draft':        draft_m,
        'trim':         trim,
        'displacement': displacement,
        'gm':    result_dict.get('gm')   if isinstance(result_dict, dict) else None,
        'kmt':   result_dict.get('kmt')  if isinstance(result_dict, dict) else None,
        'lcb':   result_dict.get('lcb')  if isinstance(result_dict, dict) else None,
        'trim_cm': result_dict.get('trim_cm') if isinstance(result_dict, dict) else None,
    }


def _format_hydro_log(results_log, hydro_results):
    """Formatiert Hydrostatik-Ergebnisse für das Log."""
    draft = hydro_results.get('draft')
    trim  = hydro_results.get('trim')

    draft_str = f"{draft:.3f} m" if draft is not None else "?"
    if trim is not None:
        trim_val  = trim.Value if hasattr(trim, 'Value') else float(trim)
        trim_str  = f"{trim_val:.2f}°"
    else:
        trim_str = "?"

    results_log.append("✓ Hydrostatische Equilibrium-Berechnung durchgeführt")
    results_log.append(f"  - Draft: {draft_str}")
    results_log.append(f"  - Trim:  {trim_str}")

    gm = hydro_results.get('gm')
    if gm is not None:
        gm_val = gm.Value if hasattr(gm, 'Value') else float(gm)
        results_log.append(f"  - GMt:  {gm_val:.3f} m")

        if gm_val > 0.5:
            results_log.append("  - Stabilität: ✓ GUT")
        elif gm_val > 0.15:
            results_log.append("  - Stabilität: ⚠ AKZEPTABEL")
        elif gm_val > 0:
            results_log.append("  - Stabilität: ⚠ KRITISCH")
        else:
            results_log.append("  - Stabilität: ✗ INSTABIL!")


# =============================================================================
# HAUPT-TRANSFER-FUNKTION
# =============================================================================

def transfer_crane_data_and_calculate(crane_data, doc=None,
                                       auto_calculate=True,
                                       show_confirmation=True):
    """
    Schreibt Kran-Daten und führt die komplette Stabilitätskette aus.

    REIHENFOLGE:
      1. Krangewichte ins Sheet schreiben
      2. doc.recompute()
      3. CalculateLoadCondition  → neue Summen/COG/FSM
      4. doc.recompute()         (intern in run_stability_chain)
      5. SinkAndTrim             → korrekter Tiefgang/GM

    Returns: (success, message, hydro_results)
    """
    if doc is None:
        doc = App.activeDocument()
        if doc is None:
            return False, "Kein aktives Dokument!", None

    # Schritt 1: Krangewichte schreiben
    lc = find_loadcondition(doc)
    if not lc:
        return False, "Kein LoadCondition-Spreadsheet gefunden", None

    success = write_crane_to_loadcondition(lc, crane_data, reset_existing=True)
    if not success:
        return False, "Kran-Daten konnten nicht geschrieben werden", None

    # Schritt 2: Spreadsheet propagieren BEVOR CalculateLoadCondition läuft
    doc.recompute()
    App.Console.PrintMessage("  ✓ doc.recompute() nach Kran-Daten\n")

    if not auto_calculate:
        return True, "Kran-Daten übertragen (Berechnung ausgelassen)", None

    # Schritte 3-5: CalculateLoadCondition → recompute → SinkAndTrim
    success_chain, msg_chain, hydro = run_stability_chain_after_crane(
        doc=doc,
        auto_run=True,
        show_dialog=show_confirmation
    )

    full_msg = f"✓ Kran-Daten übertragen\n\n{msg_chain}"
    return success_chain, full_msg, hydro


# ALIAS für interne Konsistenz
write_crane_and_calculate = transfer_crane_data_and_calculate


# =============================================================================
# DIALOG
# =============================================================================

def _show_stability_results_dialog(log_lines, hydro_results):
    """Zeigt die Ergebnisse der Stabilitätskette in einem Dialog."""
    try:
        dialog = QtGui.QDialog(Gui.getMainWindow())
        dialog.setWindowTitle("Stability Calculation Results")
        dialog.setMinimumWidth(450)
        dialog.setMinimumHeight(400)

        layout = QtGui.QVBoxLayout()

        title = QtGui.QLabel("⚓ Stabilitätsberechnung Abgeschlossen")
        title.setStyleSheet(
            "font-size: 14px; font-weight: bold; color: #003366;")
        title.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(title)
        layout.addSpacing(10)

        results_text = QtGui.QTextEdit()
        results_text.setReadOnly(True)
        results_text.setStyleSheet("""
            background-color: #f8f8f8;
            border: 1px solid #cccccc;
            padding: 8px;
            font-family: monospace;
            font-size: 11px;
        """)
        results_text.setText(_format_dialog_text(log_lines, hydro_results))
        layout.addWidget(results_text)

        btn_layout = QtGui.QHBoxLayout()
        close_btn  = QtGui.QPushButton("Schließen")
        close_btn.clicked.connect(dialog.accept)
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

        dialog.setLayout(layout)
        dialog.exec_()

    except Exception as e:
        App.Console.PrintError(f"Fehler beim Anzeigen des Dialogs: {e}\n")


def _format_dialog_text(log_lines, hydro_results):
    text = "\n".join(log_lines)

    if hydro_results and hydro_results.get('draft') is not None:
        text += "\n\n" + "="*50 + "\n"
        text += "DETAILLIERTE HYDROSTATISCHE DATEN\n"
        text += "="*50 + "\n"

        draft = hydro_results['draft']
        text += f"Mittlerer Tiefgang: {draft:.3f} m\n"

        trim = hydro_results.get('trim')
        if trim is not None:
            tv = trim.Value if hasattr(trim, 'Value') else float(trim)
            text += f"Trim:               {tv:.2f}°\n"

        disp = hydro_results.get('displacement')
        if disp is not None:
            dv = disp.Value if hasattr(disp, 'Value') else float(disp)
            text += f"Verdrängung:        {dv/1000:.1f} t\n"

        lcb = hydro_results.get('lcb')
        if lcb is not None:
            lv = lcb.Value if hasattr(lcb, 'Value') else float(lcb)
            text += f"LCB:                {lv:.3f} m\n"

        kmt = hydro_results.get('kmt')
        if kmt is not None:
            kv = kmt.Value if hasattr(kmt, 'Value') else float(kmt)
            text += f"KMt:                {kv:.3f} m\n"

        gm = hydro_results.get('gm')
        if gm is not None:
            gv = gm.Value if hasattr(gm, 'Value') else float(gm)
            text += f"\nGMt:                {gv:.3f} m\n"
            if gv > 0.5:
                text += "Stabilität:         ✓ GUT (GM > 0.5m)\n"
            elif gv > 0.15:
                text += "Stabilität:         ⚠ AKZEPTABEL\n"
            elif gv > 0:
                text += "Stabilität:         ⚠ KRITISCH\n"
            else:
                text += "Stabilität:         ✗ INSTABIL!\n"

    return text


__all__ = [
    'find_loadcondition',
    'get_crane_positions',
    'write_crane_to_loadcondition',
    'transfer_crane_data_and_calculate',
    'write_crane_and_calculate',
    'run_stability_chain_after_crane',
]
