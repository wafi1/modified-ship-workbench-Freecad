#***************************************************************************
#*   Copyright (c) 2011, 2016 Jose Luis Cercos Pita <jlcercos@gmail.com>   *
#*                                                                         *
#*   FIXED:                                                                *
#*   BUG 1: Units.Quantity(val, "rad") → val * Units.Radian               *
#*   BUG 2: Same fix in var_trim=False branch                              *
#*   BUG 3: GZ return uses mm Quantities directly (no Units.Unit('m'))    *
#*   NEW:   analyze_solas_stability accepts gm_from_sheet parameter;       *
#*          curve-fit GM is only a last-resort fallback with clear warning  *
#***************************************************************************

import math
import FreeCAD as App
from FreeCAD import Vector, Matrix, Placement
import Part
from FreeCAD import Units
from .. import Instance as ShipInstance
from .. import WeightInstance
from .. import TankInstance
from ..shipHydrostatics import Tools as Hydrostatics


def __linspace(val0, val1, n):
    return [val0 + (val1 - val0) * i / (n - 1) for i in range(n)]


G = Units.parseQuantity("9.81 m/s^2")
MAX_EQUILIBRIUM_ITERS = 20
DENS = Units.parseQuantity("1025 kg/m^3")
DRAFT_RELAX_FACTOR = __linspace(1.0, 0.5, MAX_EQUILIBRIUM_ITERS)
TRIM_RELAX_FACTOR  = __linspace(1.0, 0.5, MAX_EQUILIBRIUM_ITERS)


# ---------------------------------------------------------------------------
# Unit helpers
# ---------------------------------------------------------------------------

def _m_to_freecad(value_m):
    """Convert metres (spreadsheet entry) to FreeCAD internal mm."""
    return Units.parseQuantity("{} m".format(value_m)).Value


def _parse_cog_from_sheet(lc):
    """Read COG from cells E5/F5/G5 [m] and return a Vector in mm."""
    return Vector(
        _m_to_freecad(float(lc.get('E5'))),
        _m_to_freecad(float(lc.get('F5'))),
        _m_to_freecad(float(lc.get('G5'))))


# ---------------------------------------------------------------------------
# Legacy path (individual weight / tank objects)
# ---------------------------------------------------------------------------

def weights_cog(weights):
    W     = Units.parseQuantity("0 kg")
    mom_x = Units.parseQuantity("0 kg*m")
    mom_y = Units.parseQuantity("0 kg*m")
    mom_z = Units.parseQuantity("0 kg*m")
    for w in weights:
        W     += w.Proxy.getMass(w)
        m      = w.Proxy.getMoment(w)
        mom_x += m[0];  mom_y += m[1];  mom_z += m[2]
    return Vector(mom_x / W, mom_y / W, mom_z / W), W * G


def solve(ship, weights, tanks, rolls, var_trim=True):
    COG, W = weights_cog(weights)
    TW     = Units.parseQuantity("0 kg")
    VOLS   = []
    for t in tanks:
        vol = t[0].Proxy.getVolume(t[0], t[2])
        VOLS.append(vol)
        TW += vol * t[1]
    TW = TW * G

    points = []
    for i, roll in enumerate(rolls):
        App.Console.PrintMessage("{0} / {1}\n".format(i + 1, len(rolls)))
        point = solve_point(W, COG, TW, VOLS, ship, tanks, roll, var_trim)
        if point is None:
            return []
        points.append(point)
    return points


def solve_point(W, COG, TW, VOLS, ship, tanks, roll, var_trim=True):
    max_draft = Units.Quantity(ship.Shape.BoundBox.ZMax, Units.Length)
    draft     = ship.Draft
    max_disp  = Units.Quantity(ship.Shape.Volume, Units.Volume) * DENS * G

    if max_disp < W + TW:
        msg = App.Qt.translate("ship_console",
            "Too much weight! The ship will never displace water enough")
        App.Console.PrintError(msg + ' ({} vs. {})\n'.format(
            (max_disp / G).UserString, ((W + TW) / G).UserString))
        return None

    trim = Units.parseQuantity("0 deg")
    R_y  = Units.Quantity(0.0, Units.Length)
    R_z  = Units.Quantity(0.0, Units.Length)

    for i in range(MAX_EQUILIBRIUM_ITERS):
        disp_mass, B, _ = Hydrostatics.displacement(ship, draft, roll, trim)
        disp = disp_mass * G

        mom_x = Units.Quantity(COG.x, Units.Length) * W
        mom_y = Units.Quantity(COG.y, Units.Length) * W
        mom_z = Units.Quantity(COG.z, Units.Length) * W
        for j, t in enumerate(tanks):
            tw       = VOLS[j] * t[1] * G
            tank_cog = t[0].Proxy.getCoG(t[0], VOLS[j], roll, trim)
            mom_x += Units.Quantity(tank_cog.x, Units.Length) * tw
            mom_y += Units.Quantity(tank_cog.y, Units.Length) * tw
            mom_z += Units.Quantity(tank_cog.z, Units.Length) * tw
        cog_x = mom_x / (W + TW)
        cog_y = mom_y / (W + TW)
        cog_z = mom_z / (W + TW)

        draft_err    = -DRAFT_RELAX_FACTOR[i] * ((disp - W - TW) / max_disp).Value
        R_x = cog_x - Units.Quantity(B.x, Units.Length)
        R_y = cog_y - Units.Quantity(B.y, Units.Length)
        R_z = cog_z - Units.Quantity(B.z, Units.Length)

        trim_err_rad = 0.0
        if var_trim:
            c  = math.cos(trim.getValueAs('rad'))
            s  = math.sin(trim.getValueAs('rad'))
            rx = c * R_x - s * R_z
            _, _, fs_shape = Hydrostatics.floatingArea(ship, draft, roll, trim)
            if fs_shape is not None:
                bml, _ = Hydrostatics.BML(ship, fs_shape, draft, roll, trim,
                                          precomputed_disp=(disp_mass, B, _))
            else:
                bml = ship.Length * math.cos(trim.getValueAs('rad'))
            if bml < -B.y:
                bml = -B.y
            bml_m = float(bml.getValueAs('m')) if hasattr(bml, 'getValueAs') else float(bml)
            rx_m  = float(rx.getValueAs('m'))
            if abs(bml_m) > 1e-10:
                trim_err_rad = -TRIM_RELAX_FACTOR[i] * rx_m / bml_m

        if abs(draft_err) < 1E-2 and abs(trim_err_rad) < 1E-4:
            break

        draft += draft_err * max_draft
        trim  += trim_err_rad * Units.Radian

        _draft_m  = draft.getValueAs('m').Value
        _trim_deg = abs(trim.getValueAs('deg').Value)
        _bbox_m   = ship.Shape.BoundBox.ZMax / 1000.0
        if _draft_m > _bbox_m * 1.05 or _draft_m < -_bbox_m * 0.5:
            App.Console.PrintWarning(
                "Solver diverged at roll={:.1f} deg: draft={:.2f} m outside "
                "ship bounds ({:.2f} m) – angle skipped.\n".format(
                    roll.getValueAs('deg').Value, _draft_m, _bbox_m))
            return None
        if _trim_deg > 60.0:
            App.Console.PrintWarning(
                "Solver diverged at roll={:.1f} deg: trim={:.1f} deg "
                "unrealistic – angle skipped.\n".format(
                    roll.getValueAs('deg').Value, _trim_deg))
            return None

    c = math.cos(roll.getValueAs('rad'))
    s = math.sin(roll.getValueAs('rad'))
    return c * R_y - s * R_z, draft, trim


# ---------------------------------------------------------------------------
# New spreadsheet-based path
# ---------------------------------------------------------------------------

def gz(lc, rolls, var_trim=True):
    """Compute GZ curve from a LoadCondition spreadsheet."""
    doc = lc.Document

    ship_label = None
    for cell in ('B2', 'B1'):
        try:
            ship_label = lc.get(cell)
            break
        except Exception:
            continue

    if not ship_label:
        App.Console.PrintError("Cannot find Ship reference in LoadCondition!\n")
        return [], None, [], [], {}

    ships = doc.getObjectsByLabel(ship_label)
    if len(ships) != 1:
        App.Console.PrintError(
            "{} ship instance(s) labeled '{}' – expected 1.\n".format(
                len(ships), ship_label))
        return [], None, [], [], {}

    ship = ships[0]
    if ship is None or "IsShip" not in ship.PropertiesList:
        App.Console.PrintError("'{}' is not a valid ship\n".format(ship_label))
        return [], None, [], [], {}

    try:
        total_mass_kg = float(lc.get('D4'))
        W   = Units.parseQuantity("{} kg".format(total_mass_kg)) * G
        COG = _parse_cog_from_sheet(lc)

        try:
            fs_moment = float(lc.get('K4'))
        except Exception:
            fs_moment = 0.0

        # Read GM directly from G4
        try:
            gm_from_sheet = float(lc.get('G4'))
        except Exception:
            gm_from_sheet = None

        solas_data = {
            'total_mass_kg': total_mass_kg,
            'cog_x': COG.x, 'cog_y': COG.y, 'cog_z': COG.z,
            'fs_moment': fs_moment,
            'ship_label': ship.Label, 'lc_label': lc.Label,
        }
        App.Console.PrintMessage(
            "LoadCondition: {:.0f} kg  COG ({:.1f}, {:.1f}, {:.1f}) mm\n".format(
                total_mass_kg, COG.x, COG.y, COG.z))
    except Exception as e:
        App.Console.PrintError(
            "Error reading LoadCondition (D4=mass, E5/F5/G5=COG): {}\n".format(e))
        return [], None, [], [], {}

    points = solve_direct(ship, W, COG, rolls, var_trim)
    if points:
        solas_data.update(analyze_solas_stability(
            points, rolls, ship, COG, gm_from_sheet=gm_from_sheet))
    return points, ship, [], [], solas_data


def solve_direct(ship, W, COG, rolls, var_trim=True):
    points = []
    for i, roll in enumerate(rolls):
        App.Console.PrintMessage("{0} / {1}\n".format(i + 1, len(rolls)))
        point = solve_point_direct(W, COG, ship, roll, var_trim)
        if point is None:
            return []
        points.append(point)
    return points


def solve_point_direct(W, COG, ship, roll, var_trim=True):
    """GZ from total weight + COG (spreadsheet path).
    Returns (GZ [mm Quantity], draft, trim, disp_mass_kg) or None.
    """
    max_draft = Units.Quantity(ship.Shape.BoundBox.ZMax, Units.Length)
    draft     = ship.Draft
    max_disp  = Units.Quantity(ship.Shape.Volume, Units.Volume) * DENS * G

    if max_disp < W:
        msg = App.Qt.translate("ship_console",
            "Too much weight! The ship will never displace water enough")
        App.Console.PrintError(msg + ' ({} vs. {})\n'.format(
            (max_disp / G).UserString, (W / G).UserString))
        return None

    trim = Units.parseQuantity("0 deg")
    R_y  = Units.Quantity(0.0, Units.Length)
    R_z  = Units.Quantity(0.0, Units.Length)

    for i in range(MAX_EQUILIBRIUM_ITERS):
        disp_mass, B, _ = Hydrostatics.displacement(ship, draft, roll, trim)
        disp = disp_mass * G

        if B.x == 0.0 and B.y == 0.0 and B.z == 0.0 and disp_mass.Value == 0.0:
            App.Console.PrintWarning(
                "Underwater shape empty at draft={}, roll={}, trim={}\n".format(
                    draft, roll, trim))
            return None

        cog_x = Units.Quantity(COG.x, Units.Length)
        cog_y = Units.Quantity(COG.y, Units.Length)
        cog_z = Units.Quantity(COG.z, Units.Length)

        draft_err = -DRAFT_RELAX_FACTOR[i] * ((disp - W) / max_disp).Value
        R_x = cog_x - Units.Quantity(B.x, Units.Length)
        R_y = cog_y - Units.Quantity(B.y, Units.Length)
        R_z = cog_z - Units.Quantity(B.z, Units.Length)

        trim_err_rad = 0.0
        if var_trim:
            c  = math.cos(trim.getValueAs('rad'))
            s  = math.sin(trim.getValueAs('rad'))
            rx = c * R_x - s * R_z
            _, _, fs_shape = Hydrostatics.floatingArea(ship, draft, roll, trim)
            if fs_shape is not None:
                bml, _ = Hydrostatics.BML(ship, fs_shape, draft, roll, trim,
                                          precomputed_disp=(disp_mass, B, _))
            else:
                bml = ship.Length * math.cos(trim.getValueAs('rad'))
            if bml < -B.y:
                bml = -B.y
            bml_m = float(bml.getValueAs('m')) if hasattr(bml, 'getValueAs') else float(bml)
            rx_m  = float(rx.getValueAs('m'))
            if abs(bml_m) > 1e-10:
                trim_err_rad = -TRIM_RELAX_FACTOR[i] * rx_m / bml_m

        if abs(draft_err) < 1E-2 and abs(trim_err_rad) < 1E-4:
            break

        draft += draft_err * max_draft
        trim  += trim_err_rad * Units.Radian

        _draft_m  = draft.getValueAs('m').Value
        _trim_deg = abs(trim.getValueAs('deg').Value)
        _bbox_m   = ship.Shape.BoundBox.ZMax / 1000.0
        if _draft_m > _bbox_m * 1.05 or _draft_m < -_bbox_m * 0.5:
            App.Console.PrintWarning(
                "Solver diverged at roll={:.1f} deg: draft={:.2f} m outside "
                "ship bounds ({:.2f} m) – angle skipped.\n".format(
                    roll.getValueAs('deg').Value, _draft_m, _bbox_m))
            return None
        if _trim_deg > 60.0:
            App.Console.PrintWarning(
                "Solver diverged at roll={:.1f} deg: trim={:.1f} deg "
                "unrealistic – angle skipped.\n".format(
                    roll.getValueAs('deg').Value, _trim_deg))
            return None

    c = math.cos(roll.getValueAs('rad'))
    s = math.sin(roll.getValueAs('rad'))
    try:
        disp_mass_kg = float(disp_mass.getValueAs('kg').Value)
    except Exception:
        disp_mass_kg = 0.0
    return c * R_y - s * R_z, draft, trim, disp_mass_kg


# ---------------------------------------------------------------------------
# SOLAS analysis
# ---------------------------------------------------------------------------

def analyze_solas_stability(points, rolls, ship, COG, gm_from_sheet=None):
    """Compute SOLAS criteria from the computed GZ points.

    Parameters
    ----------
    gm_from_sheet : float or None
        GM value read directly from the LoadCondition spreadsheet (cell G4).
        When provided this is used as-is.  The curve-fit estimate is computed
        only as a last resort when this is None, and a clear warning is issued.
    """
    try:
        import numpy as np
    except ImportError:
        App.Console.PrintWarning("NumPy not available – SOLAS skipped.\n")
        return {}

    if hasattr(np, 'trapezoid'):
        _trapz = np.trapezoid
    elif hasattr(np, 'trapz'):
        _trapz = np.trapz
    else:
        def _trapz(y, x):
            return sum((x[i+1]-x[i])*(y[i]+y[i+1])/2.0 for i in range(len(x)-1))

    roll_deg = []
    for a in rolls:
        if hasattr(a, 'getValueAs'):
            roll_deg.append(a.getValueAs('deg').Value)
        else:
            roll_deg.append(math.degrees(float(a)))
    roll_deg = np.array(roll_deg)

    gz_m = []
    for point in points:
        gz = point[0]
        if hasattr(gz, 'getValueAs'):
            gz_m.append(float(gz.getValueAs('m').Value))
        else:
            gz_m.append(float(gz))
    gz_m = np.array(gz_m)

    if len(gz_m) == 0:
        return {}

    roll_rad = np.radians(roll_deg)

    max_idx         = int(np.argmax(gz_m))
    max_gz          = float(gz_m[max_idx])
    max_gz_angle    = float(roll_deg[max_idx])
    vanishing_angle = float(roll_deg[-1])

    for i in range(max_idx + 1, len(gz_m)):
        if gz_m[i] <= 0.0 and gz_m[i-1] > 0.0:
            x1, y1 = roll_rad[i-1], gz_m[i-1]
            x2, y2 = roll_rad[i],   gz_m[i]
            vanishing_angle = float(np.degrees(x1 + (x2-x1)*(-y1)/(y2-y1)))
            break

    def _area(a0, a1):
        a1 = min(a1, vanishing_angle)
        if a1 <= a0:
            return 0.0
        ang = np.linspace(np.radians(a0), np.radians(a1), 200)
        return float(_trapz(np.interp(ang, roll_rad, gz_m), ang))

    area_0_30  = _area(0,  30)
    area_0_40  = _area(0,  40)
    area_30_40 = _area(30, 40)
    gz_at_30   = float(np.interp(np.radians(30), roll_rad, gz_m))

    # ── GM: spreadsheet value takes absolute priority ─────────────────────
    gm_source = 'spreadsheet (G4)'
    if gm_from_sheet is not None:
        GM0 = float(gm_from_sheet)
        App.Console.PrintMessage(
            "GM0 = {:.3f} m  (read from LoadCondition G4)\n".format(GM0))
    else:
        # Last-resort fallback: slope of GZ curve at small angles.
        # This is known to differ significantly from the true GM in many cases.
        GM0 = 0.0
        small = (roll_deg > 0) & (roll_deg < 10)
        if np.sum(small) >= 2:
            xs, ys = roll_rad[small], gz_m[small]
            A   = np.vstack([xs, np.ones(len(xs))]).T
            GM0 = float(np.linalg.lstsq(A, ys, rcond=None)[0][0])
        if GM0 == 0.0:
            pos = np.where(roll_deg > 0)[0]
            if len(pos):
                phi = roll_rad[pos[0]]
                GM0 = float(gz_m[pos[0]] / phi) if phi > 1e-6 else 0.0
        gm_source = 'curve fit FALLBACK – add G4 to LoadCondition!'
        App.Console.PrintWarning(
            "GM0 not supplied (lc_info missing 'gm' / G4 unreadable).\n"
            "Curve-fit estimate = {:.3f} m.  This value may be unreliable.\n"
            "Add GM to cell G4 of the LoadCondition spreadsheet.\n".format(GM0))

    criteria = {
        'area_0_30':    {'value': area_0_30,    'required': 0.055, 'passed': area_0_30    >= 0.055},
        'area_0_40':    {'value': area_0_40,    'required': 0.090, 'passed': area_0_40    >= 0.090},
        'area_30_40':   {'value': area_30_40,   'required': 0.030, 'passed': area_30_40   >= 0.030},
        'gz_at_30':     {'value': gz_at_30,     'required': 0.200, 'passed': gz_at_30     >= 0.200},
        'max_gz_angle': {'value': max_gz_angle, 'required': 25.0,  'passed': max_gz_angle >= 25.0 },
        'GM0':          {'value': GM0,          'required': 0.150, 'passed': GM0          >= 0.150},
    }
    passed = sum(1 for c in criteria.values() if c['passed'])
    return {
        'max_gz': max_gz, 'max_gz_angle': max_gz_angle,
        'vanishing_angle': vanishing_angle,
        'area_0_30': area_0_30, 'area_0_40': area_0_40, 'area_30_40': area_30_40,
        'gz_at_30': gz_at_30,
        'GM0': GM0, 'gm_source': gm_source,
        'solas_criteria': criteria,
        'passed_count': passed, 'total_criteria': len(criteria),
        'compliant': passed == len(criteria),
    }


def print_solas_report(solas_data):
    if not solas_data:
        return
    sep  = "=" * 70
    thin = "-" * 70
    App.Console.PrintMessage("\n{}\n".format(sep))
    App.Console.PrintMessage("SOLAS / IMO A.749(18) STABILITY ANALYSIS\n")
    App.Console.PrintMessage("{}\n".format(sep))
    App.Console.PrintMessage("Ship           : {}\n".format(solas_data.get('ship_label', 'N/A')))
    App.Console.PrintMessage("Load condition : {}\n".format(solas_data.get('lc_label', 'N/A')))
    App.Console.PrintMessage("Total mass     : {:.1f} kg\n".format(solas_data.get('total_mass_kg', 0)))
    App.Console.PrintMessage("COG            : ({:.3f}, {:.3f}, {:.3f}) m\n".format(
        solas_data.get('cog_x', 0)/1000,
        solas_data.get('cog_y', 0)/1000,
        solas_data.get('cog_z', 0)/1000))
    App.Console.PrintMessage("{}\n".format(thin))
    for lbl, key, fmt in [
        ("Max GZ",              'max_gz',          "{:.3f} m"),
        ("Angle of max GZ",     'max_gz_angle',    "{:.1f} deg"),
        ("Vanishing stability", 'vanishing_angle', "{:.1f} deg"),
        ("GZ at 30 deg",        'gz_at_30',        "{:.3f} m"),
        ("Initial GM",          'GM0',             "{:.3f} m  [{}]"),
        ("Area  0-30 deg",      'area_0_30',       "{:.4f} m*rad  (min 0.055)"),
        ("Area  0-40 deg",      'area_0_40',       "{:.4f} m*rad  (min 0.090)"),
        ("Area 30-40 deg",      'area_30_40',      "{:.4f} m*rad  (min 0.030)"),
    ]:
        if key == 'GM0':
            val = fmt.format(solas_data.get(key, 0),
                             solas_data.get('gm_source', '?'))
        else:
            val = fmt.format(solas_data.get(key, 0))
        App.Console.PrintMessage("  {:22s} : {}\n".format(lbl, val))
    App.Console.PrintMessage("{}\n".format(thin))
    lmap = {
        'area_0_30':    'Area  0-30 deg', 'area_0_40':    'Area  0-40 deg',
        'area_30_40':   'Area 30-40 deg', 'gz_at_30':     'GZ at 30 deg  ',
        'max_gz_angle': 'Angle max GZ  ', 'GM0':          'Initial GM    ',
    }
    for name, crit in solas_data.get('solas_criteria', {}).items():
        App.Console.PrintMessage("  {} : {:.4f} / {:.3f}  [{}]\n".format(
            lmap.get(name, name), crit['value'], crit['required'],
            "PASS" if crit['passed'] else "FAIL"))
    p, t = solas_data.get('passed_count', 0), solas_data.get('total_criteria', 0)
    App.Console.PrintMessage("{}\n".format(sep))
    App.Console.PrintMessage("SUMMARY: {}/{} – {}\n".format(
        p, t, "COMPLIANT" if solas_data.get('compliant') else "NON-COMPLIANT"))
    App.Console.PrintMessage("{}\n\n".format(sep))
