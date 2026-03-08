#***************************************************************************
#*                                                                         *
#*   Copyright (c) 2011, 2016 Jose Luis Cercos Pita <jlcercos@gmail.com>   *
#*   Copyright (c) 2024, 2025 Peter Gottwald <yachtdesign@peter-gottwald.de>            *
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

import os
import FreeCAD as App
import FreeCADGui as Gui
from FreeCAD import Units
from PySide import QtGui, QtCore
from .. import WeightInstance as Instance
from ..shipUtils import Locale, Selection
from ..shipUtils.Math import compute_inertia

class AdvancedTaskPanel:
    def __init__(self):
        self.name = "advanced ship weight creation"
        
        # Create main widget
        self.form = QtGui.QWidget()
        self.form.setWindowTitle("Create Weight")
        layout = QtGui.QVBoxLayout(self.form)
        
        # Name input
        name_group = QtGui.QGroupBox("Weight Identification")
        name_layout = QtGui.QFormLayout()
        self.name_edit = QtGui.QLineEdit()
        self.name_edit.setPlaceholderText("Enter weight name (e.g., Lightship, Cargo, Fuel)")
        name_layout.addRow("Name:", self.name_edit)
        name_group.setLayout(name_layout)
        layout.addWidget(name_group)
        
        # Ship selection
        ship_group = QtGui.QGroupBox("Ship Assignment")
        ship_layout = QtGui.QHBoxLayout()
        self.ship_combo = QtGui.QComboBox()
        ship_layout.addWidget(QtGui.QLabel("Assign to Ship:"))
        ship_layout.addWidget(self.ship_combo)
        ship_layout.addStretch()
        ship_group.setLayout(ship_layout)
        layout.addWidget(ship_group)
        
        # Weight type - SIMPLIFIED
        type_group = QtGui.QGroupBox("Weight Properties")
        type_layout = QtGui.QVBoxLayout()
        
        # Type selection
        type_selector_layout = QtGui.QHBoxLayout()
        type_selector_layout.addWidget(QtGui.QLabel("Type:"))
        self.type_combo = QtGui.QComboBox()
        self.type_combo.addItems([
            "Point Mass", 
            "Distributed Load",
            "Tank (Fluid)",
            "Container",
            "General Cargo",
            "Vehicle"
        ])
        type_selector_layout.addWidget(self.type_combo)
        type_selector_layout.addStretch()
        type_layout.addLayout(type_selector_layout)
        
        # Mass input
        mass_layout = QtGui.QHBoxLayout()
        mass_layout.addWidget(QtGui.QLabel("Mass:"))
        self.mass_edit = QtGui.QLineEdit("1000 kg")
        mass_layout.addWidget(self.mass_edit)
        mass_layout.addStretch()
        type_layout.addLayout(mass_layout)
        
        # COG section - MOST IMPORTANT!
        cog_group = QtGui.QGroupBox("Center of Gravity (COG) - Relative to Shape")
        cog_layout = QtGui.QGridLayout()
        
        # Auto-calc button
        self.auto_cog_btn = QtGui.QPushButton("Auto Calculate from Shape")
        self.auto_cog_btn.clicked.connect(self.calculateCOGfromShape)
        cog_layout.addWidget(self.auto_cog_btn, 0, 0, 1, 3)
        
        # COG inputs
        cog_layout.addWidget(QtGui.QLabel("X:"), 1, 0)
        self.cog_x_edit = QtGui.QLineEdit("0 m")
        cog_layout.addWidget(self.cog_x_edit, 1, 1)
        cog_layout.addWidget(QtGui.QLabel("(Longitudinal)"), 1, 2)
        
        cog_layout.addWidget(QtGui.QLabel("Y:"), 2, 0)
        self.cog_y_edit = QtGui.QLineEdit("0 m")
        cog_layout.addWidget(self.cog_y_edit, 2, 1)
        cog_layout.addWidget(QtGui.QLabel("(Transverse)"), 2, 2)
        
        cog_layout.addWidget(QtGui.QLabel("Z:"), 3, 0)
        self.cog_z_edit = QtGui.QLineEdit("0 m")
        cog_layout.addWidget(self.cog_z_edit, 3, 1)
        cog_layout.addWidget(QtGui.QLabel("(Vertical)"), 3, 2)
        
        # Relative/absolute toggle
        self.cog_relative = QtGui.QCheckBox("Relative to shape center (checked) or absolute (unchecked)")
        self.cog_relative.setChecked(True)
        cog_layout.addWidget(self.cog_relative, 4, 0, 1, 3)
        
        cog_group.setLayout(cog_layout)
        type_layout.addWidget(cog_group)
        
        # Additional properties for specific types
        self.additional_widget = QtGui.QWidget()
        self.additional_layout = QtGui.QFormLayout(self.additional_widget)
        type_layout.addWidget(self.additional_widget)
        
        type_group.setLayout(type_layout)
        layout.addWidget(type_group)
        
        # Connect signals
        self.type_combo.currentIndexChanged.connect(self.updateAdditionalProperties)
        
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
        self.shape_cog = None
        self.shape_center = None
        
        # Initialize additional properties
        self.updateAdditionalProperties()
    
    def compute_shape_cog(self, shapes):
        """Calculate Center of Gravity for given shapes"""
        if not shapes:
            return None
        
        try:
            # For multiple shapes, calculate weighted average
            total_volume = 0
            weighted_sum = App.Vector(0, 0, 0)
            
            for shape in shapes:
                if hasattr(shape, 'Volume') and shape.Volume > 0:
                    # Get shape center (bounding box center)
                    bbox = shape.BoundBox
                    center = App.Vector(bbox.Center.x, bbox.Center.y, bbox.Center.z)
                    
                    volume = shape.Volume
                    weighted_sum = weighted_sum.add(center.multiply(volume))
                    total_volume += volume
                else:
                    # For shapes without volume, use bounding box center with small weight
                    bbox = shape.BoundBox
                    center = App.Vector(bbox.Center.x, bbox.Center.y, bbox.Center.z)
                    # Estimate volume from bounding box
                    volume = bbox.XLength * bbox.YLength * bbox.ZLength
                    weighted_sum = weighted_sum.add(center.multiply(volume))
                    total_volume += volume
            
            if total_volume > 0:
                return weighted_sum.multiply(1.0 / total_volume)
            else:
                # Fallback: average of all centers
                avg = App.Vector(0, 0, 0)
                count = 0
                for shape in shapes:
                    bbox = shape.BoundBox
                    avg = avg.add(App.Vector(bbox.Center.x, bbox.Center.y, bbox.Center.z))
                    count += 1
                if count > 0:
                    return avg.multiply(1.0 / count)
                return App.Vector(0, 0, 0)
                
        except Exception as e:
            print(f"DEBUG: Error computing COG: {e}")
            return App.Vector(0, 0, 0)
    
    def calculateCOGfromShape(self):
        """Calculate COG automatically from selected shape"""
        if not self.shapes:
            self.showError("No shape selected")
            return
        
        try:
            # Calculate COG of the shape
            self.shape_cog = self.compute_shape_cog(self.shapes)
            
            # Also get shape center (bounding box center of first shape)
            if self.shapes:
                bbox = self.shapes[0].BoundBox
                self.shape_center = App.Vector(
                    bbox.Center.x,
                    bbox.Center.y,
                    bbox.Center.z
                )
            
            if self.shape_cog:
                # If relative mode, show offset from shape center
                if self.cog_relative.isChecked() and self.shape_center:
                    offset = self.shape_cog.sub(self.shape_center)
                    # Convert mm to m for display
                    self.cog_x_edit.setText(f"{offset.x / 1000.0:.3f} m")
                    self.cog_y_edit.setText(f"{offset.y / 1000.0:.3f} m")
                    self.cog_z_edit.setText(f"{offset.z / 1000.0:.3f} m")
                else:
                    # Show absolute coordinates
                    self.cog_x_edit.setText(f"{self.shape_cog.x / 1000.0:.3f} m")
                    self.cog_y_edit.setText(f"{self.shape_cog.y / 1000.0:.3f} m")
                    self.cog_z_edit.setText(f"{self.shape_cog.z / 1000.0:.3f} m")
                
                print(f"DEBUG: Calculated COG: {self.shape_cog}")
                print(f"DEBUG: Shape center: {self.shape_center}")
            else:
                self.showError("Could not calculate COG from shape")
                
        except Exception as e:
            print(f"DEBUG: Error calculating COG: {e}")
            self.showError(f"Error calculating COG: {str(e)}")
    
    def updateAdditionalProperties(self):
        """Update additional properties based on selected type"""
        # Clear previous widgets
        while self.additional_layout.count():
            child = self.additional_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        
        weight_type = self.type_combo.currentText()
        
        if weight_type == "Tank (Fluid)":
            self.fluid_combo = QtGui.QComboBox()
            self.fluid_combo.addItems(["Fresh Water", "Sea Water", "Fuel Oil", "Diesel", "LNG", "LPG"])
            self.additional_layout.addRow("Fluid Type:", self.fluid_combo)
            
            self.fill_percent = QtGui.QDoubleSpinBox()
            self.fill_percent.setSuffix(" %")
            self.fill_percent.setRange(0, 100)
            self.fill_percent.setValue(100)
            self.additional_layout.addRow("Fill Level:", self.fill_percent)
            
        elif weight_type == "Container":
            self.container_type = QtGui.QComboBox()
            self.container_type.addItems(["20' Standard", "40' Standard", "40' High Cube", "Reefer"])
            self.additional_layout.addRow("Container Type:", self.container_type)
            
            self.teu_spin = QtGui.QDoubleSpinBox()
            self.teu_spin.setRange(0.5, 2.5)
            self.teu_spin.setSingleStep(0.5)
            self.teu_spin.setValue(1.0)
            self.additional_layout.addRow("TEU:", self.teu_spin)
            
        elif weight_type == "General Cargo":
            self.cargo_type = QtGui.QComboBox()
            self.cargo_type.addItems(["Pallets", "Boxes", "Drums", "Rolls", "Machinery", "Steel"])
            self.additional_layout.addRow("Cargo Type:", self.cargo_type)
            
        elif weight_type == "Vehicle":
            self.vehicle_type = QtGui.QComboBox()
            self.vehicle_type.addItems(["Car", "Truck", "Bus", "Trailer", "Construction"])
            self.additional_layout.addRow("Vehicle Type:", self.vehicle_type)
            
            self.axle_count = QtGui.QSpinBox()
            self.axle_count.setRange(2, 10)
            self.axle_count.setValue(4)
            self.additional_layout.addRow("Axles:", self.axle_count)
    
    def getStandardButtons(self):
        """Return standard buttons"""
        return 0
    
    def accept(self):
        """OK button clicked - SIMPLIFIED AND PRACTICAL"""
        try:
            from . import Tools
            
            if not self.ships or self.ship_combo.currentIndex() < 0:
                self.showError("No ship selected")
                return False
                
            ship = self.ships[self.ship_combo.currentIndex()]
            
            # Get weight name
            weight_name = self.name_edit.text().strip()
            if not weight_name:
                weight_name = "Weight"
            
            # Get mass
            mass_str = self.mass_edit.text().strip()
            if not mass_str:
                self.showError("Please enter mass")
                return False
            
            mass = Units.parseQuantity(Locale.fromString(mass_str))
            print(f"DEBUG: Mass: {mass}")
            
            # Get COG
            cog_x = Units.parseQuantity(Locale.fromString(self.cog_x_edit.text()))
            cog_y = Units.parseQuantity(Locale.fromString(self.cog_y_edit.text()))
            cog_z = Units.parseQuantity(Locale.fromString(self.cog_z_edit.text()))
            
            # Convert COG to absolute coordinates if relative
            if self.cog_relative.isChecked() and self.shape_center:
                # Relative to shape center, convert to absolute
                abs_x = self.shape_center.x + cog_x.getValueAs("mm").Value
                abs_y = self.shape_center.y + cog_y.getValueAs("mm").Value
                abs_z = self.shape_center.z + cog_z.getValueAs("mm").Value
                cog_absolute = App.Vector(abs_x, abs_y, abs_z)
            else:
                # Already absolute
                abs_x = cog_x.getValueAs("mm").Value
                abs_y = cog_y.getValueAs("mm").Value
                abs_z = cog_z.getValueAs("mm").Value
                cog_absolute = App.Vector(abs_x, abs_y, abs_z)
            
            print(f"DEBUG: COG Absolute: {cog_absolute}")
            print(f"DEBUG: COG in meters: ({abs_x/1000:.3f}, {abs_y/1000:.3f}, {abs_z/1000:.3f}) m")
            
            # Convert mass to density for the Tools function
            total_volume = 0
            for shape in self.shapes:
                if hasattr(shape, 'Volume'):
                    total_volume += shape.Volume
            
            if total_volume > 0:
                density_value = mass.getValueAs("kg").Value / total_volume
                density = Units.Quantity(density_value, Units.Density)
                print(f"DEBUG: Density: {density}")
                print(f"DEBUG: Total volume: {total_volume} mm³")
            else:
                # For point masses without volume, use a default density
                density = Units.Quantity("1000 kg/m^3")
                print(f"DEBUG: Using default density: {density}")
            
            # Create simple inertia matrix based on mass
            # Simple approximation: I = mass * (characteristic_length^2) / 12
            characteristic_length = 1.0  # meters default
            
            if self.shapes:
                bbox = self.shapes[0].BoundBox
                # Use average dimension as characteristic length
                char_length = (bbox.XLength + bbox.YLength + bbox.ZLength) / (3 * 1000.0)  # mm to m
                if char_length > 0:
                    characteristic_length = char_length
            
            base_inertia = mass.getValueAs("kg").Value * (characteristic_length ** 2) / 12.0
            
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
            
            print(f"DEBUG: Characteristic length: {characteristic_length:.3f}m")
            print(f"DEBUG: Base inertia: {base_inertia:.1f} kg·m²")
            
            # Create weight object
            obj = Tools.createWeight(self.shapes, ship, density, I)
            
            if obj:
                # Rename object
                obj.Label = weight_name
                
                # Store COG as property
                if not hasattr(obj, 'COG'):
                    obj.addProperty("App::PropertyVector", "COG", "Weight", "Center of Gravity")
                obj.COG = cog_absolute
                
                # Store mass as property
                if not hasattr(obj, 'Mass'):
                    obj.addProperty("App::PropertyFloat", "Mass", "Weight", "Mass in kg")
                obj.Mass = mass.getValueAs("kg").Value
                
                # Store type
                weight_type = self.type_combo.currentText()
                if not hasattr(obj, 'WeightType'):
                    obj.addProperty("App::PropertyString", "WeightType", "Weight", "Type of weight")
                obj.WeightType = weight_type
                
                # Store additional properties based on type
                if weight_type == "Tank (Fluid)":
                    if not hasattr(obj, 'FluidType'):
                        obj.addProperty("App::PropertyString", "FluidType", "Tank", "Type of fluid")
                    obj.FluidType = self.fluid_combo.currentText()
                    if not hasattr(obj, 'FillPercentage'):
                        obj.addProperty("App::PropertyFloat", "FillPercentage", "Tank", "Fill percentage")
                    obj.FillPercentage = self.fill_percent.value()
                    
                elif weight_type == "Container":
                    if not hasattr(obj, 'ContainerType'):
                        obj.addProperty("App::PropertyString", "ContainerType", "Container", "Type of container")
                    obj.ContainerType = self.container_type.currentText()
                    if not hasattr(obj, 'TEU'):
                        obj.addProperty("App::PropertyFloat", "TEU", "Container", "Twenty-foot Equivalent Units")
                    obj.TEU = self.teu_spin.value()
                    
                elif weight_type == "General Cargo":
                    if not hasattr(obj, 'CargoType'):
                        obj.addProperty("App::PropertyString", "CargoType", "Cargo", "Type of cargo")
                    obj.CargoType = self.cargo_type.currentText()
                    
                elif weight_type == "Vehicle":
                    if not hasattr(obj, 'VehicleType'):
                        obj.addProperty("App::PropertyString", "VehicleType", "Vehicle", "Type of vehicle")
                    obj.VehicleType = self.vehicle_type.currentText()
                    if not hasattr(obj, 'AxleCount'):
                        obj.addProperty("App::PropertyInteger", "AxleCount", "Vehicle", "Number of axles")
                    obj.AxleCount = self.axle_count.value()
                
                # Set view properties
                if hasattr(obj, 'ViewObject'):
                    guiobj = Gui.ActiveDocument.getObject(obj.Name)
                    if guiobj:
                        guiobj.PointSize = 10.00
                        # Show COG as point
                        if hasattr(guiobj, 'ShowCenterOfGravity'):
                            guiobj.ShowCenterOfGravity = True
                
                # Recompute to update properties
                App.ActiveDocument.recompute()
                
                print(f"DEBUG: Weight '{weight_name}' created successfully")
                print(f"DEBUG: - Mass: {obj.Mass} kg")
                print(f"DEBUG: - COG: {obj.COG}")
                print(f"DEBUG: - Type: {obj.WeightType}")
                
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
        
        # Auto-generate name based on selected shape and type
        if self.shapes:
            shape_name = self.shapes[0].Label if hasattr(self.shapes[0], 'Label') and self.shapes[0].Label else "Shape"
            weight_type = self.type_combo.currentText()
            default_name = f"{weight_type} - {shape_name}"
            self.name_edit.setText(default_name)
        
        # Auto-calculate COG
        self.calculateCOGfromShape()
        
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
                print(f"DEBUG: Found {len(self.shapes)} shapes of type {self.elem_type}")
                # Print shape info
                for idx, shape in enumerate(self.shapes):
                    shape_label = shape.Label if hasattr(shape, 'Label') and shape.Label else f"Shape_{idx}"
                    print(f"  Shape {idx}: {shape_label}")
                    if hasattr(shape, 'Volume'):
                        print(f"    Volume: {shape.Volume:.1f} mm³")
                    bbox = shape.BoundBox
                    print(f"    BBox Center: ({bbox.Center.x:.1f}, {bbox.Center.y:.1f}, {bbox.Center.z:.1f}) mm")
                    print(f"    BBox Size: ({bbox.XLength:.1f}, {bbox.YLength:.1f}, {bbox.ZLength:.1f}) mm")
                break
        
        if not self.shapes:
            self.showError("No shapes selected. Please select a shape first.")
            return True
        
        # Get ships
        self.ships = Selection.get_doc_ships()
        if not self.ships:
            self.showError("No ship found in document. Please create a ship first.")
            return True
        
        print(f"DEBUG: Found {len(self.ships)} ships")
        
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
