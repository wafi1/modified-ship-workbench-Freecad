# -*- coding: utf-8 -*-
"""
CraneSpreadsheetTools.py
Gemeinsame Hilfsfunktionen für den Export von Krandaten
in das LoadCondition-Spreadsheet.
Wird verwendet von MonopileSwing.py und TaskLiftOperation.py

STABILITÄTSKETTE (vollständig in CalculateLoadCondition.recalculate_current):
  1. write_crane_to_loadcondition()   → Krangewichte ins Sheet
  2. doc.recompute()
  3. CalculateLoadCondition.recalculate_current()
       → intern: Masse/COG/FSM berechnen
       → intern: doc.recompute()
       → intern: SinkAndTrim (Tiefgang/KM/GM)
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
    SheavePosition = Umlenkrolle an der Auslegerspitze = korrekter
    Angriffspunkt für frei hängende Lasten (Pendeleffekt).

    Returns: (boom_pos, hook_pos) jeweils als (lcg, tcg, vcg) in Metern
    """
    if hasattr(crane, 'BoomCGPosition'):
        bg   = crane.BoomCGPosition
        boom = (bg.x / 1000.0, bg.y / 1000.0, bg.z / 1000.0)
    else:
        p    = crane.Placement.Base
        boom = (p.x / 1000.0, p.y / 1000.0, p.z / 1000.0)

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

    App.Console.PrintMessage(
        "  _reset_all_hook_loads: Setze Haken-Lasten auf Null...\n")

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
            App.Console.PrintMessage(
                f"    Zeile {row}: CRANES-Sektion gefunden ✓\n")
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
# STABILITÄTSKETTE – vereinfacht
# =============================================================================

def run_stability_chain_after_crane(doc=None, auto_run=True, show_dialog=True):
    """
    Führt die Stabilitätskette aus.

    Da CalculateLoadCondition.recalculate_current() intern bereits
    doc.recompute() + SinkAndTrim aufruft, reicht hier ein einziger Aufruf.
    """
    if doc is None:
        doc = App.activeDocument()
        if doc is None:
            return False, "Kein aktives Dokument", None

    results_log = []

    try:
        calc_class = _import_calculate_loadcondition()
        if not calc_class:
            raise ImportError("CalculateLoadCondition nicht importierbar")

        calc = calc_class()
        calc.recalculate_current()   # → intern: Summen + recompute + SinkAndTrim

        results_log.append("✓ LoadCondition neu berechnet")
        results_log.append("✓ SinkAndTrim durchgeführt (intern)")

    except Exception as e:
        msg = f"⚠ Stabilitätskette fehlgeschlagen: {str(e)}"
        results_log.append(msg)
        App.Console.PrintWarning(msg + "\n")
        traceback.print_exc()
        return False, "\n".join(results_log), None

    # Ergebnisse aus Spreadsheet lesen für Dialog/Rückgabe
    hydro_results = _read_hydro_from_sheet(doc)

    final_msg = "\n".join(results_log)
    if show_dialog and Gui.getMainWindow():
        _show_stability_results_dialog(results_log, hydro_results)

    return True, final_msg, hydro_results


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
            cls    = getattr(module, 'CalculateLoadCondition', None)
            if cls:
                return cls
        except ImportError:
            continue
    return None


def _read_hydro_from_sheet(doc):
    """
    Liest die von SinkAndTrim geschriebenen Werte aus dem Spreadsheet.
    E4=Draft, F4=KMt, G4=GMt, G5=KG, D4=Masse
    """
    lc = find_loadcondition(doc)
    if not lc:
        return None

    def sf(cell):
        try:
            return float(str(lc.get(cell)).strip())
        except Exception:
            return None

    draft_raw = sf('E4')
    draft_m   = None
    if draft_raw is not None:
        draft_m = draft_raw / 1000.0 if draft_raw > 100 else draft_raw

    return {
        'draft': draft_m,
        'kmt':   sf('F4'),
        'gm':    sf('G4'),
        'mass':  sf('D4'),
        'kg':    sf('G5'),
    }


# =============================================================================
# HAUPT-TRANSFER-FUNKTION
# =============================================================================

def transfer_crane_data_and_calculate(crane_data, doc=None,
                                       auto_calculate=True,
                                       show_confirmation=True):
    """
    Schreibt Kran-Daten und führt die Stabilitätskette aus.

    REIHENFOLGE:
      1. Krangewichte ins Sheet
      2. doc.recompute()
      3. CalculateLoadCondition.recalculate_current()
           → Masse/COG/FSM + recompute + SinkAndTrim

    Returns: (success, message, hydro_results)
    """
    if doc is None:
        doc = App.activeDocument()
        if doc is None:
            return False, "Kein aktives Dokument!", None

    lc = find_loadcondition(doc)
    if not lc:
        return False, "Kein LoadCondition-Spreadsheet gefunden", None

    # Schritt 1: Krangewichte schreiben
    success = write_crane_to_loadcondition(lc, crane_data, reset_existing=True)
    if not success:
        return False, "Kran-Daten konnten nicht geschrieben werden", None

    # Schritt 2: Propagieren bevor CalculateLoadCondition läuft
    doc.recompute()
    App.Console.PrintMessage("  ✓ doc.recompute() nach Kran-Daten\n")

    if not auto_calculate:
        return True, "Kran-Daten übertragen (Berechnung ausgelassen)", None

    # Schritt 3: Stabilitätskette (ein einziger Aufruf reicht jetzt!)
    success_chain, msg_chain, hydro = run_stability_chain_after_crane(
        doc=doc,
        auto_run=True,
        show_dialog=show_confirmation
    )

    full_msg = f"✓ Kran-Daten übertragen\n\n{msg_chain}"
    return success_chain, full_msg, hydro


# ALIAS
write_crane_and_calculate = transfer_crane_data_and_calculate


# =============================================================================
# ERGEBNIS-DIALOG
# =============================================================================

def _show_stability_results_dialog(log_lines, hydro_results):
    try:
        dialog = QtGui.QDialog(Gui.getMainWindow())
        dialog.setWindowTitle("Stability Calculation Results")
        dialog.setMinimumWidth(420)
        dialog.setMinimumHeight(320)

        layout = QtGui.QVBoxLayout()

        title = QtGui.QLabel("⚓ Stabilitätsberechnung Abgeschlossen")
        title.setStyleSheet(
            "font-size: 14px; font-weight: bold; color: #003366;")
        title.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(title)
        layout.addSpacing(8)

        text_edit = QtGui.QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet(
            "background:#f8f8f8; border:1px solid #ccc; "
            "padding:8px; font-family:monospace; font-size:11px;")
        text_edit.setText(_format_dialog_text(log_lines, hydro_results))
        layout.addWidget(text_edit)

        btn_row  = QtGui.QHBoxLayout()
        close_btn = QtGui.QPushButton("Schließen")
        close_btn.clicked.connect(dialog.accept)
        btn_row.addStretch()
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        dialog.setLayout(layout)
        dialog.exec_()

    except Exception as e:
        App.Console.PrintError(f"Dialog-Fehler: {e}\n")


def _format_dialog_text(log_lines, hydro_results):
    text = "\n".join(log_lines)

    if not hydro_results:
        return text

    text += "\n\n" + "="*45 + "\n"
    text += "HYDROSTATISCHE ERGEBNISSE\n"
    text += "="*45 + "\n"

    if hydro_results.get('mass') is not None:
        text += f"Masse    : {hydro_results['mass']:,.0f} kg\n"
    if hydro_results.get('draft') is not None:
        text += f"Tiefgang : {hydro_results['draft']:.3f} m\n"
    if hydro_results.get('kg') is not None:
        text += f"KG       : {hydro_results['kg']:.3f} m\n"
    if hydro_results.get('kmt') is not None:
        text += f"KMt      : {hydro_results['kmt']:.3f} m\n"

    gm = hydro_results.get('gm')
    if gm is not None:
        text += f"\nGMt      : {gm:.3f} m\n"
        if gm > 0.5:
            text += "Stabilität: ✓ GUT (GM > 0.5 m)\n"
        elif gm > 0.15:
            text += "Stabilität: ⚠ AKZEPTABEL\n"
        elif gm > 0:
            text += "Stabilität: ⚠ KRITISCH\n"
        else:
            text += "Stabilität: ✗ INSTABIL!\n"

    return text


__all__ = [
    'find_loadcondition',
    'get_crane_positions',
    'write_crane_to_loadcondition',
    'transfer_crane_data_and_calculate',
    'write_crane_and_calculate',
    'run_stability_chain_after_crane',
]
