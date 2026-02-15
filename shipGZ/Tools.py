#***************************************************************************
#*                                                                         *
#*   Copyright (c) 2011, 2016 Jose Luis Cercos Pita <jlcercos@gmail.com>   *
#*                                                                         *
#*   This program is free software; you can redistribute it and/or modify  *
#*   it under the terms of the GNU Lesser General Public License (LGPL)    *
#*   as published by the Free Software Foundation; either version 2 of     *
#*   the License, or (at your option) any later version.                   *
#*   for detail see the LICENCE text file.                                 *
#*                                                                         *
#*   This program is distributed in the hope that it will be useful,       *
#*   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
#*   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
#*   GNU Library General Public License for more details.                  *
#*                                                                         *
#*   You should have received a copy of the GNU Library General Public     *
#*   License along with this program; if not, write to the Free Software   *
#*   Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  *
#*   USA                                                                   *
#*                                                                         *
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
TRIM_RELAX_FACTOR = __linspace(1.0, 0.5, MAX_EQUILIBRIUM_ITERS)


def weights_cog(weights):
    W = Units.parseQuantity("0 kg")
    mom_x = Units.parseQuantity("0 kg*m")
    mom_y = Units.parseQuantity("0 kg*m")
    mom_z = Units.parseQuantity("0 kg*m")
    for w in weights:
        W += w.Proxy.getMass(w)
        m = w.Proxy.getMoment(w)
        mom_x += m[0]
        mom_y += m[1]
        mom_z += m[2]
    W = W
    return Vector(mom_x / W, mom_y / W, mom_z / W), W * G


def solve(ship, weights, tanks, rolls, var_trim=True):
    """Compute the ship GZ stability curve

    Position arguments:
    ship -- Ship object
    weights -- List of weights to consider
    tanks -- List of tanks to consider (each one should be a tuple with the
    tank instance, the density of the fluid inside, and the filling level ratio)
    rolls -- List of roll angles

    Keyword arguments:
    var_trim -- True if the equilibrium trim should be computed for each roll
    angle, False if null trim angle can be used instead.

    Returned value:
    List of GZ curve points. Each point contains the GZ stability length, the
    equilibrium draft, and the equilibrium trim angle (0 deg if var_trim is
    False)
    """
    COG, W = weights_cog(weights)

    # Get the tanks weight
    TW = Units.parseQuantity("0 kg")
    VOLS = []
    for t in tanks:
        # t[0] = tank object
        # t[1] = load density
        # t[2] = filling level
        vol = t[0].Proxy.getVolume(t[0], t[2])
        VOLS.append(vol)
        TW += vol * t[1]
    TW = TW * G

    points = []
    for i,roll in enumerate(rolls):
        App.Console.PrintMessage("{0} / {1}\n".format(i + 1, len(rolls)))
        point = solve_point(W, COG, TW, VOLS,
                            ship, tanks, roll, var_trim)
        if point is None:
            return []
        points.append(point)

    return points


def solve_point(W, COG, TW, VOLS, ship, tanks, roll, var_trim=True):
    """ Compute the ship GZ value.
    @param W Empty ship weight.
    @param COG Empty ship Center of mass.
    @param TW Tanks weights.
    @param VOLS List of tank volumes.
    @param tanks Considered tanks.
    @param roll Roll angle.
    @param var_trim True if the trim angle should be recomputed at each roll
    angle, False otherwise.
    @return GZ value, equilibrium draft, and equilibrium trim angle (0 if
    variable trim has not been requested)
    """    
    # Look for the equilibrium draft (and eventually the trim angle too)
    max_draft = Units.Quantity(ship.Shape.BoundBox.ZMax, Units.Length)
    draft = ship.Draft
    max_disp = Units.Quantity(ship.Shape.Volume, Units.Volume) * DENS * G
    if max_disp < W + TW:
        msg = App.Qt.translate(
            "ship_console",
            "Too much weight! The ship will never displace water enough")
        App.Console.PrintError(msg + ' ({} vs. {})\n'.format(
            (max_disp / G).UserString, ((W + TW) / G).UserString))
        return None

    trim = Units.parseQuantity("0 deg")
    for i in range(MAX_EQUILIBRIUM_ITERS):
        # Get the displacement, and the bouyance application point
        disp, B, _ = Hydrostatics.displacement(ship,
                                               draft,
                                               roll,
                                               trim)
        disp *= G

        # Add the tanks effect on the center of gravity
        mom_x = Units.Quantity(COG.x, Units.Length) * W
        mom_y = Units.Quantity(COG.y, Units.Length) * W
        mom_z = Units.Quantity(COG.z, Units.Length) * W
        for j,t in enumerate(tanks):
            tank_weight = VOLS[j] * t[1] * G
            tank_cog = t[0].Proxy.getCoG(t[0], VOLS[j], roll, trim)
            mom_x += Units.Quantity(tank_cog.x, Units.Length) * tank_weight
            mom_y += Units.Quantity(tank_cog.y, Units.Length) * tank_weight
            mom_z += Units.Quantity(tank_cog.z, Units.Length) * tank_weight
        cog_x = mom_x / (W + TW)
        cog_y = mom_y / (W + TW)
        cog_z = mom_z / (W + TW)
        # Compute the errors
        draft_err = -DRAFT_RELAX_FACTOR[i] * ((disp - W - TW) / max_disp).Value
        R_x = cog_x - Units.Quantity(B.x, Units.Length)
        R_y = cog_y - Units.Quantity(B.y, Units.Length)
        R_z = cog_z - Units.Quantity(B.z, Units.Length)
        if not var_trim:
            trim_err = 0.0
        else:
            c = math.cos(trim.getValueAs('rad'))
            s = math.sin(trim.getValueAs('rad'))
            rx = c * R_x - s * R_z
            # We need the BMl to estimate the required angle change
            _, _, fs_shape = Hydrostatics.floatingArea(ship, draft, roll, trim)
            if fs_shape is not None:
                bml, _ = Hydrostatics.BML(ship, fs_shape, draft, roll, trim)
            else:
                bml = ship.Length * math.cos(trim.getValueAs('rad').Value)
            if bml < -B.y:
                bml = -B.y
            # We approximate tan(alpha) = alpha, which is fine for small angles
            trim_err = -TRIM_RELAX_FACTOR[i] * rx / bml

        # Check if we can tolerate the errors
        if abs(draft_err) < 1E-2 and abs(trim_err) < 1E-4:
            break

        # Get the new draft and trim
        draft += draft_err * max_draft
        trim += trim_err * Units.Radian

    # GZ should be provided in the Free surface oriented frame of reference
    c = math.cos(roll.getValueAs('rad'))
    s = math.sin(roll.getValueAs('rad'))
    return c * R_y - s * R_z, draft, trim



def gz(lc, rolls, var_trim=True):
    """Compute the ship GZ stability curve - MODIFIED for new LoadCondition format

    Position arguments:
    lc -- Load condition spreadsheet (NEW FORMAT)
    rolls -- List of roll angles to compute

    Keyword arguments:
    var_trim -- True if the equilibrium trim should be computed for each roll
    angle, False if null trim angle can be used instead.

    Returned value:
    Tuple of (points, ship, weights, tanks, solas_data)
    """
    doc = lc.Document
    
    # NEW FORMAT: Read from fixed cells
    try:
        # Check if this is the new format by looking for ship reference
        ship_label = None
        try:
            ship_label = lc.get('B2')  # Try new format first
        except:
            try:
                ship_label = lc.get('B1')  # Fallback to old format
            except:
                pass
        
        if ship_label is None:
            msg = App.Qt.translate(
                "ship_console",
                "Cannot find Ship reference in LoadCondition!")
            App.Console.PrintError(msg + '\n')
            return [], None, [], [], {}
        
        ships = doc.getObjectsByLabel(ship_label)
        if len(ships) != 1:
            if len(ships) == 0:
                msg = App.Qt.translate(
                    "ship_console",
                    "Wrong Ship label! (no instances labeled as '{}' found)")
                App.Console.PrintError(msg.format(ship_label) + '\n')
            else:
                msg = App.Qt.translate(
                    "ship_console",
                    "Ambiguous Ship label! ({} instances labeled as '{}' found)")
                App.Console.PrintError(msg.format(len(ships), ship_label) + '\n')
            return [], None, [], [], {}
        
        ship = ships[0]
        if ship is None or "IsShip" not in ship.PropertiesList:
            return [], None, [], [], {}
            
    except Exception as e:
        App.Console.PrintError("Error reading ship reference: {}\n".format(str(e)))
        return [], None, [], [], {}
    
    # NEW FORMAT: Read total mass and COG from fixed cells
    solas_data = {}
    try:
        # Read total mass from D4
        total_mass_kg = float(lc.get('D4'))
        W = Units.parseQuantity("{} kg".format(total_mass_kg)) * G
        
        # Read COG from E5, F5, G5
        cog_x = float(lc.get('E5'))
        cog_y = float(lc.get('F5'))
        cog_z = float(lc.get('G5'))
        COG = Vector(cog_x, cog_y, cog_z)
        
        # Read Free Surface Moment from K4 (optional)
        try:
            fs_moment = float(lc.get('K4'))
        except:
            fs_moment = 0.0
        
        # Store for SOLAS analysis
        solas_data = {
            'total_mass_kg': total_mass_kg,
            'cog_x': cog_x,
            'cog_y': cog_y,
            'cog_z': cog_z,
            'fs_moment': fs_moment,
            'ship_label': ship.Label,
            'lc_label': lc.Label
        }
        
        App.Console.PrintMessage("LoadCondition (NEW FORMAT):\n")
        App.Console.PrintMessage("  Total Mass: {} kg\n".format(total_mass_kg))
        App.Console.PrintMessage("  COG: ({:.3f}, {:.3f}, {:.3f}) m\n".format(cog_x, cog_y, cog_z))
        App.Console.PrintMessage("  Free Surface: {} kg·m\n".format(fs_moment))
        
    except Exception as e:
        App.Console.PrintError("Error reading new LoadCondition format: {}\n".format(str(e)))
        App.Console.PrintError("Expected cells: D4 (mass), E5/F5/G5 (COG), K4 (FS moment)\n")
        return [], None, [], [], {}
    
    # For the new format, we don't use individual weight/tank objects
    weights = []
    tanks = []
    
    # Calculate GZ curve
    points = solve_direct(ship, W, COG, rolls, var_trim)
    
    # Perform SOLAS analysis if we have points
    if points:
        solas_data.update(analyze_solas_stability(points, rolls, ship, COG))
    
    return points, ship, weights, tanks, solas_data


def solve_direct(ship, W, COG, rolls, var_trim=True):
    """Compute GZ curve using total weight and COG directly
    
    Position arguments:
    ship -- Ship object
    W -- Total weight (including G factor, in Newtons)
    COG -- Center of Gravity as Vector
    rolls -- List of roll angles
    
    Keyword arguments:
    var_trim -- True if the equilibrium trim should be computed
    
    Returned value:
    List of GZ curve points
    """
    points = []
    for i, roll in enumerate(rolls):
        App.Console.PrintMessage("{0} / {1}\n".format(i + 1, len(rolls)))
        point = solve_point_direct(W, COG, ship, roll, var_trim)
        if point is None:
            return []
        points.append(point)
    
    return points


def solve_point_direct(W, COG, ship, roll, var_trim=True):
    """Compute GZ value using total weight and COG
    
    Position arguments:
    W -- Total weight (in Newtons, already multiplied by G)
    COG -- Center of Gravity as Vector
    ship -- Ship object
    roll -- Roll angle
    var_trim -- True if trim should be calculated
    
    Returned value:
    Tuple of (GZ, draft, trim)
    """
    # Look for the equilibrium draft
    max_draft = Units.Quantity(ship.Shape.BoundBox.ZMax, Units.Length)
    draft = ship.Draft
    max_disp = Units.Quantity(ship.Shape.Volume, Units.Volume) * DENS * G
    
    if max_disp < W:
        msg = App.Qt.translate(
            "ship_console",
            "Too much weight! The ship will never displace water enough")
        App.Console.PrintError(msg + ' ({} vs. {})\n'.format(
            (max_disp / G).UserString, (W / G).UserString))
        return None
    
    trim = Units.parseQuantity("0 deg")
    
    for i in range(MAX_EQUILIBRIUM_ITERS):
        # Get the displacement and buoyancy center
        disp, B, _ = Hydrostatics.displacement(ship, draft, roll, trim)
        disp *= G
        
        # COG is already the total COG (no need to add tanks)
        cog_x = Units.Quantity(COG.x, Units.Length)
        cog_y = Units.Quantity(COG.y, Units.Length)
        cog_z = Units.Quantity(COG.z, Units.Length)
        
        # Compute the errors
        draft_err = -DRAFT_RELAX_FACTOR[i] * ((disp - W) / max_disp).Value
        R_x = cog_x - Units.Quantity(B.x, Units.Length)
        R_y = cog_y - Units.Quantity(B.y, Units.Length)
        R_z = cog_z - Units.Quantity(B.z, Units.Length)
        
        if not var_trim:
            trim_err = 0.0
        else:
            c = math.cos(trim.getValueAs('rad'))
            s = math.sin(trim.getValueAs('rad'))
            rx = c * R_x - s * R_z
            
            # Get BML for trim calculation
            _, _, fs_shape = Hydrostatics.floatingArea(ship, draft, roll, trim)
            if fs_shape is not None:
                bml, _ = Hydrostatics.BML(ship, fs_shape, draft, roll, trim)
            else:
                bml = ship.Length * math.cos(trim.getValueAs('rad').Value)
            if bml < -B.y:
                bml = -B.y
            
            trim_err = -TRIM_RELAX_FACTOR[i] * rx / bml
        
        # Check convergence
        if abs(draft_err) < 1E-2 and abs(trim_err) < 1E-4:
            break
        
        # Update draft and trim
        draft += draft_err * max_draft
        trim += trim_err * Units.Radian
    
    # Calculate GZ in the free surface frame
    c = math.cos(roll.getValueAs('rad'))
    s = math.sin(roll.getValueAs('rad'))
    
    return c * R_y - s * R_z, draft, trim


def analyze_solas_stability(points, rolls, ship, COG):
    """Analyze GZ curve for SOLAS/IMO compliance
    
    Args:
        points: List of (GZ, draft, trim) tuples
        rolls: List of roll angles as Quantity objects
        ship: Ship object
        COG: Center of Gravity vector
    
    Returns:
        Dictionary with SOLAS analysis results
    """
    try:
        import numpy as np
    except ImportError:
        App.Console.PrintError("NumPy is not installed. SOLAS analysis disabled.\n")
        return {}
    
    import math
    
    # Convert rolls to numeric degrees
    roll_angles_deg = []
    for angle in rolls:
        if hasattr(angle, 'getValueAs'):
            angle_deg = angle.getValueAs('deg').Value
        elif hasattr(angle, 'Value'):
            # FreeCAD stores angles in radians, convert to degrees
            angle_deg = math.degrees(angle.Value)
        else:
            angle_deg = float(angle)
        roll_angles_deg.append(angle_deg)
    
    # Convert to numpy array
    roll_angles_deg_array = np.array(roll_angles_deg)
    
    # Convert GZ values from mm to meters (FreeCAD stores length in mm)
    gz_values = []
    for point in points:
        gz, draft, trim = point
        if hasattr(gz, 'Value'):
            gz_m = gz.Value / 1000.0  # mm to meters
            gz_values.append(gz_m)
        else:
            gz_values.append(float(gz))
    
    # Convert to numpy arrays
    roll_rad = np.radians(roll_angles_deg_array)
    gz_m = np.array(gz_values)
    
    # Check if we have any valid GZ values
    if len(gz_m) == 0:
        return {}
    
    # 1. Find max GZ and its angle
    max_gz_idx = np.argmax(gz_m)
    max_gz = gz_m[max_gz_idx]
    max_gz_angle = roll_angles_deg_array[max_gz_idx]
    
    # 2. Find vanishing stability angle
    vanishing_angle = 90.0  # Default
    for i in range(max_gz_idx + 1, len(gz_m)):
        if gz_m[i] <= 0:
            if i > 0 and gz_m[i-1] > 0:
                # Linear interpolation
                x1 = roll_rad[i-1]
                y1 = gz_m[i-1]
                x2 = roll_rad[i]
                y2 = gz_m[i]
                vanishing_rad = x1 + (x2 - x1) * (0 - y1) / (y2 - y1)
                vanishing_angle = np.degrees(vanishing_rad)
            break
    
    # 3. Calculate areas under GZ curve with manual trapezoidal integration
    def calculate_area(angle_start_deg, angle_end_deg):
        # Only integrate up to vanishing angle
        angle_end_deg = min(angle_end_deg, vanishing_angle)
        if angle_end_deg <= angle_start_deg:
            return 0.0
            
        # Manual trapezoidal integration
        total_area = 0.0
        
        # Create finer grid for better accuracy
        n_points = 100
        angles = np.linspace(angle_start_deg, angle_end_deg, n_points)
        angles_rad = np.radians(angles)
        
        # Interpolate GZ values
        gz_interp = np.interp(angles_rad, roll_rad, gz_m)
        
        # Trapezoidal integration manually
        for i in range(len(angles_rad) - 1):
            x1 = angles_rad[i]
            x2 = angles_rad[i + 1]
            y1 = gz_interp[i]
            y2 = gz_interp[i + 1]
            total_area += (x2 - x1) * (y1 + y2) / 2.0
        
        return total_area
    
    # Alternative: Use numpy.trapz if available
    try:
        # Check if trapz exists in numpy
        if hasattr(np, 'trapz'):
            def calculate_area_np(angle_start_deg, angle_end_deg):
                angle_end_deg = min(angle_end_deg, vanishing_angle)
                if angle_end_deg <= angle_start_deg:
                    return 0.0
                    
                start_rad = np.radians(angle_start_deg)
                end_rad = np.radians(angle_end_deg)
                
                # Use interpolation
                angles_interp = np.linspace(start_rad, end_rad, 100)
                gz_interp = np.interp(angles_interp, roll_rad, gz_m)
                
                return np.trapz(gz_interp, angles_interp)
            
            # Use numpy version
            area_0_30 = calculate_area_np(0, 30)
            area_0_40 = calculate_area_np(0, 40)
            area_30_40 = calculate_area_np(30, 40)
        else:
            # Use manual version
            area_0_30 = calculate_area(0, 30)
            area_0_40 = calculate_area(0, 40)
            area_30_40 = calculate_area(30, 40)
    except:
        # Fallback to manual calculation
        area_0_30 = calculate_area(0, 30)
        area_0_40 = calculate_area(0, 40)
        area_30_40 = calculate_area(30, 40)
    
    # 4. GZ at 30° (interpolated)
    gz_at_30 = np.interp(np.radians(30), roll_rad, gz_m)
    
    # 5. Calculate initial GM from slope at small angles
    GM0 = 0.0
    if len(gz_m) >= 3:
        # Find the smallest positive angle
        pos_indices = np.where(roll_angles_deg_array > 0)[0]
        if len(pos_indices) > 0:
            first_pos_idx = pos_indices[0]
            if first_pos_idx > 0:
                # Use finite difference: GM ≈ GZ(φ) / φ for small φ
                φ_rad = roll_rad[first_pos_idx]
                GZ_φ = gz_m[first_pos_idx]
                GM0 = GZ_φ / φ_rad
    
    # Alternative method: linear fit to first few points
    if GM0 == 0.0 and len(gz_m) >= 2:
        # Use points with angle < 10° for GM calculation
        small_angle_mask = roll_angles_deg_array < 10
        small_angle_count = np.sum(small_angle_mask)
        
        if small_angle_count >= 2:
            x_small = roll_rad[small_angle_mask]
            y_small = gz_m[small_angle_mask]
            
            # Remove φ=0 point if exists
            if 0 in roll_angles_deg_array:
                zero_idx = np.where(roll_angles_deg_array == 0)[0]
                if len(zero_idx) > 0:
                    x_small = np.delete(x_small, np.where(x_small == 0))
                    y_small = np.delete(y_small, np.where(roll_rad[small_angle_mask] == 0))
            
            if len(x_small) >= 2:
                # Linear fit: y = a*x + b, where a = GM
                A = np.vstack([x_small, np.ones(len(x_small))]).T
                a, b = np.linalg.lstsq(A, y_small, rcond=None)[0]
                GM0 = a
    
    # 6. Check SOLAS criteria
    solas_criteria = {
        'area_0_30': {
            'value': area_0_30,
            'required': 0.055,
            'passed': area_0_30 >= 0.055
        },
        'area_0_40': {
            'value': area_0_40,
            'required': 0.090,
            'passed': area_0_40 >= 0.090
        },
        'area_30_40': {
            'value': area_30_40,
            'required': 0.030,
            'passed': area_30_40 >= 0.030
        },
        'gz_at_30': {
            'value': gz_at_30,
            'required': 0.20,
            'passed': gz_at_30 >= 0.20
        },
        'max_gz_angle': {
            'value': max_gz_angle,
            'required': 25.0,
            'passed': max_gz_angle >= 25.0
        },
        'GM0': {
            'value': GM0,
            'required': 0.15,
            'passed': GM0 >= 0.15
        }
    }
    
    # Calculate overall compliance
    passed_count = sum(1 for crit in solas_criteria.values() if crit['passed'])
    total_criteria = len(solas_criteria)
    
    result = {
        'max_gz': max_gz,
        'max_gz_angle': max_gz_angle,
        'vanishing_angle': vanishing_angle,
        'area_0_30': area_0_30,
        'area_0_40': area_0_40,
        'area_30_40': area_30_40,
        'gz_at_30': gz_at_30,
        'GM0': GM0,
        'solas_criteria': solas_criteria,
        'passed_count': passed_count,
        'total_criteria': total_criteria,
        'compliant': passed_count == total_criteria
    }
    
    return result



def print_solas_report(solas_data):
    """Print SOLAS stability report to console"""
    
    if not solas_data:
        return
    
    App.Console.PrintMessage("\n" + "="*70 + "\n")
    App.Console.PrintMessage("SOLAS/IMO STABILITY ANALYSIS REPORT\n")
    App.Console.PrintMessage("="*70 + "\n")
    
    # Basic info
    App.Console.PrintMessage(f"Ship: {solas_data.get('ship_label', 'N/A')}\n")
    App.Console.PrintMessage(f"Load Condition: {solas_data.get('lc_label', 'N/A')}\n")
    App.Console.PrintMessage(f"Total Mass: {solas_data.get('total_mass_kg', 0):.1f} kg\n")
    
    cog = (solas_data.get('cog_x', 0), solas_data.get('cog_y', 0), solas_data.get('cog_z', 0))
    App.Console.PrintMessage(f"COG: ({cog[0]:.3f}, {cog[1]:.3f}, {cog[2]:.3f}) m\n")
    
    App.Console.PrintMessage("\n" + "-"*70 + "\n")
    App.Console.PrintMessage("STABILITY PARAMETERS:\n")
    App.Console.PrintMessage(f"  Maximum GZ: {solas_data.get('max_gz', 0):.3f} m\n")
    App.Console.PrintMessage(f"  Angle of Max GZ: {solas_data.get('max_gz_angle', 0):.1f} °\n")
    App.Console.PrintMessage(f"  Vanishing Stability Angle: {solas_data.get('vanishing_angle', 0):.1f} °\n")
    App.Console.PrintMessage(f"  GZ at 30°: {solas_data.get('gz_at_30', 0):.3f} m\n")
    App.Console.PrintMessage(f"  Initial GM: {solas_data.get('GM0', 0):.3f} m\n")
    
    App.Console.PrintMessage("\nAREA UNDER GZ CURVE:\n")
    App.Console.PrintMessage(f"  0-30°: {solas_data.get('area_0_30', 0):.4f} m·rad (min: 0.055)\n")
    App.Console.PrintMessage(f"  0-40°: {solas_data.get('area_0_40', 0):.4f} m·rad (min: 0.090)\n")
    App.Console.PrintMessage(f"  30-40°: {solas_data.get('area_30_40', 0):.4f} m·rad (min: 0.030)\n")
    
    App.Console.PrintMessage("\n" + "-"*70 + "\n")
    App.Console.PrintMessage("SOLAS/IMO CRITERIA COMPLIANCE:\n")
    
    criteria = solas_data.get('solas_criteria', {})
    for name, crit in criteria.items():
        status = "✓ PASS" if crit.get('passed', False) else "✗ FAIL"
        value = crit.get('value', 0)
        required = crit.get('required', 0)
        
        # Format name for display
        display_name = name.replace('_', ' ').title()
        if name == 'area_0_30':
            display_name = "Area 0-30°"
        elif name == 'area_0_40':
            display_name = "Area 0-40°"
        elif name == 'area_30_40':
            display_name = "Area 30-40°"
        elif name == 'gz_at_30':
            display_name = "GZ at 30°"
        elif name == 'max_gz_angle':
            display_name = "Max GZ Angle"
        
        App.Console.PrintMessage(f"  {display_name}: {value:.4f} / {required:.3f} {status}\n")
    
    passed = solas_data.get('passed_count', 0)
    total = solas_data.get('total_criteria', 0)
    compliant = solas_data.get('compliant', False)
    
    App.Console.PrintMessage("\n" + "="*70 + "\n")
    App.Console.PrintMessage(f"SUMMARY: {passed}/{total} criteria passed\n")
    
    if compliant:
        App.Console.PrintMessage("✅ VESSEL COMPLIES WITH SOLAS/IMO STABILITY REQUIREMENTS\n")
    else:
        App.Console.PrintMessage("❌ VESSEL DOES NOT COMPLY WITH SOLAS/IMO STABILITY REQUIREMENTS\n")
    
    App.Console.PrintMessage("="*70 + "\n\n")
