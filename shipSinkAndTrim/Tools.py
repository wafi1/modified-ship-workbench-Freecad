#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# shipSinkAndTrim/Tools.py - MIT SPREADSHEET-SPEICHERUNG
#***************************************************************************

import math
import FreeCAD as App
from FreeCAD import Units
import numpy as np

def extract_loadcondition_data(lc):
    """Extrahiert Daten aus LoadCondition Spreadsheet"""
    totals = {'mass': 0.0, 'free_surface': 0.0}
    cog = [0.0, 0.0, 0.0]
    
    try:
        mass_val = lc.get('D4')
        if mass_val:
            totals['mass'] = float(mass_val)
        
        x_val = lc.get('E5')
        y_val = lc.get('F5')
        z_val = lc.get('G5')
        
        if x_val:
            cog[0] = float(x_val)
        if y_val:
            cog[1] = float(y_val)
        if z_val:
            cog[2] = float(z_val)
            
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

def find_lightship_in_spreadsheet(lc):
    """Sucht nach Lightship in Spalte A"""
    try:
        for row in range(5, 30):
            try:
                cell_a = lc.get(f"A{row}")
                if cell_a:
                    cell_str = str(cell_a).strip().lower()
                    if "lightship" in cell_str:
                        weight_str = lc.get(f"D{row}", "0")
                        try:
                            weight = float(weight_str)
                            if weight > 0:
                                App.Console.PrintMessage(f"Lightship gefunden in Zeile {row}: {weight/1000:.1f}t\n")
                                return weight
                        except:
                            continue
            except:
                continue
        return None
    except:
        return None

def get_max_draft_from_ship(ship):
    """Ermittelt Max Draft aus Schiff"""
    if not ship:
        return None
    
    bbox = ship.Shape.BoundBox
    D_m = bbox.ZLength * 0.001
    
    return D_m * 0.85

def calculate_correct_tmc(point, ship_obj):
    """Berechnet korrekten TMC aus hydrostatischen Werten"""
    try:
        bbox = ship_obj.Shape.BoundBox
        L_m = bbox.XLength * 0.001
        B_m = bbox.YLength * 0.001
        
        disp_t = point.disp.Value
        
        C_wp = 0.75
        I_L = C_wp * (L_m**3 * B_m) / 12
        
        rho = 1.025
        displacement_volume = disp_t / rho
        
        if displacement_volume > 0:
            BML = I_L / displacement_volume
        else:
            BML = 0
        
        tmc = (disp_t * BML) / (100 * L_m)
        
        return tmc
        
    except Exception as e:
        App.Console.PrintWarning(f"Fehler in TMC-Berechnung: {e}\n")
        return 0.0

def find_or_create_hydrostatic_spreadsheet(doc):
    """Findet oder erzeugt Hydrostatic_Load Spreadsheet"""
    for obj in doc.Objects:
        if obj.TypeId == "Spreadsheet::Sheet":
            if obj.Label == "Hydrostatic_Load" or obj.Name == "Hydrostatic_Load":
                App.Console.PrintMessage("✓ Bestehendes Hydrostatic_Load Spreadsheet gefunden\n")
                return obj
    
    App.Console.PrintMessage("Erzeuge neues Hydrostatic_Load Spreadsheet...\n")
    sheet = doc.addObject('Spreadsheet::Sheet', 'Hydrostatic_Load')
    sheet.Label = "Hydrostatic_Load"
    
    headers = [
        ('A1', 'Draft [m]'),
        ('B1', 'Trim [deg]'),
        ('C1', 'Disp [kg]'),
        ('D1', 'LCB [m]'),
        ('E1', 'KB [m]'),
        ('F1', 'BMt [m]'),
        ('G1', 'TMC [t*m/cm]'),
        ('H1', 'Mom [mm*kg]'),
        ('I1', 'Mom [t*m]')
    ]
    
    for cell, text in headers:
        sheet.set(cell, text)
        sheet.setStyle(cell, 'bold', 'add')
        sheet.setBackground(cell, (0.8, 0.8, 0.8))
    
    widths = [('A', 80), ('B', 80), ('C', 100), ('D', 80), ('E', 80), 
              ('F', 80), ('G', 100), ('H', 120), ('I', 100)]
    for col, width in widths:
        sheet.setColumnWidth(col, width)
    
    doc.recompute()
    App.Console.PrintMessage("✓ Hydrostatic_Load Spreadsheet erzeugt\n")
    
    return sheet

def save_hydrostatic_points_to_spreadsheet(sheet, hydro_points, doc):
    """Speichert hydrostatische Punkte im Spreadsheet"""
    App.Console.PrintMessage(f"Speichere {len(hydro_points)} Punkte im Spreadsheet...\n")
    
    try:
        for row in range(2, 200):
            for col in ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I']:
                sheet.set(f'{col}{row}', '')
    except:
        pass
    
    row = 2
    for point in hydro_points:
        try:
            sheet.set(f'A{row}', f"{point['draft']:.4f}")
            sheet.set(f'B{row}', f"{point['trim']:.2f}")
            sheet.set(f'C{row}', f"{point['disp']:.1f}")
            sheet.set(f'D{row}', f"{point['lcb_abs']:.4f}")
            sheet.set(f'E{row}', f"{point['kb']:.4f}")
            sheet.set(f'F{row}', f"{point['bmt']:.4f}")
            sheet.set(f'G{row}', f"{point['tmc']:.2f}")
            sheet.set(f'H{row}', f"{point['mom_mmkg']:.1f}")
            sheet.set(f'I{row}', f"{point['mom_tm']:.4f}")
            row += 1
        except Exception as e:
            App.Console.PrintWarning(f"Fehler beim Schreiben Zeile {row}: {e}\n")
    
    doc.recompute()
    App.Console.PrintMessage(f"✓ {row-2} Punkte gespeichert\n")

def load_hydrostatic_points_from_spreadsheet(sheet):
    """Liest hydrostatische Punkte aus Spreadsheet"""
    App.Console.PrintMessage("Lade hydrostatische Punkte aus Spreadsheet...\n")
    
    points = []
    row = 2
    
    while True:
        try:
            draft_str = sheet.get(f'A{row}')
            if not draft_str or draft_str == '':
                break
            
            trim_str = sheet.get(f'B{row}')
            disp_str = sheet.get(f'C{row}')
            lcb_str = sheet.get(f'D{row}')
            kb_str = sheet.get(f'E{row}')
            bmt_str = sheet.get(f'F{row}')
            tmc_str = sheet.get(f'G{row}')
            mom_mmkg_str = sheet.get(f'H{row}')
            mom_tm_str = sheet.get(f'I{row}')
            
            point = {
                'draft': float(draft_str),
                'trim': float(trim_str),
                'disp': float(disp_str),
                'lcb_abs': float(lcb_str),
                'kb': float(kb_str),
                'bmt': float(bmt_str),
                'tmc': float(tmc_str),
                'mom_mmkg': float(mom_mmkg_str),
                'mom_tm': float(mom_tm_str)
            }
            
            points.append(point)
            row += 1
            
        except Exception as e:
            break
    
    App.Console.PrintMessage(f"✓ {len(points)} Punkte geladen\n")
    return points

def check_if_recalculation_needed(sheet, ship_obj):
    """Prüft ob Neuberechnung nötig ist"""
    try:
        first_draft = sheet.get('A2')
        if not first_draft or first_draft == '':
            App.Console.PrintMessage("Spreadsheet ist leer - Neuberechnung nötig\n")
            return True
        
        return False
        
    except:
        return True

def compute_hydrostatic_table(ship_obj, min_draft_m, max_draft_m, L_m):
    """Berechnet die vollständige hydrostatische Tabelle"""
    from freecad.ship.shipHydrostatics import Tools as HydroTools
    
    hydro_points = []
    drafts = np.linspace(min_draft_m, max_draft_m, 8)
    trims = [-1.0, -0.5, 0.0, 0.5, 1.0]
    
    App.Console.PrintMessage(f"Berechne Hydrostatik-Punkte...\n")
    
    for draft_m in drafts:
        for trim_deg in trims:
            try:
                draft_q = Units.parseQuantity(f"{draft_m * 1000} mm")
                trim_q = Units.parseQuantity(f"{trim_deg} deg")
                
                point = HydroTools.Point(ship_obj, None, draft_q, trim_q)
                
                if point.disp.Value > 0:
                    correct_tmc = calculate_correct_tmc(point, ship_obj)
                    
                    mom_mmkg = point.mom.Value
                    mom_tm = mom_mmkg / 1e6
                    
                    hydro_points.append({
                        'draft': draft_m,
                        'trim': trim_deg,
                        'disp': point.disp.Value,
                        'lcb_abs': point.xcb.Value * 0.001,
                        'kb': point.KBt.Value * 0.001,
                        'bmt': point.BMt.Value * 0.001,
                        'tmc': correct_tmc,
                        'mom_mmkg': mom_mmkg,
                        'mom_tm': mom_tm
                    })
            except Exception as e:
                App.Console.PrintWarning(f"Fehler bei Draft {draft_m}m, Trim {trim_deg}°: {e}\n")
                continue
    
    App.Console.PrintMessage(f"✓ {len(hydro_points)} Hydrostatik-Punkte berechnet\n")
    return hydro_points


def save_results_to_loadcondition(lc_sheet, result):
    """Speichert berechnete Werte zurück ins LoadCondition-Spreadsheet.
    
    Schreibt:
    - E4, D6: Tiefgang [m]
    - F4:     KM [m]
    - G4:     GM korrigiert [m] = GM - FSM_Hebel
    - H5:     FSM-Hebel [m] = (D4/1000) / H4   (NEU!)
    """
    try:
        App.Console.PrintMessage("\nSpeichere Ergebnisse in LoadCondition...\n")
        
        # --- 1. Tiefgang ---
        draft_m = result['draft']
        lc_sheet.set('E4', f"{draft_m:.4f}")
        lc_sheet.set('D6', f"{draft_m:.4f}")
        App.Console.PrintMessage(f"  E4, D6: Draft = {draft_m:.4f} m\n")
        
        # --- 2. KM ---
        km_m = result['km']
        lc_sheet.set('F4', f"{km_m:.4f}")
        App.Console.PrintMessage(f"  F4: KM = {km_m:.4f} m\n")
        
        # --- 3. FSM-Hebel in H5 berechnen ---
        try:
            # D4 = Gesamtgewicht [kg]
            d4_val = lc_sheet.get('D4')
            # H4 = Gesamt FSM [t*m]
            h4_val = lc_sheet.get('H4')
            
            if d4_val and h4_val:
                total_mass_kg = float(str(d4_val).replace(',', '.').strip())
                total_fsm_tm = float(str(h4_val).replace(',', '.').strip())
                
                # FSM-Hebel = Gewicht [t] / FSM [t*m]
                if total_fsm_tm > 0:
                    fsm_lever_m = total_fsm_tm / (total_mass_kg / 1000)
                    lc_sheet.set('H5', f"{fsm_lever_m:.6f}")
                    App.Console.PrintMessage(f"  H5: FSM-Hebel = ({total_mass_kg/1000:.1f}t) / ({total_fsm_tm:.3f}t*m) = {fsm_lever_m:.6f} m\n")
                else:
                    lc_sheet.set('H5', "0.0")
                    App.Console.PrintMessage(f"  H5: FSM-Hebel = 0.0 (H4 = 0)\n")
            else:
                App.Console.PrintWarning("  H5: D4 oder H4 nicht verfügbar\n")
                lc_sheet.set('H5', "0.0")
                
        except Exception as e:
            App.Console.PrintWarning(f"  Fehler bei H5-Berechnung: {e}\n")
            lc_sheet.set('H5', "0.0")
        
        # --- 4. GM korrigiert in G4 ---
        try:
            # H5 lesen (gerade geschrieben)
            fsm_lever_val = lc_sheet.get('H5')
            
            if fsm_lever_val:
                fsm_lever_m = float(str(fsm_lever_val).replace(',', '.').strip())
                gm_m = result['gm']
                gm_corrected_m = gm_m - fsm_lever_m
                
                lc_sheet.set('G4', f"{gm_corrected_m:.4f}")
                App.Console.PrintMessage(
                    f"  G4: GM_korr = {gm_m:.4f} - {fsm_lever_m:.6f} = "
                    f"{gm_corrected_m:.4f} m\n")
            else:
                App.Console.PrintWarning("  H5 (FSM-Hebel) ist leer — G4 = GM ohne Korrektur\n")
                lc_sheet.set('G4', f"{result['gm']:.4f}")
                
        except Exception as e:
            App.Console.PrintWarning(f"  Fehler beim Lesen von H5: {e}\n")
            lc_sheet.set('G4', f"{result['gm']:.4f}")
        
        # Recompute
        App.ActiveDocument.recompute()
        App.Console.PrintMessage("✓ Ergebnisse in LoadCondition gespeichert\n")
        
    except Exception as e:
        App.Console.PrintError(f"Fehler beim Speichern in LoadCondition: {e}\n")
        import traceback
        traceback.print_exc()
        

def compute(lc_spreadsheet, fs_ref=True, ship_obj=None, doc=None):
    """Hydrostatische Equilibrium-Berechnung mit Spreadsheet-Speicherung"""
    
    App.Console.PrintMessage("\n" + "="*60 + "\n")
    App.Console.PrintMessage("Hydrostatische Berechnung\n")
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
        
        App.Console.PrintMessage(f"Schiff: {ship_obj.Label}\n")
        
        totals, cog = extract_loadcondition_data(lc_spreadsheet)
        total_mass_kg = totals['mass']
        
        if total_mass_kg <= 0:
            App.Console.PrintError("Kein gültiges Gewicht in Zelle D4!\n")
            return None, None, None, None, None, None
        
        lightship_kg = find_lightship_in_spreadsheet(lc_spreadsheet)
        if not lightship_kg:
            lightship_kg = total_mass_kg * 0.4
            App.Console.PrintMessage(f"Lightship nicht gefunden, schätze {lightship_kg/1000:.1f}t\n")
        
        max_draft_m = get_max_draft_from_ship(ship_obj)
        
        App.Console.PrintMessage(f"Gesamtgewicht: {total_mass_kg/1000:.1f} t\n")
        App.Console.PrintMessage(f"Lightship: {lightship_kg/1000:.1f} t\n")
        App.Console.PrintMessage(f"LCG: {cog[0]:.3f} m\n")
        App.Console.PrintMessage(f"VCG: {cog[2]:.3f} m\n")
        App.Console.PrintMessage(f"Max Draft: {max_draft_m:.2f} m\n")
        
        bbox = ship_obj.Shape.BoundBox
        L_m = bbox.XLength * 0.001
        B_m = bbox.YLength * 0.001
        D_m = bbox.ZLength * 0.001
        
        min_draft_m = lightship_kg / (L_m * B_m * 0.7 * 1000)
        min_draft_m = max(min_draft_m, 1.0)
        min_draft_m = min(min_draft_m, max_draft_m * 0.7)
        
        App.Console.PrintMessage(f"\nSchiffsabmessungen:\n")
        App.Console.PrintMessage(f"  Länge: {L_m:.1f} m\n")
        App.Console.PrintMessage(f"  Breite: {B_m:.1f} m\n")
        App.Console.PrintMessage(f"  Tiefe: {D_m:.1f} m\n")
        App.Console.PrintMessage(f"  Draft-Bereich: {min_draft_m:.2f} - {max_draft_m:.2f} m\n")
        
        hydro_sheet = find_or_create_hydrostatic_spreadsheet(doc)
        
        needs_recalc = check_if_recalculation_needed(hydro_sheet, ship_obj)
        
        if needs_recalc:
            App.Console.PrintMessage("\n>>> Berechne neue hydrostatische Tabelle <<<\n")
            hydro_points = compute_hydrostatic_table(ship_obj, min_draft_m, max_draft_m, L_m)
            
            if len(hydro_points) < 5:
                App.Console.PrintError("Zu wenige Hydrostatik-Punkte berechnet!\n")
                return None, None, None, None, None, None
            
            save_hydrostatic_points_to_spreadsheet(hydro_sheet, hydro_points, doc)
        else:
            App.Console.PrintMessage("\n>>> Lade hydrostatische Daten aus Spreadsheet <<<\n")
            hydro_points = load_hydrostatic_points_from_spreadsheet(hydro_sheet)
            
            if len(hydro_points) < 5:
                App.Console.PrintWarning("Zu wenige Punkte im Spreadsheet, neu berechnen...\n")
                hydro_points = compute_hydrostatic_table(ship_obj, min_draft_m, max_draft_m, L_m)
                save_hydrostatic_points_to_spreadsheet(hydro_sheet, hydro_points, doc)
        
        points_0_trim = [p for p in hydro_points if abs(p['trim']) < 0.1]
        points_0_trim.sort(key=lambda x: x['draft'])
        
        target_draft = None
        target_lcb_abs = None
        target_kb = None
        target_bmt = None
        target_tmc = None
        
        for i in range(len(points_0_trim) - 1):
            p1 = points_0_trim[i]
            p2 = points_0_trim[i + 1]
            
            if p1['disp'] <= total_mass_kg <= p2['disp']:
                factor = (total_mass_kg - p1['disp']) / (p2['disp'] - p1['disp'])
                target_draft = p1['draft'] + factor * (p2['draft'] - p1['draft'])
                target_lcb_abs = p1['lcb_abs'] + factor * (p2['lcb_abs'] - p1['lcb_abs'])
                target_kb = p1['kb'] + factor * (p2['kb'] - p1['kb'])
                target_bmt = p1['bmt'] + factor * (p2['bmt'] - p1['bmt'])
                target_tmc = p1['tmc'] + factor * (p2['tmc'] - p1['tmc'])
                break
        
        if not target_draft:
            closest = min(points_0_trim, key=lambda x: abs(x['disp'] - total_mass_kg))
            target_draft = closest['draft']
            target_lcb_abs = closest['lcb_abs']
            target_kb = closest['kb']
            target_bmt = closest['bmt']
            target_tmc = closest['tmc']
        
        App.Console.PrintMessage(f"Gleichgewicht bei: {target_draft:.3f} m\n")
        
        ap_fc = bbox.XMin * 0.001
        mid_fc = (bbox.XMin + bbox.XMax) / 2 * 0.001
        
        lcg_fc = cog[0]
        lcb_fc = target_lcb_abs
        
        lcg_from_mid = lcg_fc - mid_fc
        lcb_from_mid = lcb_fc - mid_fc
        
        App.Console.PrintMessage(f"\nKoordinaten:\n")
        App.Console.PrintMessage(f"  Schiffsmitte (FreeCAD): {mid_fc:.2f} m\n")
        App.Console.PrintMessage(f"  AP (FreeCAD): {ap_fc:.2f} m\n")
        App.Console.PrintMessage(f"\n  LCG (absolut):   {lcg_fc:.3f} m\n")
        App.Console.PrintMessage(f"  LCG (von Mitte): {lcg_from_mid:+.3f} m\n")
        App.Console.PrintMessage(f"\n  LCB (absolut):   {lcb_fc:.3f} m\n")
        App.Console.PrintMessage(f"  LCB (von Mitte): {lcb_from_mid:+.3f} m\n")
        
        delta_x = lcg_fc - lcb_fc
        
        App.Console.PrintMessage(f"\nTrim-Berechnung:\n")
        App.Console.PrintMessage(f"  LCG - LCB = {lcg_fc:.3f} - {lcb_fc:.3f} = {delta_x:.3f} m\n")
        
        trim_moment_kg_m = total_mass_kg * delta_x
        trim_moment_t_m = trim_moment_kg_m / 1000
        
        if target_tmc > 0 and abs(trim_moment_t_m) > 0.1:
            trim_cm = trim_moment_t_m / target_tmc
            trim_m = trim_cm / 100
            
            if L_m > 0:
                trim_rad = math.atan(trim_m / L_m)
                trim_deg = math.degrees(trim_rad)
                trim_deg = max(-2.0, min(trim_deg, 2.0))
            else:
                trim_deg = 0.0
            
            App.Console.PrintMessage(f"  Trim Moment: {trim_moment_t_m:.1f} t*m\n")
            App.Console.PrintMessage(f"  TMC: {target_tmc:.1f} t*m/cm\n")
            App.Console.PrintMessage(f"  Trim: {trim_cm:.1f} cm = {trim_deg:.2f}°\n")
        else:
            trim_deg = 0.0
            trim_cm = 0.0
            App.Console.PrintMessage(f"  Trim: 0.00° (Moment zu klein oder TMC = 0)\n")
        
        km = target_kb + target_bmt
        gm = km - cog[2]
        
        result = {
            'displacement': total_mass_kg,
            'draft': target_draft,
            'trim': trim_deg,
            'lcb': lcb_fc,
            'lcg': lcg_fc,
            'vcg': cog[2],
            'tcg': cog[1],
            'kb': target_kb,
            'bmt': target_bmt,
            'km': km,
            'gm': gm,
            'tmc': target_tmc,
            'trim_cm': trim_cm,
            'trim_moment': trim_moment_t_m,
            'lcb_from_midship': lcb_from_mid,
            'lcg_from_midship': lcg_from_mid,
            'B': B_m,
            'L': L_m,
            'xcb': target_lcb_abs,
            'awp': L_m * B_m * 0.7,
            'KBt': target_kb,
            'BMt': target_bmt,
            'disp': total_mass_kg,
            'Cb': total_mass_kg / (1025 * L_m * B_m * target_draft),
            'draft_m': target_draft,
            'trim_deg': trim_deg,
            'lcb_m': lcb_from_mid,
            'vcb_m': target_kb,
            'kb_m': target_kb,
            'bmt_m': target_bmt,
            'km_m': km,
            'gm_m': gm,
            'displacement_kg': total_mass_kg,
            'displacement_t': total_mass_kg / 1000,
            'delta_x': delta_x,
            'mid_fc': mid_fc,
            'ap_fc': ap_fc
        }
        
        App.Console.PrintMessage(f"\n" + "="*60 + "\n")
        App.Console.PrintMessage("ERGEBNISSE:\n")
        App.Console.PrintMessage(f"  Tiefgang:        {result['draft']:.3f} m\n")
        App.Console.PrintMessage(f"  Trim:            {result['trim']:.2f}° ({result['trim_cm']:.1f} cm)\n")
        App.Console.PrintMessage(f"  LCB (von Mitte): {result['lcb_from_midship']:+.3f} m\n")
        App.Console.PrintMessage(f"  LCG (von Mitte): {result['lcg_from_midship']:+.3f} m\n")
        App.Console.PrintMessage(f"  VCG:             {result['vcg']:.3f} m\n")
        App.Console.PrintMessage(f"  KB:              {result['kb']:.3f} m\n")
        App.Console.PrintMessage(f"  BMt:             {result['bmt']:.3f} m\n")
        App.Console.PrintMessage(f"  KMt:             {result['km']:.3f} m\n")
        App.Console.PrintMessage(f"  GMt:             {result['gm']:.3f} m\n")
        App.Console.PrintMessage(f"  TMC:             {result['tmc']:.1f} t*m/cm\n")
        App.Console.PrintMessage(f"  Δx:              {delta_x:.3f} m\n")
        App.Console.PrintMessage(f"  Trim Moment:     {trim_moment_t_m:.1f} t*m\n")
        App.Console.PrintMessage("="*60 + "\n")
        
        App.Console.PrintMessage(f"\nTMC-Debug:\n")
        App.Console.PrintMessage(f"  Berechneter TMC: {target_tmc:.1f} t*m/cm\n")
        App.Console.PrintMessage(f"  Für L = {L_m:.1f}m, Δ = {total_mass_kg/1000:.1f}t\n")
        App.Console.PrintMessage(f"  Erwarteter TMC-Bereich: ~{L_m*L_m/30:.0f} - {L_m*L_m/20:.0f} t*m/cm\n")
        
        # NEU: Ergebnisse ins LoadCondition-Spreadsheet schreiben
        save_results_to_loadcondition(lc_spreadsheet, result)
        
        draft_qty = Units.Quantity(f"{target_draft} m")
        trim_qty = Units.Quantity(f"{trim_deg} deg")
        disp_qty = Units.Quantity(f"{total_mass_kg} kg")
        
        return None, draft_qty, trim_qty, disp_qty, 0.0, result
        
    except Exception as e:
        App.Console.PrintError(f"Allgemeiner Fehler: {e}\n")
        import traceback
        traceback.print_exc()
        return None, None, None, None, None, None
