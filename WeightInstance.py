#***************************************************************************
#*                                                                         *
#*   Advanced Weight Instance for FreeCAD Ships Workbench                  *
#*   Extended version supporting all cargo types                           *
#*                                                                         *
#*   Based on original work by Jose Luis Cercos Pita                       *
#*   Extended for: Tanks, General Cargo, Bulk Cargo, Containers, etc.      *
#*                                                                         *
#***************************************************************************

import os
import time
from math import *
import FreeCAD as App
from FreeCAD import Base, Vector, Units
import Part
from .shipUtils import Paths, Math
from .shipUtils.Math import compute_inertia
from enum import Enum

QT_TRANSLATE_NOOP = App.Qt.QT_TRANSLATE_NOOP

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
# ORIGINAL FUNCTIONS (unchanged for compatibility)
# ===========================================================================

def add_weight_props(obj):
    """This function adds the properties to a weight instance, in case they are
    not already created

    Position arguments:
    obj -- Part::FeaturePython object

    Returns:
    The same input object, that now has the properties added
    """
    try:
        obj.getPropertyByName('IsWeight')
    except AttributeError:
        tooltip = QT_TRANSLATE_NOOP(
            "App::Property",
            "True if it is a valid weight instance, False otherwise")
        obj.addProperty("App::PropertyBool",
                        "IsWeight",
                        "Weight",
                        tooltip).IsWeight = True
    try:
        obj.getPropertyByName('Mass')
    except AttributeError:
        tooltip = QT_TRANSLATE_NOOP(
            "App::Property",
            "Mass [kg]")
        obj.addProperty("App::PropertyFloat",
                        "Mass",
                        "Weight",
                        tooltip).Mass = 0.0
    try:
        obj.getPropertyByName('LineDens')
    except AttributeError:
        tooltip = QT_TRANSLATE_NOOP(
            "App::Property",
            "Linear density [kg / m]")
        obj.addProperty("App::PropertyFloat",
                        "LineDens",
                        "Weight",
                        tooltip).LineDens = 0.0
    try:
        obj.getPropertyByName('AreaDens')
    except AttributeError:
        tooltip = QT_TRANSLATE_NOOP(
            "App::Property",
            "Area density [kg / m^2]")
        obj.addProperty("App::PropertyFloat",
                        "AreaDens",
                        "Weight",
                        tooltip).AreaDens = 0.0
    try:
        obj.getPropertyByName('Dens')
    except AttributeError:
        tooltip = QT_TRANSLATE_NOOP(
            "App::Property",
            "Density [kg / m^3]")
        obj.addProperty("App::PropertyFloat",
                        "Dens",
                        "Weight",
                        tooltip).Dens = 0.0
    try:
        obj.getPropertyByName('Inertia')
    except AttributeError:
        tooltip = QT_TRANSLATE_NOOP(
            "App::Property",
            "Inertia [kg * m^2]")
        obj.addProperty("App::PropertyMatrix",
                        "Inertia",
                        "Weight",
                        tooltip).Inertia = (0, 0, 0, 0,
                                            0, 0, 0, 0,
                                            0, 0, 0, 0,
                                            0, 0, 0, 1)
    return obj

def add_advanced_weight_props(obj, weight_type):
    """Add advanced properties based on weight type
    
    Parameters:
    obj -- Part::FeaturePython object
    weight_type -- WeightType enum
    """
    # Common advanced properties
    try:
        obj.getPropertyByName('Category')
    except AttributeError:
        tooltip = QT_TRANSLATE_NOOP(
            "App::Property",
            "Weight category")
        obj.addProperty("App::PropertyString",
                        "Category",
                        "Advanced",
                        tooltip)
    
    try:
        obj.getPropertyByName('CenterOfGravity')
    except AttributeError:
        tooltip = QT_TRANSLATE_NOOP(
            "App::Property",
            "Center of gravity position")
        obj.addProperty("App::PropertyVector",
                        "CenterOfGravity",
                        "Advanced",
                        tooltip)
    
    try:
        obj.getPropertyByName('TotalWeight')
    except AttributeError:
        tooltip = QT_TRANSLATE_NOOP(
            "App::Property",
            "Total weight in kg")
        obj.addProperty("App::PropertyFloat",
                        "TotalWeight",
                        "Advanced",
                        tooltip).TotalWeight = 0.0
    
    # Type-specific properties
    if weight_type == WeightType.TANK or weight_type == WeightType.LIQUID_BULK:
        # Tank properties
        try:
            obj.getPropertyByName('FluidType')
        except AttributeError:
            tooltip = QT_TRANSLATE_NOOP(
                "App::Property",
                "Type of fluid in tank")
            obj.addProperty("App::PropertyEnumeration",
                            "FluidType",
                            "Tank",
                            tooltip)
            obj.FluidType = [f.name for f in FluidType]
        
        try:
            obj.getPropertyByName('FillPercentage')
        except AttributeError:
            tooltip = QT_TRANSLATE_NOOP(
                "App::Property",
                "Percentage of tank filled")
            obj.addProperty("App::PropertyPercent",
                            "FillPercentage",
                            "Tank",
                            tooltip).FillPercentage = 0.0
        
        try:
            obj.getPropertyByName('Capacity')
        except AttributeError:
            tooltip = QT_TRANSLATE_NOOP(
                "App::Property",
                "Total capacity in cubic meters")
            obj.addProperty("App::PropertyFloat",
                            "Capacity",
                            "Tank",
                            tooltip).Capacity = 100.0
    
    elif weight_type == WeightType.GENERAL_CARGO:
        # General Cargo properties
        try:
            obj.getPropertyByName('CargoType')
        except AttributeError:
            tooltip = QT_TRANSLATE_NOOP(
                "App::Property",
                "Type of general cargo")
            obj.addProperty("App::PropertyEnumeration",
                            "CargoType",
                            "GeneralCargo",
                            tooltip)
            obj.CargoType = ['MACHINERY', 'STEEL_PARTS', 'TIMBER', 'PIPES', 
                           'ELECTRICAL', 'MACHINE_PARTS', 'PALLETS', 'OTHER']
        
        try:
            obj.getPropertyByName('SecuringRequired')
        except AttributeError:
            tooltip = QT_TRANSLATE_NOOP(
                "App::Property",
                "Cargo securing required")
            obj.addProperty("App::PropertyBool",
                            "SecuringRequired",
                            "GeneralCargo",
                            tooltip).SecuringRequired = True
        
        try:
            obj.getPropertyByName('TippingAngle')
        except AttributeError:
            tooltip = QT_TRANSLATE_NOOP(
                "App::Property",
                "Critical tipping angle in degrees")
            obj.addProperty("App::PropertyFloat",
                            "TippingAngle",
                            "GeneralCargo",
                            tooltip).TippingAngle = 25.0
    
    elif weight_type == WeightType.BULK_CARGO:
        # Bulk Cargo properties
        try:
            obj.getPropertyByName('CargoType')
        except AttributeError:
            tooltip = QT_TRANSLATE_NOOP(
                "App::Property",
                "Type of bulk material")
            obj.addProperty("App::PropertyEnumeration",
                            "CargoType",
                            "BulkCargo",
                            tooltip)
            obj.CargoType = ['GRAIN', 'COAL', 'IRON_ORE', 'BAUXITE', 'CEMENT',
                           'SUGAR', 'RICE', 'FERTILIZER', 'SALT', 'GRAVEL',
                           'SAND', 'OTHER']
        
        try:
            obj.getPropertyByName('FillPercentage')
        except AttributeError:
            tooltip = QT_TRANSLATE_NOOP(
                "App::Property",
                "Fill percentage")
            obj.addProperty("App::PropertyPercent",
                            "FillPercentage",
                            "BulkCargo",
                            tooltip).FillPercentage = 90.0
        
        try:
            obj.getPropertyByName('AngleOfRepose')
        except AttributeError:
            tooltip = QT_TRANSLATE_NOOP(
                "App::Property",
                "Angle of repose in degrees")
            obj.addProperty("App::PropertyFloat",
                            "AngleOfRepose",
                            "BulkCargo",
                            tooltip).AngleOfRepose = 25.0
        
        try:
            obj.getPropertyByName('FreeSurfaceMoment')
        except AttributeError:
            tooltip = QT_TRANSLATE_NOOP(
                "App::Property",
                "Free surface moment (m⁴)")
            obj.addProperty("App::PropertyFloat",
                            "FreeSurfaceMoment",
                            "BulkCargo",
                            tooltip).FreeSurfaceMoment = 0.0
    
    elif weight_type == WeightType.CONTAINER:
        # Container properties
        try:
            obj.getPropertyByName('ContainerType')
        except AttributeError:
            tooltip = QT_TRANSLATE_NOOP(
                "App::Property",
                "ISO container type")
            obj.addProperty("App::PropertyEnumeration",
                            "ContainerType",
                            "Container",
                            tooltip)
            obj.ContainerType = ['20FT_DRY', '40FT_DRY', '20FT_REEFER', 
                               '40FT_REEFER', '20FT_TANK', '40FT_HC', '45FT_HC']
        
        try:
            obj.getPropertyByName('TareWeight')
        except AttributeError:
            tooltip = QT_TRANSLATE_NOOP(
                "App::Property",
                "Tare weight in kg")
            obj.addProperty("App::PropertyFloat",
                            "TareWeight",
                            "Container",
                            tooltip).TareWeight = 2200.0
        
        try:
            obj.getPropertyByName('ActualPayload')
        except AttributeError:
            tooltip = QT_TRANSLATE_NOOP(
                "App::Property",
                "Actual payload in kg")
            obj.addProperty("App::PropertyFloat",
                            "ActualPayload",
                            "Container",
                            tooltip).ActualPayload = 0.0
    
    elif weight_type == WeightType.CRANE_LOAD:
        # Crane Load properties
        try:
            obj.getPropertyByName('CraneID')
        except AttributeError:
            tooltip = QT_TRANSLATE_NOOP(
                "App::Property",
                "Crane identifier")
            obj.addProperty("App::PropertyString",
                            "CraneID",
                            "CraneLoad",
                            tooltip).CraneID = "CRANE01"
        
        try:
            obj.getPropertyByName('BoomAngle')
        except AttributeError:
            tooltip = QT_TRANSLATE_NOOP(
                "App::Property",
                "Boom angle in degrees")
            obj.addProperty("App::PropertyFloat",
                            "BoomAngle",
                            "CraneLoad",
                            tooltip).BoomAngle = 45.0
        
        try:
            obj.getPropertyByName('IsSuspended')
        except AttributeError:
            tooltip = QT_TRANSLATE_NOOP(
                "App::Property",
                "Load is currently suspended")
            obj.addProperty("App::PropertyBool",
                            "IsSuspended",
                            "CraneLoad",
                            tooltip).IsSuspended = True
    
    elif weight_type == WeightType.VEHICLE:
        # Vehicle properties
        try:
            obj.getPropertyByName('VehicleType')
        except AttributeError:
            tooltip = QT_TRANSLATE_NOOP(
                "App::Property",
                "Type of vehicle")
            obj.addProperty("App::PropertyEnumeration",
                            "VehicleType",
                            "Vehicle",
                            tooltip)
            obj.VehicleType = ['CAR', 'TRUCK', 'TRAILER', 'BUS', 'EXCAVATOR',
                             'CRANE', 'TRACTOR', 'OTHER']
    
    elif weight_type == WeightType.PROJECT_CARGO:
        # Project Cargo properties
        try:
            obj.getPropertyByName('CriticalTippingAngle')
        except AttributeError:
            tooltip = QT_TRANSLATE_NOOP(
                "App::Property",
                "Critical tipping angle in degrees")
            obj.addProperty("App::PropertyFloat",
                            "CriticalTippingAngle",
                            "ProjectCargo",
                            tooltip).CriticalTippingAngle = 15.0
        
        try:
            obj.getPropertyByName('LashingForce')
        except AttributeError:
            tooltip = QT_TRANSLATE_NOOP(
                "App::Property",
                "Required lashing force in kN")
            obj.addProperty("App::PropertyFloat",
                            "LashingForce",
                            "ProjectCargo",
                            tooltip).LashingForce = 50.0
    
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
    # Create appropriate object name based on type
    type_names = {
        WeightType.TANK: "Tank",
        WeightType.GENERAL_CARGO: "GeneralCargo",
        WeightType.BULK_CARGO: "BulkCargo",
        WeightType.CONTAINER: "Container",
        WeightType.CRANE_LOAD: "CraneLoad",
        WeightType.VEHICLE: "Vehicle",
        WeightType.PROJECT_CARGO: "ProjectCargo",
        WeightType.LIQUID_BULK: "LiquidBulk"
    }
    
    obj_name = type_names.get(weight_type, "Weight")
    obj = App.ActiveDocument.addObject("Part::FeaturePython", obj_name)
    
    # Initialize as weight
    weight = Weight(obj, shapes, ship)
    
    # Add advanced properties
    add_advanced_weight_props(obj, weight_type)
    
    # Set category
    category_map = {
        WeightType.TANK: CargoCategory.TANK,
        WeightType.GENERAL_CARGO: CargoCategory.GENERAL,
        WeightType.BULK_CARGO: CargoCategory.BULK,
        WeightType.CONTAINER: CargoCategory.CONTAINER,
        WeightType.CRANE_LOAD: CargoCategory.CRANE,
        WeightType.VEHICLE: CargoCategory.VEHICLE,
        WeightType.PROJECT_CARGO: CargoCategory.PROJECT,
        WeightType.LIQUID_BULK: CargoCategory.TANK
    }
    
    if weight_type in category_map:
        obj.Category = category_map[weight_type].value
    
    # Set type-specific properties from params
    set_advanced_properties(obj, weight_type, params)
    
    # Set to ship
    weights = ship.Weights[:]
    weights.append(obj.Name)
    ship.Weights = weights
    
    # Clean up
    if hasattr(ship, 'Proxy'):
        if hasattr(ship.Proxy, 'cleanWeights'):
            ship.Proxy.cleanWeights(ship)
        if hasattr(ship.Proxy, 'cleanTanks'):
            ship.Proxy.cleanTanks(ship)
        if hasattr(ship.Proxy, 'cleanLoadConditions'):
            ship.Proxy.cleanLoadConditions(ship)
    
    App.ActiveDocument.recompute()
    return obj

def set_advanced_properties(obj, weight_type, params):
    """Set advanced properties based on parameters"""
    
    # Common properties
    if 'weight' in params:
        obj.TotalWeight = params['weight']
        # Also set appropriate density property
        if hasattr(obj, 'Mass'):
            obj.Mass = params['weight']
    
    if 'position' in params:
        obj.Placement.Base = params['position']
    
    if 'center_of_gravity' in params:
        obj.CenterOfGravity = params['center_of_gravity']
    else:
        # Default COG from shape
        if hasattr(obj, 'Shape') and obj.Shape:
            obj.CenterOfGravity = obj.Shape.CenterOfMass
    
    # Type-specific properties
    if weight_type == WeightType.TANK or weight_type == WeightType.LIQUID_BULK:
        if 'fluid_type' in params:
            if isinstance(params['fluid_type'], str):
                obj.FluidType = params['fluid_type']
            else:
                obj.FluidType = params['fluid_type'].name
        
        if 'fill_percentage' in params:
            obj.FillPercentage = params['fill_percentage']
        
        if 'capacity' in params:
            obj.Capacity = params['capacity']
        
        # Calculate content weight
        if hasattr(obj, 'Capacity') and hasattr(obj, 'FillPercentage'):
            fluid = FluidType[obj.FluidType] if obj.FluidType in FluidType.__members__ else FluidType.SEA_WATER
            obj.TotalWeight = obj.Capacity * (obj.FillPercentage / 100.0) * fluid.value
    
    elif weight_type == WeightType.GENERAL_CARGO:
        if 'cargo_type' in params:
            obj.CargoType = params['cargo_type']
        
        if 'securing_required' in params:
            obj.SecuringRequired = params['securing_required']
        
        if 'tipping_angle' in params:
            obj.TippingAngle = params['tipping_angle']
        
        if 'length' in params and 'width' in params and 'height' in params:
            # Create bounding box geometry
            length = params['length']
            width = params['width']
            height = params['height']
            position = params.get('position', Vector(0, 0, 0))
            obj.Shape = Part.makeBox(length, width, height, position)
    
    elif weight_type == WeightType.BULK_CARGO:
        if 'cargo_type' in params:
            obj.CargoType = params['cargo_type']
        
        if 'fill_percentage' in params:
            obj.FillPercentage = params['fill_percentage']
        
        if 'angle_of_repose' in params:
            obj.AngleOfRepose = params['angle_of_repose']
        
        if 'length' in params and 'width' in params and 'height' in params:
            # Create geometry with fill height
            length = params['length']
            width = params['width']
            height = params['height']
            fill_height = height * (obj.FillPercentage / 100.0)
            position = params.get('position', Vector(0, 0, 0))
            obj.Shape = Part.makeBox(length, width, fill_height, position)
            
            # Calculate free surface moment
            free_surface_I = (length * width**3) / 12.0
            fill_ratio = obj.FillPercentage / 100.0
            reduction_factor = get_bulk_reduction_factor(obj.CargoType)
            obj.FreeSurfaceMoment = free_surface_I * fill_ratio * (1 - fill_ratio) * reduction_factor
    
    elif weight_type == WeightType.CONTAINER:
        if 'container_type' in params:
            obj.ContainerType = params['container_type']
        
        if 'tare_weight' in params:
            obj.TareWeight = params['tare_weight']
        
        if 'actual_payload' in params:
            obj.ActualPayload = params['actual_payload']
            obj.TotalWeight = obj.TareWeight + obj.ActualPayload
        
        # Set dimensions based on container type
        if '20FT' in obj.ContainerType:
            length, width, height = 6.058, 2.438, 2.591
        elif '40FT' in obj.ContainerType:
            length, width, height = 12.192, 2.438, 2.591
        else:
            length, width, height = 6.058, 2.438, 2.591
        
        position = params.get('position', Vector(0, 0, 0))
        obj.Shape = Part.makeBox(length, width, height, position)
        
        # Set COG (typical for containers: 45% height)
        obj.CenterOfGravity = Vector(
            position.x + length/2.0,
            position.y + width/2.0,
            position.z + height * 0.45
        )
    
    elif weight_type == WeightType.CRANE_LOAD:
        if 'crane_id' in params:
            obj.CraneID = params['crane_id']
        
        if 'boom_angle' in params:
            obj.BoomAngle = params['boom_angle']
        
        if 'hook_position' in params:
            obj.CenterOfGravity = params['hook_position']
    
    elif weight_type == WeightType.VEHICLE:
        if 'vehicle_type' in params:
            obj.VehicleType = params['vehicle_type']
    
    elif weight_type == WeightType.PROJECT_CARGO:
        if 'critical_tipping_angle' in params:
            obj.CriticalTippingAngle = params['critical_tipping_angle']
        
        if 'lashing_force' in params:
            obj.LashingForce = params['lashing_force']

def get_bulk_reduction_factor(cargo_type):
    """Get reduction factor for free surface effect based on material"""
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

# ===========================================================================
# ORIGINAL WEIGHT CLASS (with minor extensions)
# ===========================================================================

class Weight:
    def __init__(self, obj, shapes, ship):
        """ Transform a generic object to a ship instance.

        Position arguments:
        obj -- Part::FeaturePython created object which should be transformed
        in a weight instance.
        shapes -- Set of shapes which will compound the weight element.
        ship -- Ship where the weight is allocated.
        """
        add_weight_props(obj)
        if shapes:
            obj.Shape = Part.makeCompound(shapes)
        obj.Proxy = self

    def onChanged(self, fp, prop):
        """Detects the ship data changes.

        Position arguments:
        fp -- Part::FeaturePython object affected.
        prop -- Modified property name.
        """
        if prop == "Mass":
            pass

    def execute(self, fp):
        """Detects the entity recomputations.

        Position arguments:
        fp -- Part::FeaturePython object affected.
        """
        pass

    def _getPuntualMass(self, fp, shape):
        """Compute the mass of a puntual element.

        Position arguments:
        fp -- Part::FeaturePython object affected.
        shape -- Vertex shape object.
        """
        return Units.parseQuantity('{0} kg'.format(fp.Mass))

    def _getLinearMass(self, fp, shape):
        """Compute the mass of a linear element.

        Position arguments:
        fp -- Part::FeaturePython object affected.
        shape -- Edge shape object.
        """
        rho = Units.parseQuantity('{0} kg/m'.format(fp.LineDens))
        l = Units.Quantity(shape.Length, Units.Length)
        return rho * l

    def _getAreaMass(self, fp, shape):
        """Compute the mass of an area element.

        Position arguments:
        fp -- Part::FeaturePython object affected.
        shape -- Face shape object.
        """
        rho = Units.parseQuantity('{0} kg/m^2'.format(fp.AreaDens))
        a = Units.Quantity(shape.Area, Units.Area)
        return rho * a

    def _getVolumetricMass(self, fp, shape):
        """Compute the mass of a volumetric element.

        Position arguments:
        fp -- Part::FeaturePython object affected.
        shape -- Solid shape object.
        """
        rho = Units.parseQuantity('{0} kg/m^3'.format(fp.Dens))
        v = Units.Quantity(shape.Volume, Units.Volume)
        return rho * v

    def getMass(self, fp):
        """Compute the mass of the object, already taking into account the
        type of subentities.

        Position arguments:
        fp -- Part::FeaturePython object affected.

        Returned value:
        Object mass
        """
        # For advanced weights, use TotalWeight if available
        if hasattr(fp, 'TotalWeight') and fp.TotalWeight > 0:
            return Units.parseQuantity('{0} kg'.format(fp.TotalWeight))
        
        # Original calculation for basic weights
        m = Units.parseQuantity('0 kg')
        for s in fp.Shape.Solids:
            m += self._getVolumetricMass(fp, s)
        for f in fp.Shape.Faces:
            m += self._getAreaMass(fp, f)
        for e in fp.Shape.Edges:
            m += self._getLinearMass(fp, e)
        for v in fp.Shape.Vertexes:
            m += self._getPuntualMass(fp, v)
        return m

    def _getPuntualMoment(self, fp, shape):
        """Compute the moment of a puntual element (respect to 0, 0, 0).

        Position arguments:
        fp -- Part::FeaturePython object affected.
        shape -- Vertex shape object.
        """
        m = self._getPuntualMass(fp, shape)
        x = Units.Quantity(shape.X, Units.Length)
        y = Units.Quantity(shape.Y, Units.Length)
        z = Units.Quantity(shape.Z, Units.Length)
        return (m * x, m * y, m * z)

    def _getLinearMoment(self, fp, shape):
        """Compute the mass of a linear element (respect to 0, 0, 0).

        Position arguments:
        fp -- Part::FeaturePython object affected.
        shape -- Edge shape object.
        """
        m = self._getLinearMass(fp, shape)
        cog = shape.CenterOfMass
        x = Units.Quantity(cog.x, Units.Length)
        y = Units.Quantity(cog.y, Units.Length)
        z = Units.Quantity(cog.z, Units.Length)
        return (m * x, m * y, m * z)

    def _getAreaMoment(self, fp, shape):
        """Compute the mass of an area element (respect to 0, 0, 0).

        Position arguments:
        fp -- Part::FeaturePython object affected.
        shape -- Face shape object.
        """
        m = self._getAreaMass(fp, shape)
        cog = shape.CenterOfMass
        x = Units.Quantity(cog.x, Units.Length)
        y = Units.Quantity(cog.y, Units.Length)
        z = Units.Quantity(cog.z, Units.Length)
        return (m * x, m * y, m * z)

    def _getVolumetricMoment(self, fp, shape):
        """Compute the mass of a volumetric element (respect to 0, 0, 0).

        Position arguments:
        fp -- Part::FeaturePython object affected.
        shape -- Solid shape object.
        """
        m = self._getVolumetricMass(fp, shape)
        cog = shape.CenterOfMass
        x = Units.Quantity(cog.x, Units.Length)
        y = Units.Quantity(cog.y, Units.Length)
        z = Units.Quantity(cog.z, Units.Length)
        return (m * x, m * y, m * z)

    def getMoment(self, fp):
        """Compute the mass of the object, already taking into account the
        type of subentities.

        Position arguments:
        fp -- Part::FeaturePython object affected.

        Returned value:
        List of moments toward x, y and z
        """
        # For advanced weights with defined COG
        if hasattr(fp, 'CenterOfGravity') and hasattr(fp, 'TotalWeight') and fp.TotalWeight > 0:
            m = Units.parseQuantity('{0} kg'.format(fp.TotalWeight))
            cog = fp.CenterOfGravity
            x = Units.Quantity(cog.x, Units.Length)
            y = Units.Quantity(cog.y, Units.Length)
            z = Units.Quantity(cog.z, Units.Length)
            return (m * x, m * y, m * z)
        
        # Original calculation for basic weights
        m = [Units.parseQuantity('0 kg*m'),
             Units.parseQuantity('0 kg*m'),
             Units.parseQuantity('0 kg*m')]
        for s in fp.Shape.Solids:
            mom = self._getVolumetricMoment(fp, s)
            for i in range(len(m)):
                m[i] = m[i] + mom[i]
        for f in fp.Shape.Faces:
            mom = self._getAreaMoment(fp, f)
            for i in range(len(m)):
                m[i] = m[i] + mom[i]
        for e in fp.Shape.Edges:
            mom = self._getLinearMoment(fp, e)
            for i in range(len(m)):
                m[i] = m[i] + mom[i]
        for v in fp.Shape.Vertexes:
            mom = self._getPuntualMoment(fp, v)
            for i in range(len(m)):
                m[i] = m[i] + mom[i]
        return m

    def getCenterOfMass(self, fp):
        """Compute the mass of the object, already taking into account the
        type of subentities.

        Position arguments:
        fp -- Part::FeaturePython object affected.

        Returned value:
        Center of Mass vector
        """
        # For advanced weights, use stored COG if available
        if hasattr(fp, 'CenterOfGravity'):
            return fp.CenterOfGravity
        
        # Original calculation
        mass = self.getMass(fp)
        moment = self.getMoment(fp)
        cog = []
        for i in range(len(moment)):
            cog.append(moment[i] / mass)
        return Vector(cog[0].Value, cog[1].Value, cog[2].Value)

    def getInertia(self, fp, center=None):
        """Get the inertia with respect a point.

        Position arguments:
        fp -- Part::FeaturePython object affected.
    
        Keyword arguments:
        center -- FreeCAD.Vector The reference point. If None the center of
                  gravity is considered

        Returned value:
        Inertia matrix [kg * m^2]
        """
        # For advanced weights with custom inertia
        if hasattr(fp, 'Category') and fp.Category == CargoCategory.CRANE.value:
            # Simplified inertia for crane loads
            mass = self.getMass(fp)
            if mass.Value > 0:
                # Assume spherical inertia
                I = [[mass.Value, 0, 0],
                     [0, mass.Value, 0],
                     [0, 0, mass.Value]]
                return I
        
        # Original inertia calculation
        mass = self.getMass(fp)
        if fp.Mass != 0.0:
            add_weight_props(fp)  # For backward compatibility
            I = [[fp.Inertia.A[i + j*4] for j in range(3)] for i in range(3)]
        else:
            if fp.LineDens != 0.0:
                dens = fp.LineDens
                I = compute_inertia(fp.Shape.Edges, 2)
            if fp.AreaDens != 0.0:
                dens = fp.AreaDens
                I = compute_inertia(fp.Shape.Faces, 3)
            if fp.Dens != 0.0:
                dens = fp.Dens
                I = compute_inertia(fp.Shape.Solids, 3)
            for i, row in enumerate(I):
                for j, value in enumerate(row):
                    I[i][j] = (dens * value).getValueAs('kg*m^2').Value
        return I

# ===========================================================================
# VIEW PROVIDER (unchanged)
# ===========================================================================

class ViewProviderWeight:
    def __init__(self, obj):
        """Add this view provider to the selected object.

        Keyword arguments:
        obj -- Object which must be modified.
        """
        obj.Proxy = self

    def attach(self, obj):
        """Setup the scene sub-graph of the view provider, this method is
        mandatory.
        """
        return

    def updateData(self, fp, prop):
        """If a property of the handled feature has changed we have the chance
        to handle this here.

        Keyword arguments:
        fp -- Part::FeaturePython object affected.
        prop -- Modified property name.
        """
        return

    def getDisplayModes(self, obj):
        """Return a list of display modes.

        Keyword arguments:
        obj -- Object associated with the view provider.
        """
        modes = []
        return modes

    def getDefaultDisplayMode(self):
        """Return the name of the default display mode. It must be defined in
        getDisplayModes."""
        return "Flat Lines"

    def setDisplayMode(self, mode):
        """Map the display mode defined in attach with those defined in
        getDisplayModes. Since they have the same names nothing needs to be
        done. This method is optional.

        Keyword arguments:
        mode -- Mode to be activated.
        """
        return mode

    def onChanged(self, vp, prop):
        """Detects the ship view provider data changes.

        Keyword arguments:
        vp -- View provider object affected.
        prop -- Modified property name.
        """
        pass

    def __getstate__(self):
        """When saving the document this object gets stored using Python's
        cPickle module. Since we have some un-pickable here (the Coin stuff)
        we must define this method to return a tuple of all pickable objects
        or None.
        """
        return None

    def __setstate__(self, state):
        """When restoring the pickled object from document we have the chance
        to set some internals here. Since no data were pickled nothing needs
        to be done here.
        """
        return None

    def getIcon(self):
        """Returns the icon for this kind of objects."""
        return os.path.join(os.path.dirname(__file__),
                            "resources/icons/",
                            "Ship_Weight.svg")
