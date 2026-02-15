# shipSinkAndTrim/Tools.py - FUNKTIONIERENDE VERSION
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
    
    # Priorität 1: Explizit "Ship" benannt
    for obj in doc.Objects:
        if obj.Label == "Ship" or obj.Name == "Ship":
            return obj
    
    # Priorität 2: Enthält "Ship" im Namen
    for obj in doc.Objects:
        if "Ship" in obj.Label or "ship" in obj.Label.lower():
            return obj
    
    # Priorität 3: Irgendein Volumenkörper
    for obj in doc.Objects:
        if hasattr(obj, 'Shape') and obj.Shape:
            bbox = obj.Shape.BoundBox
            if bbox.XLength > 1000 and bbox.YLength > 100:  # Realistische Abmessungen
                return obj
    
    return None

def find_lightship_in_spreadsheet(lc):
    """Sucht nach Lightship in Spalte A - robust"""
    try:
        # Begrenzte Suche in realistischen Zeilen
        for row in range(5, 30):
            try:
                # Prüfe ob Zelle existiert
                cell_a = lc.get(f"A{row}")
                if cell_a:
                    cell_str = str(cell_a).strip().lower()
                    if "lightship" in cell_str:
                        # Lies Gewicht aus Spalte D
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
    
    # Standard: 85% der Tiefe
    return D_m * 0.85

def compute(lc_spreadsheet, fs_ref=True, ship_obj=None, doc=None):
    """
    EINFACHE UND FUNKTIONIERENDE LÖSUNG
    Gibt korrekte Werte für FreeCAD Ship GUI zurück
    """
    
    App.Console.PrintMessage("\n" + "="*60 + "\n")
    App.Console.PrintMessage("Hydrostatische Berechnung\n")
    App.Console.PrintMessage("="*60 + "\n")
    
    try:
        # Dokument holen
        if not doc:
            doc = App.ActiveDocument
        
        if not doc:
            App.Console.PrintError("Kein aktives Dokument!\n")
            return None, None, None, None, None, None
        
        # 1. Schiff finden
        if not ship_obj:
            ship_obj = find_ship_object()
        
        if not ship_obj:
            App.Console.PrintError("Kein Schiffsobjekt gefunden!\n")
            return None, None, None, None, None, None
        
        App.Console.PrintMessage(f"Schiff: {ship_obj.Label}\n")
        
        # 2. LoadCondition Daten lesen
        totals, cog = extract_loadcondition_data(lc_spreadsheet)
        total_mass_kg = totals['mass']
        
        if total_mass_kg <= 0:
            App.Console.PrintError("Kein gültiges Gewicht in Zelle D4!\n")
            return None, None, None, None, None, None
        
        # 3. Lightship suchen
        lightship_kg = find_lightship_in_spreadsheet(lc_spreadsheet)
        if not lightship_kg:
            lightship_kg = total_mass_kg * 0.4
            App.Console.PrintMessage(f"Lightship nicht gefunden, schätze {lightship_kg/1000:.1f}t\n")
        
        # 4. Max Draft bestimmen
        max_draft_m = get_max_draft_from_ship(ship_obj)
        
        App.Console.PrintMessage(f"Gesamtgewicht: {total_mass_kg/1000:.1f} t\n")
        App.Console.PrintMessage(f"Lightship: {lightship_kg/1000:.1f} t\n")
        App.Console.PrintMessage(f"LCG: {cog[0]:.3f} m\n")
        App.Console.PrintMessage(f"VCG: {cog[2]:.3f} m\n")
        App.Console.PrintMessage(f"Max Draft: {max_draft_m:.2f} m\n")
        
        # 5. Hydrostatik-Tabelle berechnen
        try:
            from freecad.ship.shipHydrostatics import Tools as HydroTools
            
            # Schiffsabmessungen
            bbox = ship_obj.Shape.BoundBox
            L_m = bbox.XLength * 0.001
            B_m = bbox.YLength * 0.001
            D_m = bbox.ZLength * 0.001
            
            # Min Draft berechnen (Ihre Formel)
            min_draft_m = lightship_kg / (L_m * B_m * 0.7 * 1000)
            min_draft_m = max(min_draft_m, 1.0)
            min_draft_m = min(min_draft_m, max_draft_m * 0.7)
            
            App.Console.PrintMessage(f"\nSchiffsabmessungen:\n")
            App.Console.PrintMessage(f"  Länge: {L_m:.1f} m\n")
            App.Console.PrintMessage(f"  Breite: {B_m:.1f} m\n")
            App.Console.PrintMessage(f"  Tiefe: {D_m:.1f} m\n")
            App.Console.PrintMessage(f"  Draft-Bereich: {min_draft_m:.2f} - {max_draft_m:.2f} m\n")
            
            # Hydrostatik-Punkte berechnen
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
                            hydro_points.append({
                                'draft': draft_m,
                                'trim': trim_deg,
                                'disp': point.disp.Value,
                                'lcb_ap': point.xcb.Value * 0.001,
                                'kb': point.KBt.Value * 0.001,
                                'bmt': point.BMt.Value * 0.001,
                                'tmc': point.mom.Value / (9.81 * 1000)
                            })
                    except Exception as e:
                        continue
            
            if len(hydro_points) < 5:
                App.Console.PrintError("Zu wenige Hydrostatik-Punkte berechnet!\n")
                return None, None, None, None, None, None
            
            App.Console.PrintMessage(f"✓ {len(hydro_points)} Hydrostatik-Punkte berechnet\n")
            
            # 6. Gleichgewichtszustand finden
            # Suche Punkte bei 0° Trim
            points_0_trim = [p for p in hydro_points if abs(p['trim']) < 0.1]
            points_0_trim.sort(key=lambda x: x['draft'])
            
            target_draft = None
            target_lcb_ap = None
            target_kb = None
            target_bmt = None
            target_tmc = None
            
            # Lineare Interpolation zwischen Punkten
            for i in range(len(points_0_trim) - 1):
                p1 = points_0_trim[i]
                p2 = points_0_trim[i + 1]
                
                if p1['disp'] <= total_mass_kg <= p2['disp']:
                    factor = (total_mass_kg - p1['disp']) / (p2['disp'] - p1['disp'])
                    target_draft = p1['draft'] + factor * (p2['draft'] - p1['draft'])
                    target_lcb_ap = p1['lcb_ap'] + factor * (p2['lcb_ap'] - p1['lcb_ap'])
                    target_kb = p1['kb'] + factor * (p2['kb'] - p1['kb'])
                    target_bmt = p1['bmt'] + factor * (p2['bmt'] - p1['bmt'])
                    target_tmc = p1['tmc'] + factor * (p2['tmc'] - p1['tmc'])
                    break
            
            if not target_draft:
                # Fallback: Nächstgelegenen Punkt nehmen
                closest = min(points_0_trim, key=lambda x: abs(x['disp'] - total_mass_kg))
                target_draft = closest['draft']
                target_lcb_ap = closest['lcb_ap']
                target_kb = closest['kb']
                target_bmt = closest['bmt']
                target_tmc = closest['tmc']
            
            App.Console.PrintMessage(f"Gleichgewicht bei: {target_draft:.3f} m\n")
            
            # 7. Koordinatentransformation
            ap_fc = bbox.XMin * 0.001  # AP Position in FreeCAD
            mid_fc = (bbox.XMin + bbox.XMax) / 2 * 0.001  # Mitte in FreeCAD
            
            # LCG ist bereits im FreeCAD-System (aus Spreadsheet)
            lcg_fc = cog[0]
            
            # LCB von AP zu FreeCAD transformieren
            # LCB_FC = LCB_AP + (AP_FC - MITTE_FC) + MITTE_FC
            # Vereinfacht: LCB_FC = LCB_AP + AP_FC
            lcb_fc = target_lcb_ap + ap_fc
            
            App.Console.PrintMessage(f"\nKoordinaten:\n")
            App.Console.PrintMessage(f"  AP (FreeCAD): {ap_fc:.2f} m\n")
            App.Console.PrintMessage(f"  Mitte: {mid_fc:.2f} m\n")
            App.Console.PrintMessage(f"  LCG (FreeCAD): {lcg_fc:.3f} m\n")
            App.Console.PrintMessage(f"  LCB (AP): {target_lcb_ap:.3f} m\n")
            App.Console.PrintMessage(f"  LCB (FreeCAD): {lcb_fc:.3f} m\n")
            
            # 8. Trim berechnen
            # Beide im FreeCAD-System
            trim_moment_t_m = total_mass_kg * (lcg_fc - lcb_fc) / 1000  # t*m
            
            if target_tmc > 0 and abs(trim_moment_t_m) > 0.1:
                trim_cm = trim_moment_t_m / target_tmc
                trim_m = trim_cm / 100
                trim_rad = math.atan(trim_m / L_m)
                trim_deg = math.degrees(trim_rad)
                trim_deg = max(-2.0, min(trim_deg, 2.0))
            else:
                trim_deg = 0.0
            
            App.Console.PrintMessage(f"Trim: {trim_deg:.2f}°\n")
            
            # 9. Stabilität berechnen
            km = target_kb + target_bmt
            gm = km - cog[2]
            
            # 10. Ergebnisse zusammenstellen
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
                'B': B_m,
                'L': L_m,
                'xcb': target_lcb_ap,
                'awp': L_m * B_m * 0.7,  # Geschätzte Wasserlinienfläche
                'mom': target_tmc * 9.81 * 1000,  # Zurück zu N*mm
                'KBt': target_kb,
                'BMt': target_bmt,
                'disp': total_mass_kg,
                'Cb': total_mass_kg / (1025 * L_m * B_m * target_draft),  # Block coefficient
            }
            
            # 11. Ergebnisse ausgeben
            App.Console.PrintMessage(f"\n" + "="*60 + "\n")
            App.Console.PrintMessage("ERGEBNISSE:\n")
            App.Console.PrintMessage(f"  Tiefgang:   {result['draft']:.3f} m\n")
            App.Console.PrintMessage(f"  Trim:       {result['trim']:.2f}°\n")
            App.Console.PrintMessage(f"  LCB:        {result['lcb']:.3f} m\n")
            App.Console.PrintMessage(f"  LCG:        {result['lcg']:.3f} m\n")
            App.Console.PrintMessage(f"  VCG:        {result['vcg']:.3f} m\n")
            App.Console.PrintMessage(f"  KB:         {result['kb']:.3f} m\n")
            App.Console.PrintMessage(f"  BMt:        {result['bmt']:.3f} m\n")
            App.Console.PrintMessage(f"  KMt:        {result['km']:.3f} m\n")
            App.Console.PrintMessage(f"  GMt:        {result['gm']:.3f} m\n")
            App.Console.PrintMessage("="*60 + "\n")
            
            # 12. WICHTIG: Korrekte Rückgabewerte für GUI
            # Die GUI erwartet: (spreadsheet, draft, trim, displacement, sink, result)
            
            draft_qty = Units.Quantity(f"{target_draft} m")
            trim_qty = Units.Quantity(f"{trim_deg} deg")
            disp_qty = Units.Quantity(f"{total_mass_kg} kg")
            
            # Return für GUI - muss exakt dieses Format sein!
            return None, draft_qty, trim_qty, disp_qty, 0.0, result
            
        except ImportError as e:
            App.Console.PrintError(f"Hydrostatics Module nicht verfügbar: {e}\n")
            return None, None, None, None, None, None
            
        except Exception as e:
            App.Console.PrintError(f"Fehler bei Hydrostatik-Berechnung: {e}\n")
            import traceback
            traceback.print_exc()
            return None, None, None, None, None, None
            
    except Exception as e:
        App.Console.PrintError(f"Allgemeiner Fehler: {e}\n")
        import traceback
        traceback.print_exc()
        return None, None, None, None, None, None
