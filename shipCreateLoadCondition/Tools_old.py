#***************************************************************************
#*                                                                         *
#*   Copyright (c) 2016 Jose Luis Cercos Pita <jlcercos@gmail.com>         *
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
#*   GNU Library General Public License for more detaillc.                 *
#*                                                                         *
#*   You should have received a copy of the GNU Library General Public     *
#*   License along with this program; if not, write to the Free Software   *
#*   Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  *
#*   USA                                                                   *
#*                                                                         *
#***************************************************************************


import FreeCAD as App
import Spreadsheet
from FreeCAD import Units
import math


READ_ONLY_FOREGROUND = (0.5, 0.5, 0.5)
READ_ONLY_BACKGROUND = (0.9, 0.9, 0.9)
HEADER_BACKGROUND = (0.8, 0.8, 1.0)  # Light blue for headers
TOTAL_BACKGROUND = (0.9, 1.0, 0.9)   # Light green for totals
WEIGHT_ROW_COLOR = (0.95, 0.95, 0.95)  # Light gray for weight rows
TANK_ROW_COLOR = (0.95, 0.95, 1.0)     # Very light blue for tank rows


def createLoadCondition(ship):
    """Create a comprehensive loading condition spreadsheet
    
    Creates a spreadsheet with all weights and tanks in the format:
    Column A: Name
    Column B: Density (kg/m³) - for tanks only
    Column C: Fill Level (%) - for tanks only
    Column D: Mass (kg)
    Column E: X Coordinate (m)
    Column F: Y Coordinate (m)
    Column G: Z Coordinate (m)
    Column H: Moment X (kg·m) = Mass * X
    Column I: Moment Y (kg·m) = Mass * Y
    Column J: Moment Z (kg·m) = Mass * Z
    Column K: Free Surface Moment (kg·m) - for tanks only
    
    Position arguments:
    ship -- Ship object
    
    Returned value:
    lc -- The new loading condition spreadsheet object
    """
    # Create the spreadsheet
    lc = App.activeDocument().addObject('Spreadsheet::Sheet',
                                       'LoadCondition')
    
    # Set column widths
    column_widths = {
        'A': 150,  # Name
        'B': 100,  # Density
        'C': 100,  # Fill %
        'D': 120,  # Mass
        'E': 100,  # X
        'F': 100,  # Y
        'G': 100,  # Z
        'H': 120,  # Moment X
        'I': 120,  # Moment Y
        'J': 120,  # Moment Z
        'K': 150,  # Free Surface Moment
    }
    
    for col, width in column_widths.items():
        lc.setColumnWidth(col, width)
    
    # Header row 1: Ship info
    lc.set("A1", "Ship:")
    lc.set("B1", ship.Label if hasattr(ship, 'Label') and ship.Label else ship.Name)
    lc.set("A2", "Load Condition:")
    lc.set("B2", "Load Condition")
    lc.setAlignment('A1:A2', 'right', 'keep')
    lc.setAlignment('B1:B2', 'left', 'keep')
    lc.setStyle('A1:A2', 'bold', 'add')
    lc.setStyle('B1:B2', 'bold', 'add')
    lc.setForeground('A1:A2', READ_ONLY_FOREGROUND)
    lc.setBackground('A1:B2', READ_ONLY_BACKGROUND)
    
    # Empty row
    lc.set("A4", "")
    
    # Header row 4: Main title
    lc.mergeCells('A5:K5')
    lc.set("A5", "LOAD CONDITION CALCULATION")
    lc.setAlignment('A5', 'center', 'keep')
    lc.setStyle('A5', 'bold', 'add')
    lc.setStyle('A5', 'underline', 'add')
    lc.setBackground('A5', HEADER_BACKGROUND)
    
    # Header row 5: Column titles
    headers = [
        "Name",
        "Density (kg/m³)",
        "Fill Level (%)",
        "Mass (kg)",
        "X (m)",
        "Y (m)", 
        "Z (m)",
        "Moment X (kg·m)",
        "Moment Y (kg·m)",
        "Moment Z (kg·m)",
        "Free Surface Moment (kg·m)"
    ]
    
    for i, header in enumerate(headers):
        cell = chr(ord('A') + i) + "6"
        lc.set(cell, header)
        lc.setAlignment(cell, 'center', 'keep')
        lc.setStyle(cell, 'bold', 'add')
        lc.setBackground(cell, HEADER_BACKGROUND)
    
    current_row = 7
    weight_count = 0
    tank_count = 0
    
    # Collect all data first
    weights_data = []
    tanks_data = []
    
    # Process all weights
    if hasattr(ship, 'Weights'):
        for weight_name in ship.Weights:
            weight = App.activeDocument().getObject(weight_name)
            if weight:
                # Get properties
                name = weight.Label if hasattr(weight, 'Label') and weight.Label else weight_name
                
                # Mass
                mass = 0.0
                if hasattr(weight, 'Mass'):
                    mass = weight.Mass
                elif hasattr(weight, 'Density') and hasattr(weight, 'Shape') and weight.Shape:
                    if hasattr(weight.Shape, 'Volume'):
                        try:
                            density = weight.Density.getValueAs("kg/m^3")
                            volume = weight.Shape.Volume / 1e9  # mm³ to m³
                            mass = density * volume
                        except:
                            mass = 0.0
                
                # COG
                cog_x = cog_y = cog_z = 0.0
                if hasattr(weight, 'COG'):
                    cog_x = weight.COG.x / 1000.0  # mm to m
                    cog_y = weight.COG.y / 1000.0
                    cog_z = weight.COG.z / 1000.0
                
                # Calculate moments
                moment_x = mass * cog_x
                moment_y = mass * cog_y
                moment_z = mass * cog_z
                
                weights_data.append({
                    'name': name,
                    'mass': mass,
                    'cog_x': cog_x,
                    'cog_y': cog_y,
                    'cog_z': cog_z,
                    'moment_x': moment_x,
                    'moment_y': moment_y,
                    'moment_z': moment_z
                })
                weight_count += 1
    
    # Process all tanks
    if hasattr(ship, 'Tanks'):
        for tank_name in ship.Tanks:
            tank = App.activeDocument().getObject(tank_name)
            if tank:
                # Get properties
                name = tank.Label if hasattr(tank, 'Label') and tank.Label else tank_name
                
                # Density
                density = 1025.0  # Default sea water
                if hasattr(tank, 'FluidType'):
                    fluid_type = tank.FluidType
                    # Fluid densities (kg/m³)
                    fluid_densities = {
                        "Fresh Water": 1000,
                        "Sea Water": 1025,
                        "Fuel Oil": 850,
                        "Diesel": 830,
                        "LNG": 450,
                        "LPG": 510
                    }
                    density = fluid_densities.get(fluid_type, 1025)
                elif hasattr(tank, 'Density'):
                    try:
                        density = tank.Density.getValueAs("kg/m^3")
                    except:
                        pass
                
                # Fill level
                fill_percent = 0.0
                if hasattr(tank, 'FillPercentage'):
                    fill_percent = tank.FillPercentage
                
                # Mass calculation
                mass = 0.0
                fill_ratio = fill_percent / 100.0
                if hasattr(tank, 'Shape') and tank.Shape and hasattr(tank.Shape, 'Volume'):
                    volume_m3 = tank.Shape.Volume / 1e9  # mm³ to m³
                    mass = density * volume_m3 * fill_ratio
                
                # COG
                cog_x = cog_y = cog_z = 0.0
                if hasattr(tank, 'COG'):
                    cog_x = tank.COG.x / 1000.0  # mm to m
                    cog_y = tank.COG.y / 1000.0
                    cog_z = tank.COG.z / 1000.0
                elif hasattr(tank, 'Shape') and tank.Shape:
                    bbox = tank.Shape.BoundBox
                    cog_x = bbox.Center.x / 1000.0
                    cog_y = bbox.Center.y / 1000.0
                    cog_z = bbox.Center.z / 1000.0
                
                # Calculate moments
                moment_x = mass * cog_x
                moment_y = mass * cog_y
                moment_z = mass * cog_z
                
                # Free surface moment (simplified calculation)
                free_surface_moment = 0.0
                if fill_ratio > 0 and fill_ratio < 1 and hasattr(tank, 'Shape') and tank.Shape:
                    bbox = tank.Shape.BoundBox
                    surface_width = bbox.YLength / 1000.0  # Transverse width in m
                    surface_length = bbox.XLength / 1000.0  # Longitudinal length in m
                    # Moment of inertia for rectangular free surface: (length * width³) / 12
                    if surface_width > 0 and surface_length > 0:
                        surface_inertia = (surface_length * (surface_width ** 3)) / 12.0
                        free_surface_moment = surface_inertia * density
                
                tanks_data.append({
                    'name': name,
                    'density': density,
                    'fill_percent': fill_percent,
                    'mass': mass,
                    'cog_x': cog_x,
                    'cog_y': cog_y,
                    'cog_z': cog_z,
                    'moment_x': moment_x,
                    'moment_y': moment_y,
                    'moment_z': moment_z,
                    'free_surface_moment': free_surface_moment
                })
                tank_count += 1
    
    # Add weights section
    if weight_count > 0:
        # Sub-header for weights
        lc.mergeCells(f'A{current_row}:K{current_row}')
        lc.set(f'A{current_row}', "WEIGHTS")
        lc.setAlignment(f'A{current_row}', 'left', 'keep')
        lc.setStyle(f'A{current_row}', 'bold', 'add')
        lc.setStyle(f'A{current_row}', 'italic', 'add')
        lc.setBackground(f'A{current_row}', HEADER_BACKGROUND)
        current_row += 1
        
        for weight in weights_data:
            lc.set(f'A{current_row}', weight['name'])
            lc.set(f'B{current_row}', "")  # Empty for weights
            lc.set(f'C{current_row}', "")  # Empty for weights
            lc.set(f'D{current_row}', f"{weight['mass']:.2f}")
            lc.set(f'E{current_row}', f"{weight['cog_x']:.3f}")
            lc.set(f'F{current_row}', f"{weight['cog_y']:.3f}")
            lc.set(f'G{current_row}', f"{weight['cog_z']:.3f}")
            lc.set(f'H{current_row}', f"{weight['moment_x']:.2f}")
            lc.set(f'I{current_row}', f"{weight['moment_y']:.2f}")
            lc.set(f'J{current_row}', f"{weight['moment_z']:.2f}")
            lc.set(f'K{current_row}', "")  # Empty for weights
            
            # Set row color
            for col in ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K']:
                lc.setBackground(f'{col}{current_row}', WEIGHT_ROW_COLOR)
            
            current_row += 1
    
    # Add tanks section
    if tank_count > 0:
        # Empty row before tanks if there were weights
        if weight_count > 0:
            current_row += 1
        
        # Sub-header for tanks
        lc.mergeCells(f'A{current_row}:K{current_row}')
        lc.set(f'A{current_row}', "TANKS")
        lc.setAlignment(f'A{current_row}', 'left', 'keep')
        lc.setStyle(f'A{current_row}', 'bold', 'add')
        lc.setStyle(f'A{current_row}', 'italic', 'add')
        lc.setBackground(f'A{current_row}', HEADER_BACKGROUND)
        current_row += 1
        
        for tank in tanks_data:
            lc.set(f'A{current_row}', tank['name'])
            lc.set(f'B{current_row}', f"{tank['density']:.1f}")
            lc.set(f'C{current_row}', f"{tank['fill_percent']:.1f}")
            lc.set(f'D{current_row}', f"{tank['mass']:.2f}")
            lc.set(f'E{current_row}', f"{tank['cog_x']:.3f}")
            lc.set(f'F{current_row}', f"{tank['cog_y']:.3f}")
            lc.set(f'G{current_row}', f"{tank['cog_z']:.3f}")
            lc.set(f'H{current_row}', f"{tank['moment_x']:.2f}")
            lc.set(f'I{current_row}', f"{tank['moment_y']:.2f}")
            lc.set(f'J{current_row}', f"{tank['moment_z']:.2f}")
            lc.set(f'K{current_row}', f"{tank['free_surface_moment']:.2f}")
            
            # Set row color
            for col in ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K']:
                lc.setBackground(f'{col}{current_row}', TANK_ROW_COLOR)
            
            current_row += 1
    
    # Calculate totals
    total_mass = 0.0
    total_moment_x = 0.0
    total_moment_y = 0.0
    total_moment_z = 0.0
    total_free_surface = 0.0
    
    for weight in weights_data:
        total_mass += weight['mass']
        total_moment_x += weight['moment_x']
        total_moment_y += weight['moment_y']
        total_moment_z += weight['moment_z']
    
    for tank in tanks_data:
        total_mass += tank['mass']
        total_moment_x += tank['moment_x']
        total_moment_y += tank['moment_y']
        total_moment_z += tank['moment_z']
        total_free_surface += tank['free_surface_moment']
    
    # Empty row before totals
    current_row += 1
    
    # Totals row
    lc.mergeCells(f'A{current_row}:C{current_row}')
    lc.set(f'A{current_row}', "TOTALS")
    lc.setAlignment(f'A{current_row}', 'right', 'keep')
    lc.setStyle(f'A{current_row}', 'bold', 'add')
    lc.setBackground(f'A{current_row}:K{current_row}', TOTAL_BACKGROUND)
    
    # Set total values directly (no formulas)
    lc.set(f'D{current_row}', f"{total_mass:.2f}")
    lc.set(f'H{current_row}', f"{total_moment_x:.2f}")
    lc.set(f'I{current_row}', f"{total_moment_y:.2f}")
    lc.set(f'J{current_row}', f"{total_moment_z:.2f}")
    lc.set(f'K{current_row}', f"{total_free_surface:.2f}")
    
    # COG calculation row (next row after totals)
    current_row += 1
    lc.mergeCells(f'A{current_row}:C{current_row}')
    lc.set(f'A{current_row}', "CENTER OF GRAVITY (COG)")
    lc.setAlignment(f'A{current_row}', 'right', 'keep')
    lc.setStyle(f'A{current_row}', 'bold', 'add')
    lc.setBackground(f'A{current_row}:G{current_row}', TOTAL_BACKGROUND)
    
    # Calculate and set COG coordinates directly
    if total_mass > 0:
        cog_x = total_moment_x / total_mass
        cog_y = total_moment_y / total_mass
        cog_z = total_moment_z / total_mass
        
        lc.set(f'E{current_row}', f"{cog_x:.3f}")
        lc.set(f'F{current_row}', f"{cog_y:.3f}")
        lc.set(f'G{current_row}', f"{cog_z:.3f}")
    else:
        lc.set(f'E{current_row}', "0.000")
        lc.set(f'F{current_row}', "0.000")
        lc.set(f'G{current_row}', "0.000")
    
    # Format all numeric cells
    start_data_row = 7
    if weight_count > 0:
        start_data_row += 2  # Skip WEIGHTS header and sub-header
    
    for row in range(start_data_row, current_row):
        for col in ['B', 'C', 'D', 'H', 'I', 'J', 'K']:
            cell = f"{col}{row}"
            if lc.getContents(cell):
                lc.setAlignment(cell, 'center', 'keep')
        
        for col in ['E', 'F', 'G']:
            cell = f"{col}{row}"
            if lc.getContents(cell):
                lc.setAlignment(cell, 'center', 'keep')
    
    # Format totals and COG cells
    total_row = current_row - 1
    cog_row = current_row
    
    for col in ['D', 'H', 'I', 'J', 'K']:
        lc.setAlignment(f'{col}{total_row}', 'center', 'keep')
        lc.setStyle(f'{col}{total_row}', 'bold', 'add')
    
    for col in ['E', 'F', 'G']:
        lc.setAlignment(f'{col}{cog_row}', 'center', 'keep')
        lc.setStyle(f'{col}{cog_row}', 'bold', 'add')
    
    # Add the spreadsheet to the list of loading conditions of the ship
    if not hasattr(ship, 'LoadConditions'):
        ship.addProperty("App::PropertyStringList", "LoadConditions", "Ship", "List of loading conditions")
    
    lcs = []
    if hasattr(ship, 'LoadConditions'):
        lcs = ship.LoadConditions[:]
    lcs.append(lc.Name)
    ship.LoadConditions = lcs
    
    # Clean up any invalid references
    if hasattr(ship, 'Proxy') and hasattr(ship.Proxy, 'cleanLoadConditions'):
        ship.Proxy.cleanLoadConditions(ship)
    
    # Recompute to take the changes
    App.activeDocument().recompute()
    
    return lc


def updateLoadCondition(lc, ship):
    """Update an existing loading condition spreadsheet
    
    Updates all the formulas and values in the load condition spreadsheet
    based on current ship configuration.
    """
    # Remove old spreadsheet
    App.activeDocument().removeObject(lc.Name)
    
    # Create new one
    return createLoadCondition(ship)
