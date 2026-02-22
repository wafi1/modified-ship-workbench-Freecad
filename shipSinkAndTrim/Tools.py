import math
import FreeCAD as App
from FreeCAD import Units


def extract_loadcondition_data(lc):
    """Extrahiert Daten aus LoadCondition Spreadsheet"""
    totals = {'mass': 0.0}
    cog = [0.0, 0.0, 0.0]
    
    try:
        mass_val = lc.get('D4')
        if mass_val:
            totals['mass'] = float(mass_val)
        
        x_val = lc.get('E5')
        y_val = lc.get('F5')
        z_val = lc.get('G5')
        
        if x_val: cog[0] = float(x_val)
        if y_val: cog[1] = float(y_val)
        if z_val: cog[2] = float(z_val)
            
    except Exception as e:
        App.Console.PrintWarning(f"Fehler beim Lesen LoadCondition: {e}\n")
    
    return totals, cog


def find_ship_object():
    """Findet Schiff-Objekt im Dokument"""
    doc = App.ActiveDocument
    if not doc:
        return None
    
    for obj in doc.Objects:
        if obj.Label == "Ship" or obj.Name == "Ship":
            return obj
    for obj in doc.Objects:
        if "Ship" in obj.Label or "ship" in obj.Label.lower():
            return obj
    for obj in doc.Objects:
        if hasattr(obj, 'Shape') and obj.Shape:
            bbox = obj.Shape.BoundBox
            if bbox.XLength > 1000 and bbox.YLength > 100:
                return obj
    return None


def load_hydrostatics_spreadsheet(doc):
    """
    Liest das bestehende Hydrostatics-Spreadsheet
    das vom shipHydrostatics-Modul erstellt wurde.
    
    Spalten laut Hydrostatik-Modul:
    A: Disp [t]
    B: Draft [m]
    C: Wet.Surface [m2]
    D: TMC [t*m/cm]
    E: FloatArea [m2]
    F: KBl [m]      (LCB)
    G: KBt [m]      (vertikaler Auftriebsschwerpunkt)
    H: BMt [m]
    I: Cb
    J: Cf
    K: Cm
    """
    # Suche Hydrostatics Spreadsheet
    hydro_sheet = None
    for obj in doc.Objects:
        if obj.TypeId == "Spreadsheet::Sheet":
            if obj.Label in ["Hydrostatics", "shipHydrostatics"] or \
               "Hydrostatic" in obj.Label:
                hydro_sheet = obj
                App.Console.PrintMessage(
                    f"Hydrostatics Spreadsheet gefunden: {obj.Label}\n")
                break
    
    if not hydro_sheet:
        App.Console.PrintError(
            "Kein Hydrostatics-Spreadsheet gefunden!\n"
            "Bitte zuerst das Hydrostatik-Modul ausfuehren.\n")
        return None
    
    # Daten einlesen - Header in Zeile 1, Daten ab Zeile 2
    points = []
    row = 2
    
    while True:
        try:
            # Erste Spalte pruefen ob Daten vorhanden
            val_a = hydro_sheet.get(f'A{row}')
            if not val_a or str(val_a).strip() == '':
                break
            
            # Alle Spalten lesen
            disp_t  = float(hydro_sheet.get(f'A{row}'))
            draft   = float(hydro_sheet.get(f'B{row}'))
            
            # Optionale Spalten mit Fallback
            def safe_float(cell, default=0.0):
                try:
                    v = hydro_sheet.get(cell)
                    return float(v) if v and str(v).strip() else default
                except:
                    return default
            
            wet     = safe_float(f'C{row}')
            tmc     = safe_float(f'D{row}')
            farea   = safe_float(f'E{row}')
            kbl     = safe_float(f'F{row}')  # LCB
            kbt     = safe_float(f'G{row}')  # KB transversal
            bmt     = safe_float(f'H{row}')  # BM transversal
            kmt     = kbt + bmt              # KM = KB + BM
            cb      = safe_float(f'I{row}')
            cf      = safe_float(f'J{row}')
            cm      = safe_float(f'K{row}')
            
            points.append({
                'disp_t': disp_t,
                'draft':  draft,
                'wet':    wet,
                'tmc':    tmc,
                'farea':  farea,
                'kbl':    kbl,
                'kbt':    kbt,
                'bmt':    bmt,
                'kmt':    kmt,
                'cb':     cb,
                'cf':     cf,
                'cm':     cm,
            })
            
            row += 1
            
        except Exception as e:
            App.Console.PrintWarning(f"  Zeile {row}: {e}\n")
            break
    
    App.Console.PrintMessage(f"  {len(points)} Hydrostatik-Punkte geladen\n")
    
    if len(points) < 2:
        App.Console.PrintError(
            "Zu wenige Punkte im Hydrostatics-Spreadsheet!\n")
        return None
    
    # Nach Tiefgang sortieren
    points.sort(key=lambda x: x['draft'])
    return points


def interpolate_hydrostatics(points, target_disp_t):
    """
    Interpoliert hydrostatische Werte fuer gegebene Verdrängung.
    Gibt dict mit interpolierten Werten zurueck.
    """
    if not points:
        return None
    
    # Ausserhalb des Bereichs: naechsten Punkt nehmen
    if target_disp_t <= points[0]['disp_t']:
        App.Console.PrintWarning(
            f"  Verdraengung {target_disp_t:.1f}t unter Minimum "
            f"{points[0]['disp_t']:.1f}t\n")
        return points[0].copy()
    
    if target_disp_t >= points[-1]['disp_t']:
        App.Console.PrintWarning(
            f"  Verdraengung {target_disp_t:.1f}t ueber Maximum "
            f"{points[-1]['disp_t']:.1f}t\n")
        return points[-1].copy()
    
    # Lineare Interpolation
    for i in range(len(points) - 1):
        p1 = points[i]
        p2 = points[i + 1]
        
        if p1['disp_t'] <= target_disp_t <= p2['disp_t']:
            f = ((target_disp_t - p1['disp_t']) / 
                 (p2['disp_t'] - p1['disp_t']))
            
            result = {}
            for key in p1:
                result[key] = p1[key] + f * (p2[key] - p1[key])
            
            App.Console.PrintMessage(
                f"  Interpoliert bei {target_disp_t:.1f}t: "
                f"Draft={result['draft']:.3f}m, "
                f"KMt={result['kmt']:.3f}m\n")
            return result
    
    return points[-1].copy()


def calculate_trim(delta_x_m, target_tmc, total_mass_t, L_m):
    """
    Berechnet Trimm aus LCG-LCB Differenz.
    delta_x_m: LCG - LCB in Metern
    """
    trim_moment_t_m = total_mass_t * delta_x_m
    
    if target_tmc > 0 and abs(trim_moment_t_m) > 0.01:
        trim_cm  = trim_moment_t_m / target_tmc
        trim_m   = trim_cm / 100.0
        trim_rad = math.atan2(trim_m, L_m) if L_m > 0 else 0.0
        trim_deg = math.degrees(trim_rad)
        trim_deg = max(-5.0, min(trim_deg, 5.0))
    else:
        trim_cm  = 0.0
        trim_deg = 0.0
    
    return trim_deg, trim_cm, trim_moment_t_m


def save_results_to_loadcondition(lc_sheet, result):
    """
    Speichert berechnete Werte zurueck ins LoadCondition-Spreadsheet:
    E4: Tiefgang [m]
    D6: Tiefgang [m]
    F4: KMt [m]
    G4: GMt korrigiert [m] = KMt - VCG - FSM-Hebel
    H5: FSM-Hebel [m]
    """
    try:
        App.Console.PrintMessage("\nSpeichere Ergebnisse in LoadCondition...\n")
        
        # Tiefgang
        lc_sheet.set('E4', f"{result['draft']:.4f}")
        lc_sheet.set('D6', f"{result['draft']:.4f}")
        App.Console.PrintMessage(f"  E4/D6: Draft = {result['draft']:.4f} m\n")
        
        # KMt
        lc_sheet.set('F4', f"{result['kmt']:.4f}")
        App.Console.PrintMessage(f"  F4: KMt = {result['kmt']:.4f} m\n")
        
        # FSM-Hebel berechnen und in H5 schreiben
        fsm_lever_m = 0.0
        try:
            d4_val = lc_sheet.get('D4')
            h4_val = lc_sheet.get('H4')
            
            if d4_val and h4_val:
                total_mass_kg = float(str(d4_val).replace(',', '.').strip())
                total_fsm_tm  = float(str(h4_val).replace(',', '.').strip())
                
                if total_fsm_tm > 0 and total_mass_kg > 0:
                    fsm_lever_m = total_fsm_tm / (total_mass_kg / 1000.0)
                
            lc_sheet.set('H5', f"{fsm_lever_m:.6f}")
            App.Console.PrintMessage(f"  H5: FSM-Hebel = {fsm_lever_m:.6f} m\n")
            
        except Exception as e:
            App.Console.PrintWarning(f"  H5 FSM-Hebel: {e}\n")
            lc_sheet.set('H5', "0.0")
        
        # GMt korrigiert = KMt - VCG - FSM-Hebel
        gm_corrected = result['kmt'] - result['vcg'] - fsm_lever_m
        lc_sheet.set('G4', f"{gm_corrected:.4f}")
        App.Console.PrintMessage(
            f"  G4: GMt_korr = {result['kmt']:.4f} - "
            f"{result['vcg']:.4f} - {fsm_lever_m:.6f} = "
            f"{gm_corrected:.4f} m\n")
        
        App.ActiveDocument.recompute()
        App.Console.PrintMessage("✓ Ergebnisse gespeichert\n")
        
    except Exception as e:
        App.Console.PrintError(f"Fehler beim Speichern: {e}\n")
        import traceback
        traceback.print_exc()


def compute(lc_spreadsheet, fs_ref=True, ship_obj=None, doc=None):
    """
    Hydrostatische Equilibrium-Berechnung.
    Liest Hydrostatik aus bestehendem Hydrostatics-Spreadsheet.
    """
    App.Console.PrintMessage("\n" + "="*60 + "\n")
    App.Console.PrintMessage("SinkAndTrim: Hydrostatische Berechnung\n")
    App.Console.PrintMessage("="*60 + "\n")
    
    try:
        if not doc:
            doc = App.ActiveDocument
        if not doc:
            App.Console.PrintError("Kein aktives Dokument!\n")
            return None, None, None, None, None, None
        
        if not ship_obj:
            ship_obj = find_ship_object()
        if not ship_obj:
            App.Console.PrintError("Kein Schiffsobjekt gefunden!\n")
            return None, None, None, None, None, None
        
        # Schiffsabmessungen
        bbox = ship_obj.Shape.BoundBox
        L_m  = bbox.XLength * 0.001
        B_m  = bbox.YLength * 0.001
        D_m  = bbox.ZLength * 0.001
        mid_fc = (bbox.XMin + bbox.XMax) / 2 * 0.001
        
        App.Console.PrintMessage(f"Schiff: {ship_obj.Label}\n")
        App.Console.PrintMessage(
            f"  L={L_m:.1f}m, B={B_m:.1f}m, D={D_m:.1f}m\n")
        
        # LoadCondition lesen
        totals, cog = extract_loadcondition_data(lc_spreadsheet)
        total_mass_kg = totals['mass']
        total_mass_t  = total_mass_kg / 1000.0
        
        if total_mass_kg <= 0:
            App.Console.PrintError("Kein gueltiges Gewicht in Zelle D4!\n")
            return None, None, None, None, None, None
        
        App.Console.PrintMessage(f"\nLadefall:\n")
        App.Console.PrintMessage(f"  Gewicht: {total_mass_t:.1f} t\n")
        App.Console.PrintMessage(f"  LCG: {cog[0]:.3f} m\n")
        App.Console.PrintMessage(f"  TCG: {cog[1]:.3f} m\n")
        App.Console.PrintMessage(f"  VCG: {cog[2]:.3f} m\n")
        
        # Hydrostatik-Tabelle laden
        App.Console.PrintMessage(f"\nLade Hydrostatik-Tabelle...\n")
        hydro_points = load_hydrostatics_spreadsheet(doc)
        
        if not hydro_points:
            return None, None, None, None, None, None
        
        App.Console.PrintMessage(
            f"  Bereich: {hydro_points[0]['disp_t']:.1f}t - "
            f"{hydro_points[-1]['disp_t']:.1f}t\n")
        App.Console.PrintMessage(
            f"  Tiefgang: {hydro_points[0]['draft']:.3f}m - "
            f"{hydro_points[-1]['draft']:.3f}m\n")
        
        # Interpolieren auf Zielgewicht
        App.Console.PrintMessage(f"\nInterpoliere fuer {total_mass_t:.1f}t...\n")
        hydro = interpolate_hydrostatics(hydro_points, total_mass_t)
        
        if not hydro:
            App.Console.PrintError("Interpolation fehlgeschlagen!\n")
            return None, None, None, None, None, None
        
        # KMt = KBt + BMt (aus Tabelle bereits berechnet)
        kmt = hydro['kmt']
        gm  = kmt - cog[2]
        
        # Trimm berechnen
        lcb_fc  = hydro['kbl']   # LCB in FreeCAD-Koordinaten
        lcg_fc  = cog[0]
        delta_x = lcg_fc - lcb_fc
        
        trim_deg, trim_cm, trim_moment_t_m = calculate_trim(
            delta_x, hydro['tmc'], total_mass_t, L_m)
        
        App.Console.PrintMessage(f"\n" + "="*60 + "\n")
        App.Console.PrintMessage("ERGEBNISSE:\n")
        App.Console.PrintMessage(
            f"  Tiefgang:  {hydro['draft']:.3f} m\n")
        App.Console.PrintMessage(
            f"  Trimm:     {trim_deg:.2f}° ({trim_cm:.1f} cm)\n")
        App.Console.PrintMessage(
            f"  LCB:       {lcb_fc:.3f} m  "
            f"({lcb_fc - mid_fc:+.3f} m von Mitte)\n")
        App.Console.PrintMessage(
            f"  LCG:       {lcg_fc:.3f} m  "
            f"({lcg_fc - mid_fc:+.3f} m von Mitte)\n")
        App.Console.PrintMessage(
            f"  VCG:       {cog[2]:.3f} m\n")
        App.Console.PrintMessage(
            f"  KBt:       {hydro['kbt']:.3f} m\n")
        App.Console.PrintMessage(
            f"  BMt:       {hydro['bmt']:.3f} m\n")
        App.Console.PrintMessage(
            f"  KMt:       {kmt:.3f} m\n")
        App.Console.PrintMessage(
            f"  GMt:       {gm:.3f} m\n")
        App.Console.PrintMessage(
            f"  TMC:       {hydro['tmc']:.2f} t*m/cm\n")
        App.Console.PrintMessage(
            f"  Trim-Mom.: {trim_moment_t_m:.1f} t*m\n")
        App.Console.PrintMessage("="*60 + "\n")
        
        result = {
            'draft':             hydro['draft'],
            'trim':              trim_deg,
            'trim_cm':           trim_cm,
            'trim_moment':       trim_moment_t_m,
            'lcb':               lcb_fc,
            'lcg':               lcg_fc,
            'vcg':               cog[2],
            'tcg':               cog[1],
            'kbt':               hydro['kbt'],
            'bmt':               hydro['bmt'],
            'kmt':               kmt,
            'gm':                gm,
            'tmc':               hydro['tmc'],
            'cb':                hydro['cb'],
            'cf':                hydro['cf'],
            'cm':                hydro['cm'],
            'displacement_t':    total_mass_t,
            'displacement_kg':   total_mass_kg,
            'lcb_from_midship':  lcb_fc - mid_fc,
            'lcg_from_midship':  lcg_fc - mid_fc,
            'delta_x':           delta_x,
            'L':                 L_m,
            'B':                 B_m,
            # Kompatibilitaet mit TaskPanel
            'kb':                hydro['kbt'],
            'km':                kmt,
            'xcb':               lcb_fc,
            'lcb_m':             lcb_fc - mid_fc,
            'vcb_m':             hydro['kbt'],
            'kb_m':              hydro['kbt'],
            'bmt_m':             hydro['bmt'],
            'km_m':              kmt,
            'gm_m':              gm,
            'draft_m':           hydro['draft'],
            'trim_deg':          trim_deg,
        }
        
        # Ergebnisse ins LoadCondition schreiben
        save_results_to_loadcondition(lc_spreadsheet, result)
        
        draft_qty = Units.Quantity(f"{hydro['draft']} m")
        trim_qty  = Units.Quantity(f"{trim_deg} deg")
        disp_qty  = Units.Quantity(f"{total_mass_kg} kg")
        
        return None, draft_qty, trim_qty, disp_qty, [], result
        
    except Exception as e:
        App.Console.PrintError(f"Allgemeiner Fehler: {e}\n")
        import traceback
        traceback.print_exc()
        return None, None, None, None, None, None
