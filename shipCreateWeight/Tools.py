#***************************************************************************
#*                                                                         *
#*   Advanced Weight Tools for FreeCAD Ships Workbench                     *
#*   Extended version supporting all cargo types                           *
#*                                                                         *
#*   Based on original work by Jose Luis Cercos Pita                       *
#*   Extended for: Tanks, General Cargo, Bulk Cargo, Containers, etc.      *
#*                                                                         *
#***************************************************************************

import FreeCAD as App
from FreeCAD import Units
from .. import WeightInstance as Instance
from ..shipUtils.Math import matrix
import math
from enum import Enum

# ===========================================================================
# ENUM DEFINITIONS
# ===========================================================================

class WeightType(Enum):
    """Complete weight type classification"""
    POINT_MASS = 1          # Point mass
    LINEAR = 2              # Linear density
    AREA = 3                # Area density  
    VOLUME = 4              # Volume density
    TANK = 5                # Tank with liquid
    CRANE_LOAD = 6          # Suspended load
    CONTAINER = 7           # ISO container
    GENERAL_CARGO = 8       # Piece goods (Stückgut)
    BULK_CARGO = 9          # Bulk cargo (Schüttgut)
    LIQUID_BULK = 10        # Liquid bulk
    VEHICLE = 11            # Vehicles
    PROJECT_CARGO = 12      # Heavy lift/Project cargo

class FluidType(Enum):
    """Fluid types with densities in kg/m³"""
    FRESH_WATER = 1000.0
    SEA_WATER = 1025.0
    FUEL_OIL = 850.0
    DIESEL_OIL = 835.0
    LUBE_OIL = 900.0
    HEAVY_FUEL = 991.0
    BALLAST_WATER = 1025.0
    SEWAGE = 1010.0
    GRAY_WATER = 1000.0
    CHEMICAL = 1100.0
    CUSTOM = 0.0

class CargoCategory(Enum):
    """Cargo category for organization"""
    TANK = "Tank"
    GENERAL = "General Cargo"
    BULK = "Bulk Cargo"
    CONTAINER = "Container"
    VEHICLE = "Vehicle"
    PROJECT = "Project Cargo"
    CRANE = "Crane Load"

# ===========================================================================
# ORIGINAL FUNCTION (unchanged)
# ===========================================================================

def createWeight(shapes, ship, density, inertia):
    """Create a new weight instance (original function)

    Position arguments:
    shapes -- List of shapes of the weight
    ship -- Ship owner
    density -- Density of the object.
    inertia -- Inertia matrix (3x3)

    Returned value:
    The new weight object
    """
    # Create the object
    obj = App.ActiveDocument.addObject("Part::FeaturePython", "Weight")
    weight = Instance.Weight(obj, shapes, ship)
    Instance.ViewProviderWeight(obj.ViewObject)

    # Setup the mass/density value
    m_unit = "kg"
    l_unit = "m"
    m_qty = Units.Quantity(1, Units.Mass)
    l_qty = Units.Quantity(1, Units.Length)
    a_qty = Units.Quantity(1, Units.Area)
    v_qty = Units.Quantity(1, Units.Volume)
    if density.Unit == m_qty.Unit:
        w_unit = m_unit
        obj.Mass = density.getValueAs(w_unit).Value
    elif density.Unit == (m_qty / l_qty).Unit:
        w_unit = m_unit + '/' + l_unit
        obj.LineDens = density.getValueAs(w_unit).Value
    elif density.Unit == (m_qty / a_qty).Unit:
        w_unit = m_unit + '/' + l_unit + '^2'
        obj.AreaDens = density.getValueAs(w_unit).Value
    elif density.Unit == (m_qty / v_qty).Unit:
        w_unit = m_unit + '/' + l_unit + '^3'
        obj.Dens = density.getValueAs(w_unit).Value

    # Install the inertia
    i_unit = "kg*m^2"
    I = matrix(4, 0.0)
    I[3][3] = 1.0
    for i,row in enumerate(inertia):
        for j,val in enumerate(row):
            I[i][j] = val.getValueAs(i_unit).Value
    I_flat = []
    for i in range(4):
        for j in range(4):
            I_flat.append(I[j][i])
    obj.Inertia = tuple(I_flat)

    # Set it as a child of the ship
    weights = ship.Weights[:]
    weights.append(obj.Name)
    ship.Weights = weights
    ship.Proxy.cleanWeights(ship)
    ship.Proxy.cleanTanks(ship)
    ship.Proxy.cleanLoadConditions(ship)

    App.ActiveDocument.recompute()

    return obj

# ===========================================================================
# ADVANCED WEIGHT CREATION FUNCTIONS
# ===========================================================================

def createAdvancedWeight(shapes, ship, weight_type, params):
    """Create advanced weight object with specific type
    
    Parameters:
    shapes -- Geometry shapes (may be empty for computational weights)
    ship -- Ship object
    weight_type -- WeightType enum
    params -- Dictionary with parameters specific to weight type
    
    Returns:
    The new weight object
    """
    if weight_type == WeightType.TANK:
        return createTank(shapes, ship, params)
    elif weight_type == WeightType.GENERAL_CARGO:
        return createGeneralCargo(shapes, ship, params)
    elif weight_type == WeightType.BULK_CARGO:
        return createBulkCargo(shapes, ship, params)
    elif weight_type == WeightType.CONTAINER:
        return createContainer(shapes, ship, params)
    elif weight_type == WeightType.CRANE_LOAD:
        return createCraneLoad(shapes, ship, params)
    elif weight_type == WeightType.VEHICLE:
        return createVehicle(shapes, ship, params)
    elif weight_type == WeightType.PROJECT_CARGO:
        return createProjectCargo(shapes, ship, params)
    elif weight_type == WeightType.LIQUID_BULK:
        return createLiquidBulk(shapes, ship, params)
    else:
        # Use base function for simple types
        return createWeight(shapes, ship, 
                           params.get('density', Units.Quantity(1000, Units.Density)),
                           params.get('inertia', matrix(3, 0.0)))

def createTank(shapes, ship, params):
    """Create a tank with liquid
    
    Parameters:
    shapes -- Geometry shapes
    ship -- Ship object
    params -- Dictionary with tank parameters
    """
    # Parse parameters
    capacity = params.get('capacity', 100.0)
    
    fluid_type = params.get('fluid_type', FluidType.SEA_WATER)
    if isinstance(fluid_type, str):
        try:
            fluid_type = FluidType[fluid_type]
        except:
            fluid_type = FluidType.SEA_WATER
    
    fill_percentage = max(0.0, min(100.0, params.get('fill_percentage', 0.0)))
    
    # Calculate weight
    fluid_density = fluid_type.value
    content_weight = capacity * (fill_percentage / 100.0) * fluid_density
    
    # Create object
    obj = App.ActiveDocument.addObject("Part::FeaturePython", "Tank")
    
    # Initialize as weight
    if shapes:
        weight = Instance.Weight(obj, shapes, ship)
    else:
        weight = Instance.Weight(obj, [], ship)
    
    Instance.ViewProviderWeight(obj.ViewObject)
    
    # Add advanced properties
    obj.addProperty("App::PropertyEnumeration", "FluidType", "Tank",
                   "Type of fluid in tank")
    obj.FluidType = [f.name for f in FluidType]
    obj.FluidType = fluid_type.name
    
    obj.addProperty("App::PropertyPercent", "FillPercentage", "Tank",
                   "Percentage of tank filled")
    obj.FillPercentage = fill_percentage
    
    obj.addProperty("App::PropertyFloat", "Capacity", "Tank",
                   "Total capacity in cubic meters")
    obj.Capacity = capacity
    
    obj.addProperty("App::PropertyFloat", "TotalWeight", "Tank",
                   "Weight of fluid in kg")
    obj.TotalWeight = content_weight
    
    obj.addProperty("App::PropertyString", "Category", "Base",
                   "Weight category")
    obj.Category = CargoCategory.TANK.value
    
    # Set density for weight calculation
    if shapes and len(shapes) > 0:
        # Calculate volume from shape
        volume = 0.0
        for shape in shapes:
            volume += shape.Volume
        if volume > 0:
            effective_density = content_weight / volume
            obj.Dens = effective_density
    
    # Add to ship
    weights = ship.Weights[:]
    weights.append(obj.Name)
    ship.Weights = weights
    ship.Proxy.cleanWeights(ship)
    ship.Proxy.cleanTanks(ship)
    ship.Proxy.cleanLoadConditions(ship)
    
    App.ActiveDocument.recompute()
    return obj

def createGeneralCargo(shapes, ship, params):
    """Create general cargo (piece goods) with bounding box
    
    Parameters:
    shapes -- Geometry shapes
    ship -- Ship object
    params -- Dictionary with parameters
    """
    # Parse parameters
    length = params.get('length', 5.0)
    width = params.get('width', 2.5)
    height = params.get('height', 2.0)
    weight = params.get('weight', 5000.0)
    
    # Calculate COG
    if 'cog_x' in params and 'cog_y' in params and 'cog_z' in params:
        cog_x = params['cog_x']
        cog_y = params['cog_y']
        cog_z = params['cog_z']
    else:
        # Use relative positions
        cog_x_rel = params.get('cog_x_rel', 0.5)
        cog_y_rel = params.get('cog_y_rel', 0.5)
        cog_z_rel = params.get('cog_z_rel', 0.5)
        
        position = params.get('position', App.Vector(0, 0, 0))
        cog_x = position.x + cog_x_rel * length
        cog_y = position.y + cog_y_rel * width
        cog_z = position.z + cog_z_rel * height
    
    # Create object
    obj = App.ActiveDocument.addObject("Part::FeaturePython", "GeneralCargo")
    
    # Create bounding box shape
    position = params.get('position', App.Vector(0, 0, 0))
    box = Part.makeBox(length, width, height, position)
    
    # Initialize as weight
    weight_obj = Instance.Weight(obj, [box], ship)
    Instance.ViewProviderWeight(obj.ViewObject)
    
    # Add advanced properties
    obj.addProperty("App::PropertyLength", "Length", "GeneralCargo",
                   "Bounding box length")
    obj.Length = length
    
    obj.addProperty("App::PropertyLength", "Width", "GeneralCargo",
                   "Bounding box width")
    obj.Width = width
    
    obj.addProperty("App::PropertyLength", "Height", "GeneralCargo",
                   "Bounding box height")
    obj.Height = height
    
    obj.addProperty("App::PropertyFloat", "TotalWeight", "GeneralCargo",
                   "Total weight in kg")
    obj.TotalWeight = weight
    
    obj.addProperty("App::PropertyVector", "CenterOfGravity", "GeneralCargo",
                   "Center of gravity")
    obj.CenterOfGravity = App.Vector(cog_x, cog_y, cog_z)
    
    obj.addProperty("App::PropertyEnumeration", "CargoType", "GeneralCargo",
                   "Type of cargo")
    obj.CargoType = ['MACHINERY', 'STEEL_PARTS', 'TIMBER', 'PIPES', 
                    'ELECTRICAL', 'MACHINE_PARTS', 'PALLETS', 'OTHER']
    obj.CargoType = params.get('cargo_type', 'OTHER')
    
    obj.addProperty("App::PropertyBool", "SecuringRequired", "GeneralCargo",
                   "Cargo securing required")
    obj.SecuringRequired = params.get('securing_required', True)
    
    obj.addProperty("App::PropertyString", "Category", "Base",
                   "Weight category")
    obj.Category = CargoCategory.GENERAL.value
    
    # Set density
    volume = length * width * height
    if volume > 0:
        obj.Dens = weight / volume
    
    # Add to ship
    weights = ship.Weights[:]
    weights.append(obj.Name)
    ship.Weights = weights
    ship.Proxy.cleanWeights(ship)
    ship.Proxy.cleanTanks(ship)
    ship.Proxy.cleanLoadConditions(ship)
    
    App.ActiveDocument.recompute()
    return obj

def createBulkCargo(shapes, ship, params):
    """Create bulk cargo (homogeneous material)
    
    Parameters:
    shapes -- Geometry shapes
    ship -- Ship object
    params -- Dictionary with parameters
    """
    # Parse parameters
    length = params.get('length', 20.0)
    width = params.get('width', 15.0)
    height = params.get('height', 10.0)
    weight = params.get('weight', 150000.0)
    fill_percentage = max(0.0, min(100.0, params.get('fill_percentage', 90.0)))
    
    # Calculate fill height and COG
    fill_height = height * (fill_percentage / 100.0)
    position = params.get('position', App.Vector(0, 0, 0))
    cog = App.Vector(
        position.x + length / 2.0,
        position.y + width / 2.0,
        position.z + fill_height / 2.0
    )
    
    # Create object
    obj = App.ActiveDocument.addObject("Part::FeaturePython", "BulkCargo")
    
    # Create shape with fill height
    box = Part.makeBox(length, width, fill_height, position)
    
    # Initialize as weight
    weight_obj = Instance.Weight(obj, [box], ship)
    Instance.ViewProviderWeight(obj.ViewObject)
    
    # Add advanced properties
    obj.addProperty("App::PropertyLength", "Length", "BulkCargo",
                   "Compartment length")
    obj.Length = length
    
    obj.addProperty("App::PropertyLength", "Width", "BulkCargo",
                   "Compartment width")
    obj.Width = width
    
    obj.addProperty("App::PropertyLength", "Height", "BulkCargo",
                   "Compartment height")
    obj.Height = height
    
    obj.addProperty("App::PropertyFloat", "TotalWeight", "BulkCargo",
                   "Total weight in kg")
    obj.TotalWeight = weight
    
    obj.addProperty("App::PropertyPercent", "FillPercentage", "BulkCargo",
                   "Fill percentage")
    obj.FillPercentage = fill_percentage
    
    obj.addProperty("App::PropertyVector", "CenterOfGravity", "BulkCargo",
                   "COG position")
    obj.CenterOfGravity = cog
    
    obj.addProperty("App::PropertyEnumeration", "CargoType", "BulkCargo",
                   "Type of bulk material")
    obj.CargoType = ['GRAIN', 'COAL', 'IRON_ORE', 'BAUXITE', 'CEMENT',
                    'SUGAR', 'RICE', 'FERTILIZER', 'SALT', 'GRAVEL',
                    'SAND', 'OTHER']
    obj.CargoType = params.get('cargo_type', 'GRAIN')
    
    obj.addProperty("App::PropertyString", "Category", "Base",
                   "Weight category")
    obj.Category = CargoCategory.BULK.value
    
    # Calculate free surface moment
    free_surface_I = (length * width**3) / 12.0
    fill_ratio = fill_percentage / 100.0
    reduction_factor = get_bulk_reduction_factor(obj.CargoType)
    free_surface_moment = free_surface_I * fill_ratio * (1 - fill_ratio) * reduction_factor
    
    obj.addProperty("App::PropertyFloat", "FreeSurfaceMoment", "BulkCargo",
                   "Free surface moment (m⁴)")
    obj.FreeSurfaceMoment = free_surface_moment
    
    # Set density
    fill_volume = length * width * fill_height
    if fill_volume > 0:
        obj.Dens = weight / fill_volume
    
    # Add to ship
    weights = ship.Weights[:]
    weights.append(obj.Name)
    ship.Weights = weights
    ship.Proxy.cleanWeights(ship)
    ship.Proxy.cleanTanks(ship)
    ship.Proxy.cleanLoadConditions(ship)
    
    App.ActiveDocument.recompute()
    return obj

def get_bulk_reduction_factor(cargo_type):
    """Get reduction factor for free surface effect"""
    factors = {
        'GRAIN': 0.4,
        'COAL': 0.5,
        'IRON_ORE': 0.6,
        'CEMENT': 0.3,
        'SUGAR': 0.4,
        'RICE': 0.4,
        'FERTILIZER': 0.5,
        'SALT': 0.4,
        'GRAVEL': 0.7,
        'SAND': 0.6
    }
    return factors.get(cargo_type, 0.5)

def createContainer(shapes, ship, params):
    """Create ISO container
    
    Parameters:
    shapes -- Geometry shapes
    ship -- Ship object
    params -- Dictionary with parameters
    """
    # Parse parameters
    container_type = params.get('container_type', '20FT_DRY')
    tare_weight = params.get('tare_weight', 2200.0)
    actual_payload = params.get('actual_payload', 20000.0)
    total_weight = tare_weight + actual_payload
    
    # Set dimensions based on type
    if '20FT' in container_type:
        length, width, height = 6.058, 2.438, 2.591
    elif '40FT' in container_type:
        length, width, height = 12.192, 2.438, 2.591
    else:
        length, width, height = 6.058, 2.438, 2.591
    
    position = params.get('position', App.Vector(0, 0, 0))
    
    # Create object
    obj = App.ActiveDocument.addObject("Part::FeaturePython", "Container")
    
    # Create shape
    box = Part.makeBox(length, width, height, position)
    
    # Initialize as weight
    weight_obj = Instance.Weight(obj, [box], ship)
    Instance.ViewProviderWeight(obj.ViewObject)
    
    # Add advanced properties
    obj.addProperty("App::PropertyEnumeration", "ContainerType", "Container",
                   "ISO container type")
    obj.ContainerType = ['20FT_DRY', '40FT_DRY', '20FT_REEFER', 
                        '40FT_REEFER', '20FT_TANK', '40FT_HC', '45FT_HC']
    obj.ContainerType = container_type
    
    obj.addProperty("App::PropertyLength", "Length", "Container",
                   "External length")
    obj.Length = length
    
    obj.addProperty("App::PropertyLength", "Width", "Container",
                   "External width")
    obj.Width = width
    
    obj.addProperty("App::PropertyLength", "Height", "Container",
                   "External height")
    obj.Height = height
    
    obj.addProperty("App::PropertyFloat", "TareWeight", "Container",
                   "Tare weight in kg")
    obj.TareWeight = tare_weight
    
    obj.addProperty("App::PropertyFloat", "ActualPayload", "Container",
                   "Actual payload in kg")
    obj.ActualPayload = actual_payload
    
    obj.addProperty("App::PropertyFloat", "TotalWeight", "Container",
                   "Total weight in kg")
    obj.TotalWeight = total_weight
    
    # Set COG (typical for containers: 45% height)
    cog = App.Vector(
        position.x + length/2.0,
        position.y + width/2.0,
        position.z + height * 0.45
    )
    obj.addProperty("App::PropertyVector", "CenterOfGravity", "Container",
                   "COG position")
    obj.CenterOfGravity = cog
    
    obj.addProperty("App::PropertyString", "Category", "Base",
                   "Weight category")
    obj.Category = CargoCategory.CONTAINER.value
    
    # Set density
    volume = length * width * height
    if volume > 0:
        obj.Dens = total_weight / volume
    
    # Add to ship
    weights = ship.Weights[:]
    weights.append(obj.Name)
    ship.Weights = weights
    ship.Proxy.cleanWeights(ship)
    ship.Proxy.cleanTanks(ship)
    ship.Proxy.cleanLoadConditions(ship)
    
    App.ActiveDocument.recompute()
    return obj

def createCraneLoad(shapes, ship, params):
    """Create a suspended crane load
    
    Parameters:
    shapes -- Geometry shapes
    ship -- Ship object
    params -- Dictionary with parameters
    """
    weight = params.get('weight', 10000.0)
    hook_position = params.get('hook_position', App.Vector(0, 0, 20.0))
    
    # Create object
    obj = App.ActiveDocument.addObject("Part::FeaturePython", "CraneLoad")
    
    # Initialize as weight (with empty shapes for suspended load)
    weight_obj = Instance.Weight(obj, [], ship)
    Instance.ViewProviderWeight(obj.ViewObject)
    
    # Add advanced properties
    obj.addProperty("App::PropertyFloat", "TotalWeight", "CraneLoad",
                   "Load weight in kg")
    obj.TotalWeight = weight
    
    obj.addProperty("App::PropertyVector", "HookPosition", "CraneLoad",
                   "Hook position")
    obj.HookPosition = hook_position
    
    obj.addProperty("App::PropertyFloat", "BoomAngle", "CraneLoad",
                   "Boom angle in degrees")
    obj.BoomAngle = params.get('boom_angle', 45.0)
    
    obj.addProperty("App::PropertyString", "CraneID", "CraneLoad",
                   "Crane identifier")
    obj.CraneID = params.get('crane_id', 'CRANE01')
    
    obj.addProperty("App::PropertyBool", "IsSuspended", "CraneLoad",
                   "Load is currently suspended")
    obj.IsSuspended = True
    
    # Use hook position as COG
    obj.addProperty("App::PropertyVector", "CenterOfGravity", "CraneLoad",
                   "Current COG position")
    obj.CenterOfGravity = hook_position
    
    obj.addProperty("App::PropertyString", "Category", "Base",
                   "Weight category")
    obj.Category = CargoCategory.CRANE.value
    
    # Set as point mass
    obj.Mass = weight
    
    # Add to ship
    weights = ship.Weights[:]
    weights.append(obj.Name)
    ship.Weights = weights
    ship.Proxy.cleanWeights(ship)
    ship.Proxy.cleanTanks(ship)
    ship.Proxy.cleanLoadConditions(ship)
    
    App.ActiveDocument.recompute()
    return obj

def createVehicle(shapes, ship, params):
    """Create a vehicle (car, truck, etc.)
    
    Parameters:
    shapes -- Geometry shapes
    ship -- Ship object
    params -- Dictionary with parameters
    """
    vehicle_type = params.get('vehicle_type', 'TRUCK')
    weight = params.get('weight', 15000.0)
    length = params.get('length', 10.0)
    width = params.get('width', 2.5)
    height = params.get('height', 3.0)
    position = params.get('position', App.Vector(0, 0, 0))
    
    # Create object
    obj = App.ActiveDocument.addObject("Part::FeaturePython", "Vehicle")
    
    # Create shape
    box = Part.makeBox(length, width, height, position)
    
    # Initialize as weight
    weight_obj = Instance.Weight(obj, [box], ship)
    Instance.ViewProviderWeight(obj.ViewObject)
    
    # Add advanced properties
    obj.addProperty("App::PropertyEnumeration", "VehicleType", "Vehicle",
                   "Type of vehicle")
    obj.VehicleType = ['CAR', 'TRUCK', 'TRAILER', 'BUS', 'EXCAVATOR',
                      'CRANE', 'TRACTOR', 'OTHER']
    obj.VehicleType = vehicle_type
    
    obj.addProperty("App::PropertyLength", "Length", "Vehicle",
                   "Vehicle length")
    obj.Length = length
    
    obj.addProperty("App::PropertyLength", "Width", "Vehicle",
                   "Vehicle width")
    obj.Width = width
    
    obj.addProperty("App::PropertyLength", "Height", "Vehicle",
                   "Vehicle height")
    obj.Height = height
    
    obj.addProperty("App::PropertyFloat", "TotalWeight", "Vehicle",
                   "Total weight in kg")
    obj.TotalWeight = weight
    
    # Set COG (typical for vehicles: 40% length, 50% width, 40% height)
    cog = App.Vector(
        position.x + length * 0.4,
        position.y + width / 2.0,
        position.z + height * 0.4
    )
    obj.addProperty("App::PropertyVector", "CenterOfGravity", "Vehicle",
                   "COG position")
    obj.CenterOfGravity = cog
    
    obj.addProperty("App::PropertyString", "Category", "Base",
                   "Weight category")
    obj.Category = CargoCategory.VEHICLE.value
    
    # Set density
    volume = length * width * height
    if volume > 0:
        obj.Dens = weight / volume
    
    # Add to ship
    weights = ship.Weights[:]
    weights.append(obj.Name)
    ship.Weights = weights
    ship.Proxy.cleanWeights(ship)
    ship.Proxy.cleanTanks(ship)
    ship.Proxy.cleanLoadConditions(ship)
    
    App.ActiveDocument.recompute()
    return obj

def createProjectCargo(shapes, ship, params):
    """Create project/heavy lift cargo
    
    Parameters:
    shapes -- Geometry shapes
    ship -- Ship object
    params -- Dictionary with parameters
    """
    description = params.get('description', 'Project Cargo')
    weight = params.get('weight', 50000.0)
    
    # Create object
    obj = App.ActiveDocument.addObject("Part::FeaturePython", "ProjectCargo")
    
    # Use provided shapes or create default box
    if shapes and len(shapes) > 0:
        shape = shapes[0]
        weight_obj = Instance.Weight(obj, shapes, ship)
    else:
        # Create default box
        dimensions = params.get('dimensions', App.Vector(10.0, 4.0, 4.0))
        position = params.get('position', App.Vector(0, 0, 0))
        box = Part.makeBox(dimensions.x, dimensions.y, dimensions.z, position)
        weight_obj = Instance.Weight(obj, [box], ship)
    
    Instance.ViewProviderWeight(obj.ViewObject)
    
    # Add advanced properties
    obj.addProperty("App::PropertyString", "Description", "ProjectCargo",
                   "Cargo description")
    obj.Description = description
    
    obj.addProperty("App::PropertyFloat", "TotalWeight", "ProjectCargo",
                   "Total weight in kg")
    obj.TotalWeight = weight
    
    obj.addProperty("App::PropertyFloat", "CriticalTippingAngle", "ProjectCargo",
                   "Critical tipping angle in degrees")
    obj.CriticalTippingAngle = params.get('critical_tipping_angle', 15.0)
    
    obj.addProperty("App::PropertyString", "Category", "Base",
                   "Weight category")
    obj.Category = CargoCategory.PROJECT.value
    
    # Set COG from shape or params
    if 'cog' in params:
        cog = params['cog']
    elif hasattr(obj, 'Shape') and obj.Shape:
        cog = obj.Shape.CenterOfMass
    else:
        cog = App.Vector(0, 0, 0)
    
    obj.addProperty("App::PropertyVector", "CenterOfGravity", "ProjectCargo",
                   "COG position")
    obj.CenterOfGravity = cog
    
    # Add to ship
    weights = ship.Weights[:]
    weights.append(obj.Name)
    ship.Weights = weights
    ship.Proxy.cleanWeights(ship)
    ship.Proxy.cleanTanks(ship)
    ship.Proxy.cleanLoadConditions(ship)
    
    App.ActiveDocument.recompute()
    return obj

def createLiquidBulk(shapes, ship, params):
    """Create liquid bulk cargo (in tanks) - alias for createTank with liquid type"""
    params['fluid_type'] = FluidType.FUEL_OIL
    params['cargo_type'] = 'LIQUID_BULK'
    return createTank(shapes, ship, params)

# ===========================================================================
# HELPER FUNCTIONS
# ===========================================================================

def get_weight_properties(obj):
    """Get standardized weight properties from any weight object"""
    if hasattr(obj, 'TotalWeight'):
        weight = obj.TotalWeight
    elif hasattr(obj, 'Mass') and obj.Mass > 0:
        weight = obj.Mass
    else:
        weight = 0.0
    
    if hasattr(obj, 'CenterOfGravity'):
        cog = obj.CenterOfGravity
    elif hasattr(obj, 'Shape') and obj.Shape:
        cog = obj.Shape.CenterOfMass
    else:
        cog = App.Vector(0, 0, 0)
    
    if hasattr(obj, 'Category'):
        category = obj.Category
    else:
        category = "BASIC"
    
    return {
        'weight': weight,
        'cog': cog,
        'category': category
    }

def calculate_free_surface_moment(obj):
    """Calculate free surface moment for tanks and bulk cargo"""
    if not hasattr(obj, 'Category'):
        return 0.0
    
    if obj.Category == CargoCategory.TANK.value:
        if hasattr(obj, 'Capacity') and hasattr(obj, 'FillPercentage'):
            # Simplified calculation for tanks
            fill_ratio = obj.FillPercentage / 100.0
            if hasattr(obj, 'Shape') and obj.Shape:
                bbox = obj.Shape.BoundBox
                length = bbox.XLength
                width = bbox.YLength
                I = (length * width**3) / 12.0
                return I * fill_ratio * (1 - fill_ratio)
    
    elif obj.Category == CargoCategory.BULK.value:
        if hasattr(obj, 'FreeSurfaceMoment'):
            return obj.FreeSurfaceMoment
    
    return 0.0
