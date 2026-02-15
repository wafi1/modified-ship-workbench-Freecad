#***************************************************************************
#*                                                                         *
#*   Advanced Weight Creation Task Panel                                   *
#*                                                                         *
#***************************************************************************

import os
import FreeCAD as App
import FreeCADGui as Gui
from FreeCAD import Units
from PySide import QtGui, QtCore
from .. import WeightInstance as Instance
from ..shipUtils import Locale, Selection
from ..shipUtils.Math import compute_inertia

# Define enums locally
class WeightType:
    POINT_MASS = 1
    LINEAR = 2
    AREA = 3
    VOLUME = 4
    TANK = 5
    CRANE_LOAD = 6
    CONTAINER = 7
    GENERAL_CARGO = 8
    BULK_CARGO = 9
    LIQUID_BULK = 10
    VEHICLE = 11
    PROJECT_CARGO = 12

class AdvancedTaskPanel:
    def __init__(self):
        self.name = "advanced ship weight creation"
        
        # Create main widget
        self.form = QtGui.QWidget()
        self.form.setWindowTitle("Create Advanced Weight")
        layout = QtGui.QVBoxLayout(self.form)
        
        # Info label
        info_label = QtGui.QLabel("Select weight type and enter parameters")
        info_label.setStyleSheet("background-color: #e8f4f8; padding: 8px; border: 1px solid #b0d4e0; border-radius: 4px;")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        # Ship selection
        ship_group = QtGui.QGroupBox("Ship Selection")
        ship_layout = QtGui.QHBoxLayout()
        self.ship_combo = QtGui.QComboBox()
        ship_layout.addWidget(QtGui.QLabel("Ship:"))
        ship_layout.addWidget(self.ship_combo)
        ship_layout.addStretch()
        ship_group.setLayout(ship_layout)
        layout.addWidget(ship_group)
        
        # Weight type with ALL options
        type_group = QtGui.QGroupBox("Weight Type")
        type_layout = QtGui.QHBoxLayout()
        self.type_combo = QtGui.QComboBox()
        self.type_combo.addItems([
            "Point Mass", 
            "Linear Density", 
            "Area Density", 
            "Volume Density",
            "Tank",
            "Crane Load",
            "Container",
            "General Cargo",
            "Bulk Cargo",
            "Liquid Bulk",
            "Vehicle",
            "Project Cargo"
        ])
        type_layout.addWidget(QtGui.QLabel("Type:"))
        type_layout.addWidget(self.type_combo)
        self.type_combo.currentIndexChanged.connect(self.onTypeChanged)
        type_group.setLayout(type_layout)
        layout.addWidget(type_group)
        
        # Create a stacked widget for all parameter types
        self.stacked_widget = QtGui.QStackedWidget()
        
        # 1. Point Mass
        point_widget = QtGui.QWidget()
        point_layout = QtGui.QFormLayout(point_widget)
        self.weight_edit = QtGui.QLineEdit("1000 kg")
        self.inertia_group = QtGui.QGroupBox("Inertia Matrix (kg·m²)")
        inertia_layout = QtGui.QGridLayout()
        
        # Inertia matrix labels
        labels = ['Ixx', 'Ixy', 'Ixz', 'Iyx', 'Iyy', 'Iyz', 'Izx', 'Izy', 'Izz']
        self.inertia_edits = {}
        
        for i, label in enumerate(labels):
            row = i // 3
            col = i % 3
            inertia_layout.addWidget(QtGui.QLabel(label), 0, col)
            edit = QtGui.QLineEdit("1000" if 'xx' in label or 'yy' in label or 'zz' in label else "0")
            self.inertia_edits[label] = edit
            inertia_layout.addWidget(edit, row + 1, col)
        
        self.inertia_group.setLayout(inertia_layout)
        point_layout.addRow("Total Mass:", self.weight_edit)
        point_layout.addRow(self.inertia_group)
        self.stacked_widget.addWidget(point_widget)
        
        # 2. Linear Density
        linear_widget = QtGui.QWidget()
        linear_layout = QtGui.QFormLayout(linear_widget)
        self.dens_line_edit = QtGui.QLineEdit("50 kg/m")
        linear_layout.addRow("Linear Density:", self.dens_line_edit)
        self.stacked_widget.addWidget(linear_widget)
        
        # 3. Area Density
        area_widget = QtGui.QWidget()
        area_layout = QtGui.QFormLayout(area_widget)
        self.dens_area_edit = QtGui.QLineEdit("100 kg/m²")
        area_layout.addRow("Area Density:", self.dens_area_edit)
        self.stacked_widget.addWidget(area_widget)
        
        # 4. Volume Density
        volume_widget = QtGui.QWidget()
        volume_layout = QtGui.QFormLayout(volume_widget)
        self.dens_vol_edit = QtGui.QLineEdit("1000 kg/m³")
        volume_layout.addRow("Volume Density:", self.dens_vol_edit)
        self.stacked_widget.addWidget(volume_widget)
        
        # 5. Tank
        tank_widget = QtGui.QWidget()
        tank_layout = QtGui.QFormLayout(tank_widget)
        self.fluid_combo = QtGui.QComboBox()
        self.fluid_combo.addItems(["Fresh Water", "Sea Water", "Fuel Oil", "Diesel Oil", 
                                 "Lube Oil", "Ballast Water", "LNG", "LPG"])
        self.tank_capacity = QtGui.QDoubleSpinBox()
        self.tank_capacity.setSuffix(" m³")
        self.tank_capacity.setRange(0.1, 100000.0)
        self.tank_capacity.setValue(100.0)
        self.fill_percentage = QtGui.QDoubleSpinBox()
        self.fill_percentage.setSuffix(" %")
        self.fill_percentage.setRange(0.0, 100.0)
        self.fill_percentage.setValue(50.0)
        tank_layout.addRow("Fluid Type:", self.fluid_combo)
        tank_layout.addRow("Capacity:", self.tank_capacity)
        tank_layout.addRow("Fill Percentage:", self.fill_percentage)
        self.stacked_widget.addWidget(tank_widget)
        
        # 6. Crane Load
        crane_widget = QtGui.QWidget()
        crane_layout = QtGui.QFormLayout(crane_widget)
        self.crane_mass = QtGui.QLineEdit("5000 kg")
        self.crane_radius = QtGui.QLineEdit("10 m")
        crane_layout.addRow("Load Mass:", self.crane_mass)
        crane_layout.addRow("Radius (for inertia):", self.crane_radius)
        self.stacked_widget.addWidget(crane_widget)
        
        # 7. Container
        container_widget = QtGui.QWidget()
        container_layout = QtGui.QFormLayout(container_widget)
        self.container_mass = QtGui.QLineEdit("2000 kg")
        self.container_type = QtGui.QComboBox()
        self.container_type.addItems(["20' Standard", "40' Standard", "40' High Cube", 
                                    "45' High Cube", "Reefer", "Tank", "Open Top"])
        self.container_teu = QtGui.QDoubleSpinBox()
        self.container_teu.setRange(0.5, 2.5)
        self.container_teu.setSingleStep(0.5)
        self.container_teu.setValue(1.0)
        container_layout.addRow("Container Mass:", self.container_mass)
        container_layout.addRow("Container Type:", self.container_type)
        container_layout.addRow("TEU (Twenty-foot Equivalent):", self.container_teu)
        self.stacked_widget.addWidget(container_widget)
        
        # 8. General Cargo
        cargo_widget = QtGui.QWidget()
        cargo_layout = QtGui.QFormLayout(cargo_widget)
        self.cargo_mass = QtGui.QLineEdit("10000 kg")
        self.cargo_type = QtGui.QComboBox()
        self.cargo_type.addItems(["Pallets", "Drums", "Bags", "Boxes", "Rolls", 
                                "Machinery", "Steel Coils", "Timber"])
        self.stowage_factor = QtGui.QLineEdit("1.5 m³/t")
        cargo_layout.addRow("Cargo Mass:", self.cargo_mass)
        cargo_layout.addRow("Cargo Type:", self.cargo_type)
        cargo_layout.addRow("Stowage Factor:", self.stowage_factor)
        self.stacked_widget.addWidget(cargo_widget)
        
        # 9. Bulk Cargo
        bulk_widget = QtGui.QWidget()
        bulk_layout = QtGui.QFormLayout(bulk_widget)
        self.bulk_density = QtGui.QLineEdit("800 kg/m³")
        self.bulk_angle = QtGui.QDoubleSpinBox()
        self.bulk_angle.setSuffix(" °")
        self.bulk_angle.setRange(0.0, 90.0)
        self.bulk_angle.setValue(30.0)
        self.bulk_type = QtGui.QComboBox()
        self.bulk_type.addItems(["Grain", "Coal", "Iron Ore", "Bauxite", "Cement", 
                               "Fertilizer", "Salt", "Sugar"])
        bulk_layout.addRow("Bulk Density:", self.bulk_density)
        bulk_layout.addRow("Angle of Repose:", self.bulk_angle)
        bulk_layout.addRow("Bulk Type:", self.bulk_type)
        self.stacked_widget.addWidget(bulk_widget)
        
        # 10. Liquid Bulk
        liquid_widget = QtGui.QWidget()
        liquid_layout = QtGui.QFormLayout(liquid_widget)
        self.liquid_density = QtGui.QLineEdit("850 kg/m³")
        self.liquid_viscosity = QtGui.QComboBox()
        self.liquid_viscosity.addItems(["Low", "Medium", "High"])
        self.free_surface = QtGui.QCheckBox("Consider Free Surface Effect")
        self.free_surface.setChecked(True)
        liquid_layout.addRow("Liquid Density:", self.liquid_density)
        liquid_layout.addRow("Viscosity:", self.liquid_viscosity)
        liquid_layout.addRow(self.free_surface)
        self.stacked_widget.addWidget(liquid_widget)
        
        # 11. Vehicle
        vehicle_widget = QtGui.QWidget()
        vehicle_layout = QtGui.QFormLayout(vehicle_widget)
        self.vehicle_mass = QtGui.QLineEdit("15000 kg")
        self.vehicle_type = QtGui.QComboBox()
        self.vehicle_type.addItems(["Car", "Truck", "Bus", "Trailer", "Excavator", 
                                  "Crane", "Tank", "Military"])
        self.axle_count = QtGui.QSpinBox()
        self.axle_count.setRange(2, 10)
        self.axle_count.setValue(4)
        vehicle_layout.addRow("Vehicle Mass:", self.vehicle_mass)
        vehicle_layout.addRow("Vehicle Type:", self.vehicle_type)
        vehicle_layout.addRow("Axle Count:", self.axle_count)
        self.stacked_widget.addWidget(vehicle_widget)
        
        # 12. Project Cargo
        project_widget = QtGui.QWidget()
        project_layout = QtGui.QFormLayout(project_widget)
        self.project_mass = QtGui.QLineEdit("50000 kg")
        self.project_dim = QtGui.QLineEdit("10x5x4 m")
        self.lashing_points = QtGui.QSpinBox()
        self.lashing_points.setRange(0, 20)
        self.lashing_points.setValue(4)
        project_layout.addRow("Project Mass:", self.project_mass)
        project_layout.addRow("Dimensions (LxWxH):", self.project_dim)
        project_layout.addRow("Lashing Points:", self.lashing_points)
        self.stacked_widget.addWidget(project_widget)
        
        layout.addWidget(self.stacked_widget)
        
        # Add stretch
        layout.addStretch()
        
        # Buttons
        button_box = QtGui.QDialogButtonBox()
        button_box.addButton(QtGui.QDialogButtonBox.Ok)
        button_box.addButton(QtGui.QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        self.ships = []
        self.shapes = []
        self.elem_type = 4
        
        # Set initial type to Volume Density
        self.type_combo.setCurrentIndex(3)
    
    def onTypeChanged(self, index):
        """Handle weight type change"""
        print(f"DEBUG: Type changed to index {index}")
        if index < self.stacked_widget.count():
            self.stacked_widget.setCurrentIndex(index)
    
    def getStandardButtons(self):
        """Return standard buttons"""
        return 0
    
    def accept(self):
        """OK button clicked - COMPLETE VERSION"""
        try:
            from . import Tools
            
            if not self.ships or self.ship_combo.currentIndex() < 0:
                self.showError("No ship selected")
                return False
                
            ship = self.ships[self.ship_combo.currentIndex()]
            weight_type_index = self.type_combo.currentIndex()
            
            print(f"DEBUG: Creating weight type index {weight_type_index}")
            
            # Map index to internal weight type
            type_mapping = {
                0: WeightType.POINT_MASS,
                1: WeightType.LINEAR,
                2: WeightType.AREA,
                3: WeightType.VOLUME,
                4: WeightType.TANK,
                5: WeightType.CRANE_LOAD,
                6: WeightType.CONTAINER,
                7: WeightType.GENERAL_CARGO,
                8: WeightType.BULK_CARGO,
                9: WeightType.LIQUID_BULK,
                10: WeightType.VEHICLE,
                11: WeightType.PROJECT_CARGO
            }
            
            weight_type = type_mapping.get(weight_type_index, WeightType.VOLUME)
            
            # Get parameters based on type
            density = None
            inertia = None
            
            if weight_type in [WeightType.POINT_MASS, WeightType.CRANE_LOAD, 
                              WeightType.CONTAINER, WeightType.GENERAL_CARGO,
                              WeightType.VEHICLE, WeightType.PROJECT_CARGO]:
                # Mass-based types
                if weight_type == WeightType.POINT_MASS:
                    value = Locale.fromString(self.weight_edit.text())
                    mass = Units.parseQuantity(value)
                    print(f"DEBUG: Point mass: {mass}")
                    
                elif weight_type == WeightType.CRANE_LOAD:
                    value = Locale.fromString(self.crane_mass.text())
                    mass = Units.parseQuantity(value)
                    print(f"DEBUG: Crane load mass: {mass}")
                    
                elif weight_type == WeightType.CONTAINER:
                    value = Locale.fromString(self.container_mass.text())
                    mass = Units.parseQuantity(value)
                    print(f"DEBUG: Container mass: {mass}")
                    
                elif weight_type == WeightType.GENERAL_CARGO:
                    value = Locale.fromString(self.cargo_mass.text())
                    mass = Units.parseQuantity(value)
                    print(f"DEBUG: Cargo mass: {mass}")
                    
                elif weight_type == WeightType.VEHICLE:
                    value = Locale.fromString(self.vehicle_mass.text())
                    mass = Units.parseQuantity(value)
                    print(f"DEBUG: Vehicle mass: {mass}")
                    
                elif weight_type == WeightType.PROJECT_CARGO:
                    value = Locale.fromString(self.project_mass.text())
                    mass = Units.parseQuantity(value)
                    print(f"DEBUG: Project cargo mass: {mass}")
                
                # Convert mass to density
                total_volume = 0
                for shape in self.shapes:
                    if hasattr(shape, 'Volume'):
                        total_volume += shape.Volume
                
                if total_volume > 0:
                    density_value = mass.Value / total_volume
                    density = Units.Quantity(density_value, Units.Density)
                    print(f"DEBUG: Converted to density: {density}")
                else:
                    self.showError("Shape has no volume for density conversion")
                    return False
                
                # Create inertia matrix
                if weight_type == WeightType.POINT_MASS:
                    # Use user-defined inertia for point mass
                    inertia = self.getInertiaMatrixFromUI()
                else:
                    # Create default inertia for other types
                    inertia = self.createDefaultInertia(mass)
                
            elif weight_type in [WeightType.LINEAR, WeightType.AREA, WeightType.VOLUME]:
                # Density-based types
                if weight_type == WeightType.LINEAR:
                    value = Locale.fromString(self.dens_line_edit.text())
                    density = Units.parseQuantity(value)
                    print(f"DEBUG: Linear density: {density}")
                    
                elif weight_type == WeightType.AREA:
                    value = Locale.fromString(self.dens_area_edit.text())
                    density = Units.parseQuantity(value)
                    print(f"DEBUG: Area density: {density}")
                    
                elif weight_type == WeightType.VOLUME:
                    value = Locale.fromString(self.dens_vol_edit.text())
                    density = Units.parseQuantity(value)
                    print(f"DEBUG: Volume density: {density}")
                
                # Compute inertia from shape
                elem_type = weight_type  # 2=Linear, 3=Area, 4=Volume
                inertia = compute_inertia(self.shapes, elem_type)
                
                # Scale by density
                for i in range(3):
                    for j in range(3):
                        if inertia[i][j] is not None:
                            inertia[i][j] = inertia[i][j] * density
            
            elif weight_type == WeightType.TANK:
                # Tank with fluid
                fluid_type = self.fluid_combo.currentText()
                capacity = self.tank_capacity.value()
                fill_percent = self.fill_percentage.value() / 100.0
                
                # Fluid densities (kg/m³)
                fluid_densities = {
                    "Fresh Water": 1000,
                    "Sea Water": 1025,
                    "Fuel Oil": 850,
                    "Diesel Oil": 830,
                    "Lube Oil": 880,
                    "Ballast Water": 1025,
                    "LNG": 450,
                    "LPG": 510
                }
                
                density_value = fluid_densities.get(fluid_type, 1000)
                actual_mass = capacity * fill_percent * density_value
                
                # Convert to density for shape
                total_volume = 0
                for shape in self.shapes:
                    if hasattr(shape, 'Volume'):
                        total_volume += shape.Volume
                
                if total_volume > 0:
                    density = Units.Quantity(density_value, Units.Density)
                    print(f"DEBUG: Tank fluid density: {density}")
                else:
                    self.showError("Tank shape has no volume")
                    return False
                
                inertia = self.createDefaultInertia(Units.Quantity(f"{actual_mass} kg"))
                
            elif weight_type == WeightType.BULK_CARGO:
                # Bulk cargo
                value = Locale.fromString(self.bulk_density.text())
                density = Units.parseQuantity(value)
                print(f"DEBUG: Bulk density: {density}")
                
                # Compute inertia
                inertia = compute_inertia(self.shapes, 4)  # Use volume
                for i in range(3):
                    for j in range(3):
                        if inertia[i][j] is not None:
                            inertia[i][j] = inertia[i][j] * density
                
            elif weight_type == WeightType.LIQUID_BULK:
                # Liquid bulk
                value = Locale.fromString(self.liquid_density.text())
                density = Units.parseQuantity(value)
                print(f"DEBUG: Liquid bulk density: {density}")
                
                # Compute inertia
                inertia = compute_inertia(self.shapes, 4)  # Use volume
                for i in range(3):
                    for j in range(3):
                        if inertia[i][j] is not None:
                            inertia[i][j] = inertia[i][j] * density
            
            if density is None:
                self.showError("Failed to calculate density")
                return False
            
            print(f"DEBUG: Final density: {density}")
            print(f"DEBUG: Inertia matrix ready")
            
            # Create weight object
            obj = Tools.createWeight(self.shapes, ship, density, inertia)
            
            if obj:
                print(f"DEBUG: Weight created: {obj.Name}")
                
                # Set additional properties based on type
                self.setAdditionalProperties(obj, weight_type, weight_type_index)
                
                # Set view properties
                if hasattr(obj, 'ViewObject'):
                    guiobj = Gui.ActiveDocument.getObject(obj.Name)
                    if guiobj:
                        guiobj.PointSize = 10.00
                
                Gui.Control.closeDialog()
                return True
            else:
                self.showError("Failed to create weight object")
                return False
            
        except Exception as e:
            App.Console.PrintError(f"Error creating weight: {str(e)}\n")
            import traceback
            traceback.print_exc()
            self.showError(f"Failed to create weight: {str(e)}")
            return False
    
    def getInertiaMatrixFromUI(self):
        """Get inertia matrix from UI inputs"""
        I = [
            [Units.Quantity("0 kg*m^2"), Units.Quantity("0 kg*m^2"), Units.Quantity("0 kg*m^2")],
            [Units.Quantity("0 kg*m^2"), Units.Quantity("0 kg*m^2"), Units.Quantity("0 kg*m^2")],
            [Units.Quantity("0 kg*m^2"), Units.Quantity("0 kg*m^2"), Units.Quantity("0 kg*m^2")]
        ]
        
        try:
            I[0][0] = Units.parseQuantity(Locale.fromString(self.inertia_edits['Ixx'].text() + " kg*m^2"))
            I[0][1] = Units.parseQuantity(Locale.fromString(self.inertia_edits['Ixy'].text() + " kg*m^2"))
            I[0][2] = Units.parseQuantity(Locale.fromString(self.inertia_edits['Ixz'].text() + " kg*m^2"))
            I[1][0] = Units.parseQuantity(Locale.fromString(self.inertia_edits['Iyx'].text() + " kg*m^2"))
            I[1][1] = Units.parseQuantity(Locale.fromString(self.inertia_edits['Iyy'].text() + " kg*m^2"))
            I[1][2] = Units.parseQuantity(Locale.fromString(self.inertia_edits['Iyz'].text() + " kg*m^2"))
            I[2][0] = Units.parseQuantity(Locale.fromString(self.inertia_edits['Izx'].text() + " kg*m^2"))
            I[2][1] = Units.parseQuantity(Locale.fromString(self.inertia_edits['Izy'].text() + " kg*m^2"))
            I[2][2] = Units.parseQuantity(Locale.fromString(self.inertia_edits['Izz'].text() + " kg*m^2"))
        except:
            pass  # Use defaults if parsing fails
        
        return I
    
    def createDefaultInertia(self, mass):
        """Create default inertia matrix based on mass"""
        try:
            mass_value = mass.getValueAs("kg").Value
            # Simple formula: I = mass * (dimension/10)²
            base_inertia = mass_value * 1.0  # kg·m²
            
            I = [
                [Units.Quantity(f"{base_inertia} kg*m^2"), 
                 Units.Quantity("0 kg*m^2"), 
                 Units.Quantity("0 kg*m^2")],
                [Units.Quantity("0 kg*m^2"), 
                 Units.Quantity(f"{base_inertia} kg*m^2"), 
                 Units.Quantity("0 kg*m^2")],
                [Units.Quantity("0 kg*m^2"), 
                 Units.Quantity("0 kg*m^2"), 
                 Units.Quantity(f"{base_inertia} kg*m^2")]
            ]
            return I
        except:
            # Fallback
            return [
                [Units.Quantity("1000 kg*m^2"), Units.Quantity("0 kg*m^2"), Units.Quantity("0 kg*m^2")],
                [Units.Quantity("0 kg*m^2"), Units.Quantity("1000 kg*m^2"), Units.Quantity("0 kg*m^2")],
                [Units.Quantity("0 kg*m^2"), Units.Quantity("0 kg*m^2"), Units.Quantity("1000 kg*m^2")]
            ]
    
    def setAdditionalProperties(self, obj, weight_type, type_index):
        """Set additional properties based on weight type"""
        try:
            type_names = [
                "Point Mass", "Linear Density", "Area Density", "Volume Density",
                "Tank", "Crane Load", "Container", "General Cargo",
                "Bulk Cargo", "Liquid Bulk", "Vehicle", "Project Cargo"
            ]
            
            obj.addProperty("App::PropertyString", "WeightType", "Weight", "Type of weight")
            obj.WeightType = type_names[type_index] if type_index < len(type_names) else "Unknown"
            
            # Type-specific properties
            if weight_type == WeightType.TANK:
                obj.addProperty("App::PropertyString", "FluidType", "Tank", "Type of fluid")
                obj.FluidType = self.fluid_combo.currentText()
                obj.addProperty("App::PropertyFloat", "Capacity", "Tank", "Tank capacity in m³")
                obj.Capacity = self.tank_capacity.value()
                obj.addProperty("App::PropertyFloat", "FillPercentage", "Tank", "Fill percentage")
                obj.FillPercentage = self.fill_percentage.value()
                
            elif weight_type == WeightType.CRANE_LOAD:
                obj.addProperty("App::PropertyString", "LoadType", "Crane", "Type of crane load")
                obj.LoadType = "Crane Load"
                obj.addProperty("App::PropertyFloat", "Radius", "Crane", "Radius for inertia calculation")
                try:
                    radius = Units.parseQuantity(Locale.fromString(self.crane_radius.text()))
                    obj.Radius = radius.getValueAs("m").Value
                except:
                    obj.Radius = 10.0
                    
            elif weight_type == WeightType.CONTAINER:
                obj.addProperty("App::PropertyString", "ContainerType", "Container", "Type of container")
                obj.ContainerType = self.container_type.currentText()
                obj.addProperty("App::PropertyFloat", "TEU", "Container", "Twenty-foot Equivalent Units")
                obj.TEU = self.container_teu.value()
                
            elif weight_type == WeightType.GENERAL_CARGO:
                obj.addProperty("App::PropertyString", "CargoType", "Cargo", "Type of cargo")
                obj.CargoType = self.cargo_type.currentText()
                obj.addProperty("App::PropertyString", "StowageFactor", "Cargo", "Stowage factor")
                obj.StowageFactor = self.stowage_factor.text()
                
            elif weight_type == WeightType.BULK_CARGO:
                obj.addProperty("App::PropertyString", "BulkType", "Bulk", "Type of bulk cargo")
                obj.BulkType = self.bulk_type.currentText()
                obj.addProperty("App::PropertyFloat", "AngleOfRepose", "Bulk", "Angle of repose in degrees")
                obj.AngleOfRepose = self.bulk_angle.value()
                
            elif weight_type == WeightType.LIQUID_BULK:
                obj.addProperty("App::PropertyString", "LiquidType", "Liquid", "Type of liquid bulk")
                obj.LiquidType = "Liquid Bulk"
                obj.addProperty("App::PropertyString", "Viscosity", "Liquid", "Viscosity level")
                obj.Viscosity = self.liquid_viscosity.currentText()
                obj.addProperty("App::PropertyBool", "FreeSurfaceEffect", "Liquid", "Consider free surface effect")
                obj.FreeSurfaceEffect = self.free_surface.isChecked()
                
            elif weight_type == WeightType.VEHICLE:
                obj.addProperty("App::PropertyString", "VehicleType", "Vehicle", "Type of vehicle")
                obj.VehicleType = self.vehicle_type.currentText()
                obj.addProperty("App::PropertyInteger", "AxleCount", "Vehicle", "Number of axles")
                obj.AxleCount = self.axle_count.value()
                
            elif weight_type == WeightType.PROJECT_CARGO:
                obj.addProperty("App::PropertyString", "ProjectDimensions", "Project", "Dimensions LxWxH")
                obj.ProjectDimensions = self.project_dim.text()
                obj.addProperty("App::PropertyInteger", "LashingPoints", "Project", "Number of lashing points")
                obj.LashingPoints = self.lashing_points.value()
                
        except Exception as e:
            print(f"DEBUG: Error setting additional properties: {e}")
    
    def reject(self):
        """Cancel button clicked"""
        Gui.Control.closeDialog()
        return True
    
    def setupUi(self):
        """Setup UI"""
        print("DEBUG: setupUi() called")
        
        if self.initValues():
            return True
        
        # Fill ship combo
        icon_path = os.path.join(os.path.dirname(__file__), "../resources/icons/Ship_Instance.svg")
        icon = QtGui.QIcon(icon_path) if os.path.exists(icon_path) else QtGui.QIcon()
        
        self.ship_combo.clear()
        for ship in self.ships:
            self.ship_combo.addItem(icon, ship.Label)
        
        if self.ship_combo.count() > 0:
            self.ship_combo.setCurrentIndex(0)
        
        # Set initial type based on detected shape
        if self.elem_type == 1:
            self.type_combo.setCurrentIndex(0)  # Point Mass
        elif self.elem_type == 2:
            self.type_combo.setCurrentIndex(1)  # Linear
        elif self.elem_type == 3:
            self.type_combo.setCurrentIndex(2)  # Area
        else:
            self.type_combo.setCurrentIndex(3)  # Volume Density
        
        self.stacked_widget.setCurrentIndex(self.type_combo.currentIndex())
        
        return False
    
    def initValues(self):
        """Initialize values"""
        print("DEBUG: initValues() called")
        
        # Get selected shapes
        backends = [Selection.get_solids, Selection.get_surfaces,
                    Selection.get_lines, Selection.get_points]
        for i, backend in enumerate(backends):
            self.shapes = backend()
            self.elem_type = 4 - i
            if self.shapes:
                print(f"DEBUG: Found shapes type {self.elem_type}")
                break
        
        if not self.shapes:
            self.showError("No shapes selected")
            return True
        
        # Get ships
        self.ships = Selection.get_doc_ships()
        if not self.ships:
            self.showError("No ships found")
            return True
        
        return False
    
    def showError(self, message):
        """Show error message"""
        App.Console.PrintError(message + '\n')
        QtGui.QMessageBox.critical(None, "Error", message)

def createTask():
    """Create task panel"""
    print("DEBUG: createTask() called")
    
    try:
        panel = AdvancedTaskPanel()
        Gui.Control.showDialog(panel)
        
        if panel.setupUi():
            Gui.Control.closeDialog()
            return None
        
        return panel
        
    except Exception as e:
        print(f"ERROR in createTask: {e}")
        import traceback
        traceback.print_exc()
        return None

__all__ = ['createTask']
