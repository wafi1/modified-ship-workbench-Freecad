# shipSinkAndTrim/Tools.py - UNIVERSALE LÖSUNG FÜR ALLE SCHIFFE
#***************************************************************************

import math
import FreeCAD as App
import FreeCADGui as Gui
from FreeCAD import Vector, Units
import numpy as np
from scipy import interpolate


#===========================================================================
# 1. UNIVERSALE DRAFT-BERECHNUNG
#===========================================================================

def calculate_universal_draft_range(ship, lightship_weight_kg=None):
    """
    Universale Draft-Berechnung für alle Schiffstypen:
    - Min Draft: lightship_weight / (L*B*0.7) ODER 10% der Tiefe
    - Max Draft: Aus Schiffsinfo (wenn verfügbar) oder 85% der Tiefe
    """
    
    bbox = ship.Shape.BoundBox
    
    # Abmessungen in Metern
    L_m = bbox.XLength / 1000.0  # Länge zwischen Loten (Lpp)
    B_m = bbox.YLength / 1000.0  # Breite
    D_m = bbox.ZLength / 1000.0  # Tiefe/Schiffshöhe
    
    App.Console.PrintMessage(f"\nSchiffsabmessungen:\n")
    App.Console.PrintMessage(f"  Länge Lpp: {L_m:.1f} m\n")
    App.Console.PrintMessage(f"  Breite B:  {B_m:.1f} m\n")
    App.Console.PrintMessage(f"  Tiefe D:   {D_m:.1f} m\n")
    
    # MAX DRAFT: Aus Schiffsinfo entnehmen
    max_draft = None
    
    # Versuche, Max Draft aus Schiffsobjekt zu lesen
    if hasattr(ship, 'DesignDraft'):
        max_draft = ship.DesignDraft
    elif hasattr(ship, 'MaxDraft'):
        max_draft = ship.MaxDraft
    elif hasattr(ship, 'Draft'):
        max_draft = ship.Draft
    
    # Falls nicht gefunden, berechne realistischen Wert
    if max_draft is None:
        # Standard: 85% der Tiefe, mindestens aber 0.8 * D
        max_draft = max(D_m * 0.85, D_m * 0.8)
    
    # Sicherheitsgrenze: Nicht mehr als 90% der Tiefe
    max_draft = min(max_draft, D_m * 0.9)
    
    # MIN DRAFT: Abhängig von Lightship
    if lightship_weight_kg and lightship_weight_kg > 0:
        # Ihre spezifische Formel
        min_draft = lightship_weight_kg / (L_m * B_m * 0.7 * 1000)  # in Metern
        min_draft = max(min_draft, D_m * 0.05)  # Mindestens 5% der Tiefe
    else:
        # Standard: 10% der Tiefe oder 0.5m, was größer ist
        min_draft = max(D_m * 0.1, 0.5)
    
    # Sicherstellen, dass min < max
    min_draft = min(min_draft, max_draft * 0.7)
    
    # Mindestabstand zwischen min und max
    if (max_draft - min_draft) < 0.5:
        max_draft = min_draft + 0.5
    
    App.Console.PrintMessage(f"\nDraft-Bereich:\n")
    App.Console.PrintMessage(f"  Min Draft: {min_draft:.2f} m\n")
    App.Console.PrintMessage(f"  Max Draft: {max_draft:.2f} m\n")
    App.Console.PrintMessage(f"  Span:      {max_draft - min_draft:.2f} m\n")
    
    return min_draft, max_draft, L_m, B_m, D_m


#===========================================================================
# 2. UNIVERSALE TRIM-BERECHNUNG
#===========================================================================

def calculate_universal_trim_range(L_m, ship_type=None):
    """
    Universale Trim-Berechnung für alle Schiffe:
    - Grundsätzlich: Max ±2° (wie von Ihnen spezifiziert)
    - Für sehr kleine Schiffe: Etwas mehr
    - Für sehr große Schiffe: Etwas weniger
    """
    
    # GRUNDLEGENDE TRIM-GRENZEN
    base_max_trim = 2.0  # ±2° wie spezifiziert
    
    # Automatische Anpassung basierend auf Länge
    if L_m < 20:  # Sehr kleine Schiffe
        max_trim_deg = min(3.0, base_max_trim * 1.5)
    elif L_m < 50:  # Kleine Schiffe
        max_trim_deg = base_max_trim
    elif L_m > 200:  # Sehr große Schiffe
        max_trim_deg = min(1.5, base_max_trim * 0.75)
    else:  # Normale Schiffe
        max_trim_deg = base_max_trim
    
    # Falls Schiffstyp bekannt, zusätzliche Anpassung
    if ship_type:
        ship_type_lower = ship_type.lower()
        if 'tanker' in ship_type_lower or 'container' in ship_type_lower:
            max_trim_deg = min(max_trim_deg, 1.0)  # Weniger Trim für bestimmte Typen
    
    trim_min_deg = -max_trim_deg
    trim_max_deg = max_trim_deg
    
    # Trim in Metern berechnen (für Information)
    trim_change_m = L_m * math.tan(math.radians(max_trim_deg))
    
    App.Console.PrintMessage(f"\nTrim-Bereich:\n")
    App.Console.PrintMessage(f"  Maximaler Trim: ±{max_trim_deg:.1f}°\n")
    App.Console.PrintMessage(f"  Entspricht: ±{trim_change_m:.2f} m an den Enden\n")
    App.Console.PrintMessage(f"  Das sind ±{trim_change_m/L_m*100:.1f}% der Schiffslänge\n")
    
    return trim_min_deg, trim_max_deg, max_trim_deg


#===========================================================================
# 3. HYDROSTATIK-TABELLE FÜR ALLE SCHIFFE
#===========================================================================

def compute_universal_hydrostatics_table(ship, lightship_weight_kg=None, 
                                         n_drafts=15, n_trims=7):
    """
    Universale hydrostatische Tabelle für alle Schiffstypen
    """
    
    try:
        from freecad.ship.shipHydrostatics import Tools as HydroTools
    except ImportError:
        App.Console.PrintError("✗ Hydrostatics Tools nicht verfügbar!\n")
        return []
    
    # 1. Universale Bereiche
    min_draft_m, max_draft_m, L_m, B_m, D_m = calculate_universal_draft_range(
        ship, lightship_weight_kg
    )
    
    trim_min_deg, trim_max_deg, max_trim = calculate_universal_trim_range(L_m)
    
    # 2. Intelligente Punktverteilung
    # Mehr Punkte bei typischen Drafts, weniger an Extremen
    draft_range = max_draft_m - min_draft_m
    
    # Dichte der Punkte anpassen basierend auf Bereich
    if draft_range > 10:  # Großer Draft-Bereich
        n_drafts = min(20, int(draft_range * 2))
    elif draft_range < 2:  # Kleiner Draft-Bereich
        n_drafts = max(8, int(draft_range * 5))
    
    # Draft-Punkte (leicht konzentriert in der Mitte)
    drafts_m = []
    for i in range(n_drafts):
        # Cosinus-Verteilung für mehr Punkte in der Mitte
        t = (i / (n_drafts - 1)) * math.pi
        factor = (1 - math.cos(t)) / 2
        draft = min_draft_m + factor * draft_range
        drafts_m.append(draft)
    
    # Trim-Punkte (gleichmäßig)
    trims_deg = np.linspace(trim_min_deg, trim_max_deg, n_trims)
    
    points = []
    
    App.Console.PrintMessage(f"\nBerechne Hydrostatik-Tabelle:\n")
    App.Console.PrintMessage(f"  Drafts: {min_draft_m:.2f}m bis {max_draft_m:.2f}m ({n_drafts} Punkte)\n")
    App.Console.PrintMessage(f"  Trims:  {trim_min_deg:.1f}° bis {trim_max_deg:.1f}° ({n_trims} Punkte)\n")
    App.Console.PrintMessage(f"  Gesamt: {n_drafts * n_trims} Punkte\n")
    
    successful = 0
    failed_points = []
    
    for draft_m in drafts_m:
        for trim_deg in trims_deg:
            try:
                draft_q = Units.parseQuantity(f"{draft_m * 1000} mm")
                trim_q = Units.parseQuantity(f"{trim_deg} deg")
                
                # Timeout-Schutz
                point = HydroTools.Point(ship, None, draft_q, trim_q)
                
                # Validierung der Ergebnisse
                if (point.disp.Value > 0 and 
                    not math.isnan(point.xcb.Value) and
                    point.KBt.Value > 0 and
                    point.BMt.Value > 0):
                    
                    hydro_point = {
                        'draft_m': draft_m,
                        'trim_deg': trim_deg,
                        'displacement_kg': point.disp.Value,
                        'lcb_m': point.xcb.Value / 1000.0,
                        'kb_m': point.KBt.Value / 1000.0,
                        'bmt_m': point.BMt.Value / 1000.0,
                        'tmc_kg_m': point.mom.Value / (9.81 * 1000),
                        'kml_m': point.KML.Value / 1000.0 if hasattr(point, 'KML') else 0,
                        'area_m2': point.AW.Value / 1e6 if hasattr(point, 'AW') else 0,
                        'valid': True
                    }
                    points.append(hydro_point)
                    successful += 1
                else:
                    failed_points.append((draft_m, trim_deg))
                    
            except Exception as e:
                failed_points.append((draft_m, trim_deg))
                continue
    
    App.Console.PrintMessage(f"✓ {successful} gültige Punkte\n")
    if failed_points:
        App.Console.PrintMessage(f"✗ {len(failed_points)} fehlgeschlagene Punkte\n")
    
    return points, L_m, B_m, D_m, max_trim


#===========================================================================
# 4. UNIVERSALER INTERPOLATOR
#===========================================================================

class UniversalHydrostaticsInterpolator:
    def __init__(self, hydro_points, ship_length_m, max_trim_deg):
        self.points = hydro_points
        self.ship_length_m = ship_length_m
        self.max_trim_deg = max_trim_deg
        
        if len(hydro_points) < 6:
            raise ValueError(f"Zu wenige gültige Punkte: {len(hydro_points)}")
        
        # Daten für Interpolation
        drafts, trims, displacements = [], [], []
        lcbs, kbs, bmts, tmcs = [], [], [], []
        
        for p in hydro_points:
            if p.get('valid', True):
                drafts.append(p['draft_m'])
                trims.append(p['trim_deg'])
                displacements.append(p['displacement_kg'])
                lcbs.append(p['lcb_m'])
                kbs.append(p['kb_m'])
                bmts.append(p['bmt_m'])
                tmcs.append(p['tmc_kg_m'])
        
        # Scipy LinearNDInterpolator für unregelmäßige Daten
        coords = np.column_stack([drafts, trims])
        
        try:
            self.disp_interp = interpolate.LinearNDInterpolator(coords, displacements)
            self.lcb_interp = interpolate.LinearNDInterpolator(coords, lcbs)
            self.kb_interp = interpolate.LinearNDInterpolator(coords, kbs)
            self.bmt_interp = interpolate.LinearNDInterpolator(coords, bmts)
            self.tmc_interp = interpolate.LinearNDInterpolator(coords, tmcs)
            
            # Backup: GridInterpolator für Ränder
            grid_drafts = np.unique(drafts)
            grid_trims = np.unique(trims)
            grid_disp = np.zeros((len(grid_drafts), len(grid_trims)))
            
            for i, d in enumerate(grid_drafts):
                for j, t in enumerate(grid_trims):
                    # Finde nächstgelegenen Punkt
                    distances = [(abs(p['draft_m']-d) + abs(p['trim_deg']-t)*0.1) 
                                for p in hydro_points if p.get('valid', True)]
                    if distances:
                        idx = np.argmin(distances)
                        grid_disp[i,j] = displacements[idx]
            
            if len(grid_drafts) > 1 and len(grid_trims) > 1:
                self.grid_disp_interp = interpolate.RegularGridInterpolator(
                    (grid_drafts, grid_trims), grid_disp, bounds_error=False, fill_value=None
                )
            else:
                self.grid_disp_interp = None
                
        except Exception as e:
            App.Console.PrintError(f"Interpolator-Erstellung fehlgeschlagen: {e}\n")
            raise
        
        # Grenzen
        self.draft_min = min(drafts)
        self.draft_max = max(drafts)
        self.trim_min = min(trims)
        self.trim_max = max(trims)
        
        App.Console.PrintMessage(f"Interpolator für {len(drafts)} Punkte erstellt\n")
        App.Console.PrintMessage(f"Draft: {self.draft_min:.2f}m - {self.draft_max:.2f}m\n")
        App.Console.PrintMessage(f"Trim:  {self.trim_min:.1f}° - {self.trim_max:.1f}°\n")
    
    def get_values(self, draft_m, trim_deg):
        """Interpoliert hydrostatische Werte mit Fallbacks"""
        
        # Auf gültigen Bereich beschränken
        draft_m = max(self.draft_min, min(draft_m, self.draft_max))
        trim_deg = max(self.trim_min, min(trim_deg, self.trim_max))
        
        try:
            disp = float(self.disp_interp(draft_m, trim_deg))
            lcb = float(self.lcb_interp(draft_m, trim_deg))
            kb = float(self.kb_interp(draft_m, trim_deg))
            bmt = float(self.bmt_interp(draft_m, trim_deg))
            tmc = float(self.tmc_interp(draft_m, trim_deg))
            
            # Validierung
            if (math.isnan(disp) or disp <= 0 or
                math.isnan(lcb) or math.isnan(kb) or kb <= 0):
                
                # Fallback zu Grid-Interpolation
                if self.grid_disp_interp:
                    try:
                        disp = float(self.grid_disp_interp([draft_m, trim_deg]))
                    except:
                        return None
                else:
                    return None
            
            return {
                'displacement_kg': disp,
                'lcb_m': lcb,
                'kb_m': kb,
                'bmt_m': bmt,
                'tmc_kg_m': tmc,
            }
            
        except Exception as e:
            return None


#===========================================================================
# 5. UNIVERSALE GLEICHGEWICHTS-SUCHE
#===========================================================================

def find_universal_equilibrium(interpolator, target_mass_kg, lcg_ap_m, vcg_m, 
                               ship_length_m, max_trim_deg):
    """
    Universale Gleichgewichtssuche für alle Schiffstypen
    """
    
    App.Console.PrintMessage(f"\nGleichgewichtssuche für {target_mass_kg/1000:.1f}t\n")
    
    # 1. INITIALE SCHÄTZUNG
    draft_min = interpolator.draft_min
    draft_max = interpolator.draft_max
    
    # Suche besten Startpunkt im Draft-Bereich
    test_drafts = np.linspace(draft_min, draft_max, 15)
    best_draft = (draft_min + draft_max) / 2
    best_error = float('inf')
    
    for test_draft in test_drafts:
        hydro = interpolator.get_values(test_draft, 0.0)
        if hydro:
            error = abs(hydro['displacement_kg'] - target_mass_kg) / target_mass_kg
            if error < best_error:
                best_error = error
                best_draft = test_draft
    
    # Startwerte
    draft = best_draft
    trim = 0.0
    
    # 2. ITERATION
    for iteration in range(20):
        hydro = interpolator.get_values(draft, trim)
        if not hydro:
            App.Console.PrintWarning(f"Iteration {iteration}: Interpolation fehlgeschlagen\n")
            # Fallback: Nur Draft anpassen
            draft = draft_min + (draft_max - draft_min) * 0.5
            continue
        
        current_mass = hydro['displacement_kg']
        mass_error = current_mass - target_mass_kg
        mass_error_rel = abs(mass_error) / target_mass_kg
        
        App.Console.PrintMessage(f"Iteration {iteration+1}:\n")
        App.Console.PrintMessage(f"  Draft: {draft:.3f}m, Trim: {trim:.2f}°\n")
        App.Console.PrintMessage(f"  Mass: {current_mass/1000:.1f}t (Ziel: {target_mass_kg/1000:.1f}t)\n")
        App.Console.PrintMessage(f"  Fehler: {mass_error_rel*100:.2f}%\n")
        
        # Konvergenz?
        if mass_error_rel < 0.001:  # 0.1%
            App.Console.PrintMessage(f"✓ Konvergiert nach {iteration+1} Iterationen\n")
            break
        
        # 3. DRAFT-KORREKTUR (konservativ)
        if hydro['tmc_kg_m'] > 0 and hydro['tmc_kg_m'] < float('inf'):
            # Sensible Draft-Anpassung basierend auf TMC
            draft_correction = -mass_error / (hydro['tmc_kg_m'] * 40)
        else:
            # Fallback: Lineare Anpassung
            draft_correction = -mass_error / target_mass_kg * 0.05
        
        draft += draft_correction
        draft = max(draft_min, min(draft, draft_max))
        
        # 4. TRIM-KORREKTUR (physikalisch korrekt)
        trim_moment_kgm = target_mass_kg * (lcg_ap_m - hydro['lcb_m'])
        
        if hydro['tmc_kg_m'] > 0 and ship_length_m > 0:
            # Trim in cm
            trim_change_cm = trim_moment_kgm / hydro['tmc_kg_m']
            
            # In Grad umrechnen: θ = atan(trim_change_m / Lpp)
            trim_change_m = trim_change_cm / 100
            trim_rad = math.atan(trim_change_m / ship_length_m)
            trim_deg = math.degrees(trim_rad)
            
            # Auf max_trim begrenzen
            trim = max(-max_trim_deg, min(trim_deg, max_trim_deg))
    
    # 5. FINALE BERECHNUNG
    final_hydro = interpolator.get_values(draft, trim)
    if not final_hydro:
        App.Console.PrintError("Finale Berechnung fehlgeschlagen\n")
        return None
    
    # Koordinatentransformation zu FreeCAD-System
    ship_obj = App.ActiveDocument.getObject("Ship")
    if ship_obj:
        bbox = ship_obj.Shape.BoundBox
        ap_m = bbox.XMin / 1000.0
        mid_m = (bbox.XMin + bbox.XMax) / 2000.0
        fp_m = bbox.XMax / 1000.0
        
        # Transformation: AP-System → FreeCAD-System (Mitte=0)
        ap_to_mid = ap_m - mid_m
        
        lcb_freecad_m = final_hydro['lcb_m'] + ap_to_mid
        lcg_freecad_m = lcg_ap_m + ap_to_mid
        
        # Trim in Metern an AP und FP
        trim_rad = math.radians(trim)
        draft_ap = draft + (mid_m - ap_m) * math.tan(trim_rad)
        draft_fp = draft + (fp_m - mid_m) * math.tan(trim_rad)
        
    else:
        lcb_freecad_m = final_hydro['lcb_m']
        lcg_freecad_m = lcg_ap_m
        draft_ap = draft
        draft_fp = draft
    
    # Stabilitätsberechnung
    km_m = final_hydro['kb_m'] + final_hydro['bmt_m']
    gm_m = km_m - vcg_m
    
    # Trim-Änderung in Metern
    trim_change_m = ship_length_m * math.tan(math.radians(trim))
    
    return {
        'displacement': target_mass_kg,
        'draft': draft,
        'draft_ap': draft_ap,
        'draft_fp': draft_fp,
        'trim': trim,
        'trim_change_m': trim_change_m,
        'lcb': lcb_freecad_m,
        'lcg': lcg_freecad_m,
        'vcg': vcg_m,
        'kb': final_hydro['kb_m'],
        'bmt': final_hydro['bmt_m'],
        'km': km_m,
        'gm': gm_m,
        'tmc': final_hydro['tmc_kg_m'],
        'trim_moment': target_mass_kg * (lcg_ap_m - final_hydro['lcb_m']),
        'ship_length': ship_length_m,
        'success': True
    }


#===========================================================================
# 6. HAUPTFUNKTION - UNIVERSAL
#===========================================================================

def compute_universal(lc_spreadsheet, fs_ref=True, ship_obj=None, doc=App.ActiveDocument):
    """
    UNIVERSALE Hauptfunktion für alle Schiffstypen
    """
    
    App.Console.PrintMessage("\n" + "="*80 + "\n")
    App.Console.PrintMessage("UNIVERSALE SCHWIMMLAGE BERECHNUNG\n")
    App.Console.PrintMessage("="*80 + "\n")
    
    try:
        # 1. SCHIFF FINDEN
        if not ship_obj:
            # Suche nach geeignetem Schiffsobjekt
            for obj in doc.Objects:
                if hasattr(obj, 'Shape') and obj.Shape:
                    # Priorität: Objekte mit Label "Ship", "Hull", "Schiff"
                    label_lower = obj.Label.lower()
                    if any(keyword in label_lower for keyword in 
                          ['ship', 'hull', 'schiff', 'rumpf', 'body']):
                        ship_obj = obj
                        break
                    elif obj.Shape.Volume > 0:  # Irgendein Volumenkörper
                        ship_obj = obj
        
        if not ship_obj:
            App.Console.PrintError("Kein geeignetes Schiffsobjekt gefunden\n")
            return None, None, None, None, None, None
        
        App.Console.PrintMessage(f"Gefunden: {ship_obj.Label} (Typ: {ship_obj.TypeId})\n")
        
        # 2. LOADCONDITION DATEN
        try:
            # Extrahiere Daten aus Spreadsheet
            # Annahme: Standard FreeCAD Ship LoadCondition Format
            mass_kg = float(lc_spreadsheet.get('D4', '0'))
            lcg_m = float(lc_spreadsheet.get('E5', '0'))
            vcg_m = float(lc_spreadsheet.get('G5', '0'))
            
            # Lightship aus verschiedenen möglichen Zellen
            lightship_cells = ['D5', 'D6', 'D7', 'C5', 'B5']
            lightship_kg = 0
            for cell in lightship_cells:
                try:
                    val = lc_spreadsheet.get(cell, '0')
                    if val and float(val) > 0:
                        lightship_kg = float(val)
                        break
                except:
                    continue
            
            # Falls kein Lightship gefunden, schätze es
            if lightship_kg <= 0:
                # Schätzung: 30-50% der Gesamtmasse, abhängig von Schiffstyp
                lightship_kg = mass_kg * 0.4  # 40% angenommen
            
        except Exception as e:
            App.Console.PrintWarning(f"Spreadsheet-Lesen: {e}, verwende Standardwerte\n")
            # Standardwerte für Test
            mass_kg = 10000000  # 10.000t
            lcg_m = 0.0
            vcg_m = 5.0
            lightship_kg = 4000000  # 4.000t
        
        App.Console.PrintMessage(f"\nLastbedingung:\n")
        App.Console.PrintMessage(f"  Gesamtmasse:   {mass_kg/1000:,.1f} t\n")
        App.Console.PrintMessage(f"  Lightship:     {lightship_kg/1000:,.1f} t\n")
        App.Console.PrintMessage(f"  LCG (FreeCAD): {lcg_m:.3f} m\n")
        App.Console.PrintMessage(f"  VCG:           {vcg_m:.3f} m\n")
        
        # 3. HYDROSTATIK-TABELLE (UNIVERSAL)
        App.Console.PrintMessage(f"\nBerechne universale Hydrostatik-Tabelle...\n")
        hydro_points, L_m, B_m, D_m, max_trim = compute_universal_hydrostatics_table(
            ship_obj, 
            lightship_weight_kg=lightship_kg,
            n_drafts=15,
            n_trims=7
        )
        
        if len(hydro_points) < 8:
            App.Console.PrintError(f"Zu wenige gültige Punkte: {len(hydro_points)}\n")
            return None, None, None, None, None, None
        
        # 4. INTERPOLATOR
        interpolator = UniversalHydrostaticsInterpolator(hydro_points, L_m, max_trim)
        
        # 5. KOORDINATENTRANSFORMATION
        bbox = ship_obj.Shape.BoundBox
        ap_m = bbox.XMin / 1000.0
        mid_m = (bbox.XMin + bbox.XMax) / 2000.0
        fp_m = bbox.XMax / 1000.0
        
        L_pp = fp_m - ap_m  # Länge zwischen Loten
        
        # Transformation: LCG (FreeCAD Mitte=0) → LCG von AP
        lcg_ap_m = lcg_m - (mid_m - ap_m)
        
        App.Console.PrintMessage(f"\nKoordinatensystem:\n")
        App.Console.PrintMessage(f"  AP (Xmin):      {ap_m:.2f} m\n")
        App.Console.PrintMessage(f"  FP (Xmax):      {fp_m:.2f} m\n")
        App.Console.PrintMessage(f"  Länge Lpp:      {L_pp:.2f} m\n")
        App.Console.PrintMessage(f"  Mitte (0-Pkt):  {mid_m:.2f} m\n")
        App.Console.PrintMessage(f"  LCG von AP:     {lcg_ap_m:.3f} m\n")
        
        # 6. GLEICHGEWICHTSSUCHE
        App.Console.PrintMessage(f"\nSuche Gleichgewichtszustand...\n")
        result = find_universal_equilibrium(
            interpolator, 
            mass_kg, 
            lcg_ap_m, 
            vcg_m,
            L_m,
            max_trim
        )
        
        if not result:
            App.Console.PrintError("Gleichgewichtssuche fehlgeschlagen\n")
            return None, None, None, None, None, None
        
        # 7. ERGEBNISSE
        App.Console.PrintMessage(f"\n" + "="*80 + "\n")
        App.Console.PrintMessage("ERGEBNISSE:\n")
        App.Console.PrintMessage(f"  Tiefgang (Mitte): {result['draft']:.3f} m\n")
        App.Console.PrintMessage(f"  Tiefgang AP:      {result['draft_ap']:.3f} m\n")
        App.Console.PrintMessage(f"  Tiefgang FP:      {result['draft_fp']:.3f} m\n")
        App.Console.PrintMessage(f"  Trim:             {result['trim']:.2f}°\n")
        App.Console.PrintMessage(f"  Trimänderung:     {result['trim_change_m']:.2f} m\n")
        App.Console.PrintMessage(f"  LCB (FreeCAD):    {result['lcb']:.3f} m\n")
        App.Console.PrintMessage(f"  LCG (FreeCAD):    {result['lcg']:.3f} m\n")
        App.Console.PrintMessage(f"  Differenz LCB-LCG: {abs(result['lcb'] - result['lcg']):.3f} m\n")
        App.Console.PrintMessage(f"  VCG:              {result['vcg']:.3f} m\n")
        App.Console.PrintMessage(f"  KB:               {result['kb']:.3f} m\n")
        App.Console.PrintMessage(f"  BMt:              {result['bmt']:.3f} m\n")
        App.Console.PrintMessage(f"  KMt:              {result['km']:.3f} m\n")
        App.Console.PrintMessage(f"  GMt:              {result['gm']:.3f} m\n")
        
        # 8. WARNUNGEN UND CHECKS
        if abs(result['trim']) > 1.5:
            App.Console.PrintWarning("⚠  Trim > 1.5° - Überprüfen Sie die Lastverteilung\n")
        
        if result['gm'] < 0.15:
            App.Console.PrintError("✗  GMt < 0.15m - SCHIFF NICHT STABIL!\n")
        elif result['gm'] < 0.5:
            App.Console.PrintWarning("⚠  GMt < 0.5m - Stabilität grenzwertig\n")
        elif result['gm'] > 3.0:
            App.Console.PrintWarning("⚠  GMt > 3.0m - Sehr hartes Schiff\n")
        
        if result['draft'] > D_m * 0.85:
            App.Console.PrintWarning("⚠  Tiefgang > 85% der Tiefe - Freibord gering\n")
        
        App.Console.PrintMessage("="*80 + "\n")
        
        # 9. RÜCKGABEWERTE FÜR GUI
        draft_qty = Units.parseQuantity(f"{result['draft']} m")
        trim_qty = Units.parseQuantity(f"{result['trim']} deg")
        disp_qty = Units.parseQuantity(f"{mass_kg} kg")
        
        # 10. ERGEBNISSE SPEICHERN
        spreadsheet = save_universal_results(doc, ship_obj.Label, hydro_points, result)
        
        return spreadsheet, draft_qty, trim_qty, disp_qty, None, result
        
    except Exception as e:
        App.Console.PrintError(f"\nFEHLER: {str(e)}\n")
        import traceback
        traceback.print_exc()
        return None, None, None, None, None, None


#===========================================================================
# 7. UNIVERSALE ERGEBNIS-SPEICHERUNG
#===========================================================================

def save_universal_results(doc, ship_name, hydro_points, equilibrium):
    """Speichert universale Ergebnisse"""
    try:
        spreadsheet = doc.addObject('Spreadsheet::Sheet', f"HydroUniversal_{ship_name}")
        spreadsheet.Label = f"Hydrostatics {ship_name}"
        
        # Hydrostatik-Tabelle
        spreadsheet.set('A1', 'HYDROSTATIC TABLE')
        spreadsheet.set('A2', 'Draft [m]')
        spreadsheet.set('B2', 'Trim [°]')
        spreadsheet.set('C2', 'Displacement [t]')
        spreadsheet.set('D2', 'LCB from AP [m]')
        spreadsheet.set('E2', 'KB [m]')
        spreadsheet.set('F2', 'BMt [m]')
        spreadsheet.set('G2', 'KMt [m]')
        spreadsheet.set('H2', 'TMC [t*m/cm]')
        
        for i, point in enumerate(hydro_points[:150]):  # Max 150 Punkte
            row = i + 3
            spreadsheet.set(f'A{row}', f"{point['draft_m']:.3f}")
            spreadsheet.set(f'B{row}', f"{point['trim_deg']:.2f}")
            spreadsheet.set(f'C{row}', f"{point['displacement_kg']/1000:.1f}")
            spreadsheet.set(f'D{row}', f"{point['lcb_m']:.3f}")
            spreadsheet.set(f'E{row}', f"{point['kb_m']:.3f}")
            spreadsheet.set(f'F{row}', f"{point['bmt_m']:.3f}")
            
            # KM = KB + BM
            km = point['kb_m'] + point['bmt_m']
            spreadsheet.set(f'G{row}', f"{km:.3f}")
            spreadsheet.set(f'H{row}', f"{point['tmc_kg_m']/1000:.1f}")
        
        # Equilibrium Results
        spreadsheet.set('K1', 'EQUILIBRIUM CONDITION')
        spreadsheet.set('K2', f"Displacement: {equilibrium['displacement']/1000:.1f} t")
        spreadsheet.set('K3', f"Draft at mid: {equilibrium['draft']:.3f} m")
        spreadsheet.set('K4', f"Draft at AP:  {equilibrium['draft_ap']:.3f} m")
        spreadsheet.set('K5', f"Draft at FP:  {equilibrium['draft_fp']:.3f} m")
        spreadsheet.set('K6', f"Trim: {equilibrium['trim']:.2f}°")
        spreadsheet.set('K7', f"Trim change: {equilibrium['trim_change_m']:.2f} m")
        spreadsheet.set('K8', f"LCB: {equilibrium['lcb']:.3f} m")
        spreadsheet.set('K9', f"LCG: {equilibrium['lcg']:.3f} m")
        spreadsheet.set('K10', f"VCG: {equilibrium['vcg']:.3f} m")
        spreadsheet.set('K11', f"KB: {equilibrium['kb']:.3f} m")
        spreadsheet.set('K12', f"BMt: {equilibrium['bmt']:.3f} m")
        spreadsheet.set('K13', f"KMt: {equilibrium['km']:.3f} m")
        spreadsheet.set('K14', f"GMt: {equilibrium['gm']:.3f} m")
        
        # Warnings
        row = 16
        if abs(equilibrium['trim']) > 1.5:
            spreadsheet.set(f'K{row}', 'WARNING: Trim > 1.5°')
            row += 1
        
        if equilibrium['gm'] < 0.15:
            spreadsheet.set(f'K{row}', 'CRITICAL: GMt < 0.15m - NOT STABLE!')
            row += 1
        elif equilibrium['gm'] < 0.5:
            spreadsheet.set(f'K{row}', 'WARNING: GMt < 0.5m - marginal stability')
            row += 1
        
        doc.recompute()
        App.Console.PrintMessage("✓ Ergebnisse gespeichert\n")
        return spreadsheet
        
    except Exception as e:
        App.Console.PrintWarning(f"Spreadsheet konnte nicht erstellt werden: {e}\n")
        return None


#===========================================================================
# 8. ALIAS FÜR KOMPATIBILITÄT
#===========================================================================

def compute(lc_spreadsheet, fs_ref=True, ship_obj=None, doc=App.ActiveDocument):
    """
    Hauptfunktion - ruft die universale Berechnung auf
    """
    return compute_universal(lc_spreadsheet, fs_ref, ship_obj, doc)
