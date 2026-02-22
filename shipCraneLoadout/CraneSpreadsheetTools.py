# -*- coding: utf-8 -*-
"""
CraneSpreadsheetTools.py
Gemeinsame Hilfsfunktionen für den Export von Krandaten
in das LoadCondition-Spreadsheet.
Wird verwendet von MonopileSwing.py und TaskLiftOperation.py
Erweitert um automatische Stabilitätsberechnung.
"""
import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtGui, QtCore
import traceback


# =============================================================================
# ORIGINALE FUNKTIONEN (unverändert)
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

    # Nichts gefunden – Debug-Ausgabe
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
    Gibt Boom-CG und Sheave-Position in Metern zurück.
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
    else:
        hook = boom

    return boom, hook


def _safe_get(lc, cell):
    """
    Liest eine Zelle sicher aus dem Spreadsheet.
    Gibt leeren String zurück wenn die Zelle leer ist oder nicht existiert.
    FreeCAD wirft bei leeren Zellen eine Exception – das fangen wir hier ab.
    """
    try:
        val = lc.get(cell)
        return str(val).strip() if val is not None else ""
    except Exception:
        return ""


def _reset_all_hook_loads_in_spreadsheet(lc):
    """
    Setzt NUR die Haken-Lasten (Last am Haken) in der CRANES-Sektion auf Null.
    Das Boom-Gewicht (Kranbaum) bleibt erhalten!
    
    WICHTIG: Muss vor dem Schreiben neuer Kran-Daten aufgerufen werden,
    damit alte Haken-Lasten nicht erhalten bleiben!
    """
    in_cranes = False
    empty_streak = 0
    MAX_EMPTY = 20
    reset_count = 0

    App.Console.PrintMessage("  _reset_all_hook_loads: Setze Haken-Lasten auf Null...\n")

    for row in range(1, 300):
        a = _safe_get(lc, f'A{row}')
        b = _safe_get(lc, f'B{row}')

        # Leerzeilen-Handling
        if a == "" and b == "":
            empty_streak += 1
            if empty_streak >= MAX_EMPTY:
                break
            continue
        else:
            empty_streak = 0

        # CRANES-Sektion gefunden
        if a == "CRANES":
            in_cranes = True
            continue

        # Ende der CRANES-Sektion
        if in_cranes and a in ("TANKS", "WEIGHTS", "CARGO", "END"):
            if reset_count > 0:
                App.Console.PrintMessage(f"    {reset_count} Haken-Lasten zurückgesetzt\n")
            break

        if not in_cranes:
            continue

        # NUR "Last am Haken" zurücksetzen, NICHT "Kranbaum"!
        if b == "Last am Haken":
            try:
                lc.set(f'D{row}', "0.0")  # Gewicht = 0
                lc.set(f'K{row}', "")     # Kommentar löschen
                reset_count += 1
                App.Console.PrintMessage(f"    Zeile {row}: {a!r} Haken-Last → 0 kg\n")
            except Exception as e:
                App.Console.PrintWarning(f"    Zeile {row}: Reset fehlgeschlagen: {e}\n")

    return reset_count > 0


def write_crane_to_loadcondition(lc, crane_data, reset_existing=True):
    """
    Sucht die CRANES-Sektion im Spreadsheet und aktualisiert
    die Kranbaum- und Hakenzeilen.

    WICHTIG: Setzt vorher alle Haken-Lasten auf Null (aber nicht das Boom-Gewicht!),
    damit alte Lasten nicht erhalten bleiben!

    crane_data = {
        'KranLabel': {
            'boom_kg':  float,
            'hook_kg':  float,   # 0 bei Counterweight
            'boom_pos': (lcg, tcg, vcg),  # Meter
            'hook_pos': (lcg, tcg, vcg),
        }, ...
    }

    Args:
        lc: LoadCondition Spreadsheet
        crane_data: Dict mit Kran-Daten
        reset_existing: True = vorher alle Haken-Lasten auf Null setzen (Standard)

    Returns: True wenn mindestens eine Zeile aktualisiert wurde.
    """
    # WICHTIG: Zuerst alle alten Haken-Lasten löschen (Boom bleibt erhalten!)
    if reset_existing:
        _reset_all_hook_loads_in_spreadsheet(lc)
    
    updated      = 0
    in_cranes    = False
    empty_streak = 0
    MAX_EMPTY    = 20   # Erst nach 20 leeren Zeilen IN FOLGE wirklich abbrechen

    App.Console.PrintMessage(
        f"  write_crane_to_loadcondition: Suche CRANES-Sektion...\n"
        f"  Erwartete Kran-Labels: {list(crane_data.keys())}\n")

    for row in range(1, 300):
        a = _safe_get(lc, f'A{row}')
        b = _safe_get(lc, f'B{row}')

        # ── Leerzeile: Zähler erhöhen, aber NICHT abbrechen ──────────────────
        # (Zwischen den Sektionen gibt es absichtliche Leerzeilen!)
        if a == "" and b == "":
            empty_streak += 1
            if empty_streak >= MAX_EMPTY:
                App.Console.PrintMessage(
                    f"    Zeile {row}: {MAX_EMPTY} leere Zeilen in Folge → Ende\n")
                break
            continue
        else:
            empty_streak = 0  # Streak zurücksetzen sobald Inhalt kommt

        # ── CRANES-Sektion gefunden ───────────────────────────────────────────
        if a == "CRANES":
            in_cranes = True
            App.Console.PrintMessage(f"    Zeile {row}: CRANES-Sektion gefunden ✓\n")
            continue

        # ── Nächste Haupt-Sektion = Ende von CRANES ──────────────────────────
        if in_cranes and a in ("TANKS", "WEIGHTS", "CARGO", "END"):
            App.Console.PrintMessage(
                f"    Zeile {row}: Ende CRANES-Sektion ({a!r})\n")
            break

        if not in_cranes:
            continue

        # ── Kran-Zeile updaten ────────────────────────────────────────────────
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
                f" {data['boom_pos'][1]:.2f}, "
                f" {data['boom_pos'][2]:.2f}) m\n")
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
                f" {data['hook_pos'][1]:.2f}, "
                f" {data['hook_pos'][2]:.2f}) m\n")
            updated += 1

    # ── Abschluss-Diagnose ────────────────────────────────────────────────────
    if updated == 0:
        App.Console.PrintWarning(
            "  ⚠ Keine Zeilen aktualisiert!\n"
            "  Mögliche Ursachen:\n"
            "    1. CRANES-Sektion nicht gefunden\n"
            "       → Spreadsheet neu erstellen (LoadCondition Tools)\n"
            "    2. Kran-Label im Sheet stimmt nicht mit crane_data überein\n"
            f"       crane_data-Keys: {list(crane_data.keys())}\n"
            "    3. Spaltenbeschriftungen 'Kranbaum' / 'Last am Haken' fehlen\n")
    else:
        App.Console.PrintMessage(
            f"  ✓ {updated} Zeile(n) aktualisiert\n")

    return updated > 0


# =============================================================================
# NEU: AUTOMATISCHE STABILITÄTSKETTE
# =============================================================================

def run_stability_chain_after_crane(doc=None, auto_run=True, show_dialog=True):
    """
    Führt nach Kran-Transfer die komplette Stabilitätskette aus:
    1. LoadCondition Recalculation (Summen/COG/FSM)
    2. ShipSinkAndTrim Hydrostatik (Equilibrium)
    
    Args:
        doc: Aktives Dokument (None = App.activeDocument())
        auto_run: True = ohne Nachfrage ausführen
        show_dialog: True = Ergebnisse in Dialog anzeigen
    
    Returns:
        (success: bool, message: str, results: dict)
    """
    if doc is None:
        doc = App.activeDocument()
        if doc is None:
            return False, "Kein aktives Dokument", None
    
    results_log = []
    hydro_results = None
    
    # -------------------------------------------------------------------------
    # SCHRITT 1: LoadCondition Recalculation
    # -------------------------------------------------------------------------
    try:
        calc_module = _import_calculate_loadcondition()
        if calc_module:
            calc = calc_module()
            calc.recalculate_current()
            results_log.append("✓ LoadCondition neu berechnet (Summen/COG/FSM)")
        else:
            results_log.append("⚠ CalculateLoadCondition nicht verfügbar")
            
    except Exception as e:
        msg = f"⚠ LoadCondition-Berechnung fehlgeschlagen: {str(e)}"
        results_log.append(msg)
        App.Console.PrintWarning(msg + "\n")
        if not auto_run:
            return False, "\n".join(results_log), None
    
    # -------------------------------------------------------------------------
    # SCHRITT 2: ShipSinkAndTrim Hydrostatik
    # -------------------------------------------------------------------------
    try:
        compute_func = _import_sink_and_trim()
        if not compute_func:
            raise ImportError("shipSinkAndTrim.Tools.compute nicht gefunden")
        
        # Finde LoadCondition
        lc = find_loadcondition(doc)
        if not lc:
            raise ValueError("Kein LoadCondition-Spreadsheet gefunden")
        
        # Finde Schiff
        ship_obj = _find_ship_object(doc)
        if not ship_obj:
            raise ValueError("Kein Schiffsobjekt gefunden")
        
        # Führe Hydrostatik-Berechnung durch
        result_tuple = compute_func(lc, fs_ref=True, ship_obj=ship_obj, doc=doc)
        
        if result_tuple and len(result_tuple) >= 6:
            hydro_results = _parse_hydro_results(result_tuple)
            _format_hydro_log(results_log, hydro_results)
        else:
            results_log.append("⚠ Hydrostatik-Berechnung lieferte keine Ergebnisse")
            
    except Exception as e:
        msg = f"⚠ Hydrostatik-Berechnung fehlgeschlagen: {str(e)}"
        results_log.append(msg)
        App.Console.PrintWarning(msg + "\n")
        traceback.print_exc()
    
    # -------------------------------------------------------------------------
    # ERGEBNIS ANZEIGEN
    # -------------------------------------------------------------------------
    final_msg = "\n".join(results_log)
    
    if show_dialog and Gui.getMainWindow():
        _show_stability_results_dialog(results_log, hydro_results)
    
    success = any("✓" in line for line in results_log)
    return success, final_msg, hydro_results


def _import_calculate_loadcondition():
    """Versucht CalculateLoadCondition aus verschiedenen Pfaden zu importieren."""
    import_paths = [
        'shipCreateLoadCondition.CalculateLoadCondition',
        'CalculateLoadCondition',
        'freecad.ship.shipCreateLoadCondition.CalculateLoadCondition'
    ]
    
    for path in import_paths:
        try:
            module = __import__(path, fromlist=['CalculateLoadCondition'])
            return getattr(module, 'CalculateLoadCondition', None)
        except ImportError:
            continue
    return None


def _import_sink_and_trim():
    """Versucht compute-Funktion aus verschiedenen Pfaden zu importieren."""
    import_paths = [
        'freecad.ship.shipSinkAndTrim.Tools',
        'ship.shipSinkAndTrim.Tools',
        'shipSinkAndTrim.Tools'
    ]
    
    for path in import_paths:
        try:
            module = __import__(path, fromlist=['compute'])
            return getattr(module, 'compute', None)
        except ImportError:
            continue
    return None


def _find_ship_object(doc):
    """Findet das Schiffsobjekt im Dokument."""
    # Priorität 1: Explizites Ship-Objekt
    for obj in doc.Objects:
        if 'Ship' in obj.Label and hasattr(obj, 'Shape'):
            return obj
    
    # Priorität 2: Schiffsähnliche Geometrie (Länge > 2*Breite, Länge > 1000mm)
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
    
    return {
        'draft': draft,
        'trim': trim,
        'displacement': displacement,
        'gm': result_dict.get('gm') if isinstance(result_dict, dict) else None,
        'kmt': result_dict.get('kmt') if isinstance(result_dict, dict) else None,
        'lcb': result_dict.get('lcb') if isinstance(result_dict, dict) else None,
        'trim_cm': result_dict.get('trim_cm') if isinstance(result_dict, dict) else None,
    }


def _format_hydro_log(results_log, hydro_results):
    """Formatiert Hydrostatik-Ergebnisse für das Log."""
    draft = hydro_results['draft']
    trim = hydro_results['trim']
    
    draft_str = f"{draft.Value:.3f} m" if hasattr(draft, 'Value') else f"{draft:.3f} m"
    trim_str = f"{trim.Value:.2f}°" if hasattr(trim, 'Value') else f"{trim:.2f}°"
    
    results_log.append("✓ Hydrostatische Equilibrium-Berechnung durchgeführt")
    results_log.append(f"  - Draft: {draft_str}")
    results_log.append(f"  - Trim: {trim_str}")
    
    if hydro_results['gm']:
        gm_val = hydro_results['gm'].Value if hasattr(hydro_results['gm'], 'Value') else hydro_results['gm']
        results_log.append(f"  - GMt: {gm_val:.3f} m")
        
        # Stabilitätsbewertung
        if gm_val > 0.5:
            results_log.append("  - Stabilität: ✓ GUT")
        elif gm_val > 0.15:
            results_log.append("  - Stabilität: ⚠ AKZEPTABEL")
        elif gm_val > 0:
            results_log.append("  - Stabilität: ⚠ KRITISCH")
        else:
            results_log.append("  - Stabilität: ✗ INSTABIL!")


def _show_stability_results_dialog(log_lines, hydro_results):
    """Zeigt die Ergebnisse der Stabilitätskette in einem Dialog an."""
    try:
        dialog = QtGui.QDialog(Gui.getMainWindow())
        dialog.setWindowTitle("Stability Calculation Results")
        dialog.setMinimumWidth(450)
        dialog.setMinimumHeight(400)
        
        layout = QtGui.QVBoxLayout()
        
        # Titel
        title = QtGui.QLabel("⚓ Stabilitätsberechnung Abgeschlossen")
        title.setStyleSheet("font-size: 14px; font-weight: bold; color: #003366;")
        title.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(title)
        layout.addSpacing(10)
        
        # Ergebnis-Text
        results_text = QtGui.QTextEdit()
        results_text.setReadOnly(True)
        results_text.setStyleSheet("""
            background-color: #f8f8f8;
            border: 1px solid #cccccc;
            padding: 8px;
            font-family: monospace;
            font-size: 11px;
        """)
        
        text = _format_dialog_text(log_lines, hydro_results)
        results_text.setText(text)
        layout.addWidget(results_text)
        
        # Buttons
        btn_layout = QtGui.QHBoxLayout()
        
        details_btn = QtGui.QPushButton("Details im TaskPanel öffnen")
        details_btn.clicked.connect(lambda: _open_sink_and_trim_taskpanel())
        details_btn.clicked.connect(dialog.accept)
        btn_layout.addWidget(details_btn)
        
        btn_layout.addStretch()
        
        close_btn = QtGui.QPushButton("Schließen")
        close_btn.clicked.connect(dialog.accept)
        btn_layout.addWidget(close_btn)
        
        layout.addLayout(btn_layout)
        dialog.setLayout(layout)
        dialog.exec_()
        
    except Exception as e:
        App.Console.PrintError(f"Fehler beim Anzeigen des Dialogs: {e}\n")


def _format_dialog_text(log_lines, hydro_results):
    """Formatiert den Text für den Ergebnis-Dialog."""
    text = "\n".join(log_lines)
    
    if hydro_results and hydro_results.get('draft'):
        text += "\n\n" + "="*50 + "\n"
        text += "DETAILLIERTE HYDROSTATISCHE DATEN\n"
        text += "="*50 + "\n"
        
        draft = hydro_results['draft']
        trim = hydro_results['trim']
        disp = hydro_results['displacement']
        
        draft_val = draft.Value if hasattr(draft, 'Value') else draft
        trim_val = trim.Value if hasattr(trim, 'Value') else trim
        disp_val = disp.Value if hasattr(disp, 'Value') else disp
        
        text += f"Verdrängung:      {disp_val/1000:.1f} t\n"
        text += f"Mittlerer Tiefgang: {draft_val:.3f} m\n"
        text += f"Trim:             {trim_val:.2f}°\n"
        
        if hydro_results.get('lcb'):
            lcb_val = hydro_results['lcb'].Value if hasattr(hydro_results['lcb'], 'Value') else hydro_results['lcb']
            text += f"LCB:              {lcb_val:.3f} m\n"
        
        if hydro_results.get('kmt'):
            kmt_val = hydro_results['kmt'].Value if hasattr(hydro_results['kmt'], 'Value') else hydro_results['kmt']
            text += f"KMt:              {kmt_val:.3f} m\n"
        
        if hydro_results.get('gm'):
            gm_val = hydro_results['gm'].Value if hasattr(hydro_results['gm'], 'Value') else hydro_results['gm']
            text += f"\nGMt:              {gm_val:.3f} m\n"
            
            if gm_val > 0.5:
                text += "Stabilität:       ✓ GUT (GM > 0.5m)\n"
            elif gm_val > 0.15:
                text += "Stabilität:       ⚠ AKZEPTABEL (0.15m < GM < 0.5m)\n"
            elif gm_val > 0:
                text += "Stabilität:       ⚠ KRITISCH (GM < 0.15m)\n"
            else:
                text += "Stabilität:       ✗ INSTABIL (Negatives GM!)\n"
        
        if hydro_results.get('trim_cm'):
            text += f"\nTrimmoment:       {hydro_results['trim_cm']:.1f} t·m/cm\n"
    
    return text


def _open_sink_and_trim_taskpanel():
    """Öffnet das vollständige ShipSinkAndTrim TaskPanel für detaillierte Analyse."""
    try:
        import_paths = [
            'freecad.ship.shipSinkAndTrim.TaskPanel',
            'ship.shipSinkAndTrim.TaskPanel',
            'shipSinkAndTrim.TaskPanel'
        ]
        
        for path in import_paths:
            try:
                module = __import__(path, fromlist=['TaskPanel'])
                panel_class = getattr(module, 'TaskPanel', None)
                if panel_class:
                    panel = panel_class.createTask() if hasattr(panel_class, 'createTask') else panel_class()
                    if panel:
                        Gui.Control.showDialog(panel)
                        return
            except ImportError:
                continue
                
        QtGui.QMessageBox.warning(None, "Fehler", "TaskPanel-Modul nicht gefunden")
        
    except Exception as e:
        QtGui.QMessageBox.warning(None, "Fehler", f"Konnte TaskPanel nicht öffnen:\n{str(e)}")


# =============================================================================
# NEU: KOMPATIBLE TRANSFER-FUNKTION FÜR TANDEMLIFT.PY
# =============================================================================

def transfer_crane_data_and_calculate(crane_data, doc=None, 
                                       auto_calculate=True, 
                                       show_confirmation=True):
    """
    Schreibt Kran-Daten und führt optional die komplette Stabilitätskette aus.
    Kompatibel mit TandemLift.py - erwartet crane_data als ersten Parameter!
    
    WICHTIG: Setzt vorher alle Haken-Lasten auf Null (Boom-Gewicht bleibt!),
    damit alte Lasten nicht erhalten bleiben!
    
    Args:
        crane_data: Dict mit Kran-Daten
        doc: FreeCAD Dokument (None = App.activeDocument())
        auto_calculate: True = sofortige Berechnung nach Schreiben
        show_confirmation: True = Ergebnis-Dialog anzeigen (für Kompatibilität)
    
    Returns:
        (success: bool, message: str, hydro_results: dict)
    """
    if doc is None:
        doc = App.activeDocument()
        if doc is None:
            return False, "Kein aktives Dokument!", None
    
    # Finde LoadCondition
    lc = find_loadcondition(doc)
    if not lc:
        return False, "Kein LoadCondition-Spreadsheet gefunden", None
    
    # Schritt 1: Kran-Daten schreiben (mit Reset der Haken-Lasten, Boom bleibt!)
    success = write_crane_to_loadcondition(lc, crane_data, reset_existing=True)
    
    if not success:
        return False, "Kran-Daten konnten nicht ins Spreadsheet geschrieben werden", None
    
    if not auto_calculate:
        return True, "Kran-Daten übertragen (Berechnung ausgelassen)", None
    
    # Schritt 2 & 3: Automatische Berechnung
    success_chain, msg_chain, hydro = run_stability_chain_after_crane(
        doc=doc, 
        auto_run=True, 
        show_dialog=show_confirmation
    )
    
    full_msg = f"✓ Kran-Daten übertragen (alte Haken-Lasten gelöscht, Boom bleibt)\n\n{msg_chain}"
    return success_chain, full_msg, hydro


# ALIAS für interne Konsistenz
write_crane_and_calculate = transfer_crane_data_and_calculate


__all__ = [
    'find_loadcondition', 
    'get_crane_positions', 
    'write_crane_to_loadcondition',
    'transfer_crane_data_and_calculate',
    'write_crane_and_calculate',  # ALIAS
    'run_stability_chain_after_crane',
]
