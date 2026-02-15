# ERWEITERTE PlotAux.py - Minimal mit SOLAS-Kriterien
import os
import math
import numpy as np
from PySide import QtGui, QtCore
import FreeCAD
import FreeCADGui
import Spreadsheet
from ..shipHydrostatics.PlotAux import autolim


class Plot(object):
    def __init__(self, roll, gz, draft, trim, lc_info=None):
        """ Plot the GZ curve with SOLAS criteria
        
        Position arguments:
        roll -- List of roll angles (in degrees).
        gz -- List of GZ values (in meters).
        draft -- List of equilibrium drafts (in meters).
        trim -- List of equilibrium trim angles (in degrees).
        lc_info -- Optional dict with LoadCondition info
        """
        self.roll_deg = [r.getValueAs('deg').Value for r in roll]
        self.gz_m = [l.getValueAs('m').Value for l in gz]
        draft_vals = [t.getValueAs('m').Value for t in draft]
        trim_vals = [t.getValueAs('deg').Value for t in trim]
        self.lc_info = lc_info or {}
        
        # Calculate SOLAS criteria
        self.calculate_solas_criteria()
        
        # Original plotting
        self.plot(self.roll_deg, self.gz_m)
        self.spreadSheet(self.roll_deg, self.gz_m, draft_vals, trim_vals)
        
        # Show SOLAS results in console
        self.print_solas_results()
    
    def calculate_solas_criteria(self):
        """Calculate SOLAS/IMO stability criteria"""
        # Convert to numpy for calculations
        import numpy as np
        roll_rad = np.radians(self.roll_deg)
        gz_m = np.array(self.gz_m)
        
        # 1. Find max GZ and its angle
        max_gz_idx = np.argmax(gz_m)
        self.max_gz = gz_m[max_gz_idx]
        self.max_gz_angle = self.roll_deg[max_gz_idx]
        
        # 2. Find vanishing stability angle
        vanishing_angle = 90  # Default
        for i in range(max_gz_idx + 1, len(gz_m)):
            if gz_m[i] <= 0:
                if i > 0:
                    # Linear interpolation
                    x1 = roll_rad[i-1]
                    y1 = gz_m[i-1]
                    x2 = roll_rad[i]
                    y2 = gz_m[i]
                    if y1 > 0 and y2 <= 0:
                        vanishing_rad = x1 + (x2 - x1) * (0 - y1) / (y2 - y1)
                        vanishing_angle = np.degrees(vanishing_rad)
                break
        self.vanishing_angle = vanishing_angle
        
        # 3. Calculate areas
        self.calculate_areas(roll_rad, gz_m)
        
        # 4. Check criteria
        self.check_criteria()
    
    def manual_trapz(self, y, x):
        """Manual trapezoidal integration as fallback for np.trapz"""
        total = 0.0
        for i in range(len(x) - 1):
            dx = x[i+1] - x[i]
            avg_y = (y[i] + y[i+1]) / 2.0
            total += dx * avg_y
        return total
    
    def calculate_areas(self, roll_rad, gz_m):
        """Calculate areas under GZ curve"""
        # Determine integration method
        use_numpy_trapz = hasattr(np, 'trapz')
        
        # Area 0-30° (0-0.5236 rad)
        idx_30 = np.searchsorted(roll_rad, np.radians(30))
        if idx_30 > 0:
            if use_numpy_trapz:
                self.area_0_30 = np.trapz(gz_m[:idx_30], roll_rad[:idx_30])
            else:
                self.area_0_30 = self.manual_trapz(gz_m[:idx_30], roll_rad[:idx_30])
        else:
            self.area_0_30 = 0
        
        # Area 0-40° or vanishing angle
        angle_limit = min(np.radians(40), np.radians(self.vanishing_angle))
        idx_limit = np.searchsorted(roll_rad, angle_limit)
        if idx_limit > 0:
            if use_numpy_trapz:
                self.area_0_limit = np.trapz(gz_m[:idx_limit], roll_rad[:idx_limit])
            else:
                self.area_0_limit = self.manual_trapz(gz_m[:idx_limit], roll_rad[:idx_limit])
        else:
            self.area_0_limit = 0
        
        # Area 30-40° or 30-vanishing
        if angle_limit > np.radians(30):
            idx_30 = np.searchsorted(roll_rad, np.radians(30))
            if idx_30 < idx_limit:
                if use_numpy_trapz:
                    self.area_30_limit = np.trapz(gz_m[idx_30:idx_limit], roll_rad[idx_30:idx_limit])
                else:
                    self.area_30_limit = self.manual_trapz(gz_m[idx_30:idx_limit], roll_rad[idx_30:idx_limit])
            else:
                self.area_30_limit = 0
        else:
            self.area_30_limit = 0
        
        # GZ at 30° (interpolated)
        target_angle = np.radians(30)
        idx = np.searchsorted(roll_rad, target_angle)
        if idx == 0:
            self.gz_at_30 = gz_m[0]
        elif idx >= len(gz_m):
            self.gz_at_30 = gz_m[-1]
        else:
            # Linear interpolation
            x1 = roll_rad[idx-1]
            y1 = gz_m[idx-1]
            x2 = roll_rad[idx]
            y2 = gz_m[idx]
            self.gz_at_30 = y1 + (y2 - y1) * (target_angle - x1) / (x2 - x1)
    
    def check_criteria(self):
        """Check SOLAS criteria"""
        self.criteria = {
            'Area 0-30° ≥ 0.055 m·rad': {
                'value': self.area_0_30,
                'required': 0.055,
                'passed': self.area_0_30 >= 0.055
            },
            'Area 0-40°/vanishing ≥ 0.09 m·rad': {
                'value': self.area_0_limit,
                'required': 0.09,
                'passed': self.area_0_limit >= 0.09
            },
            'Area 30-40°/vanishing ≥ 0.03 m·rad': {
                'value': self.area_30_limit,
                'required': 0.03,
                'passed': self.area_30_limit >= 0.03
            },
            'GZ at 30° ≥ 0.20 m': {
                'value': self.gz_at_30,
                'required': 0.20,
                'passed': self.gz_at_30 >= 0.20
            },
            'Max GZ angle ≥ 25°': {
                'value': self.max_gz_angle,
                'required': 25.0,
                'passed': self.max_gz_angle >= 25.0
            }
        }
        
        # Count passed criteria
        self.passed_count = sum(1 for crit in self.criteria.values() if crit['passed'])
        self.total_criteria = len(self.criteria)
    
    def print_solas_results(self):
        """Print SOLAS results to FreeCAD console"""
        FreeCAD.Console.PrintMessage("\n" + "="*60 + "\n")
        FreeCAD.Console.PrintMessage("SOLAS/IMO STABILITY CRITERIA CHECK\n")
        FreeCAD.Console.PrintMessage("="*60 + "\n")
        
        FreeCAD.Console.PrintMessage(f"Max GZ: {self.max_gz:.3f} m at {self.max_gz_angle:.1f}°\n")
        FreeCAD.Console.PrintMessage(f"Vanishing Stability Angle: {self.vanishing_angle:.1f}°\n")
        FreeCAD.Console.PrintMessage(f"GZ at 30°: {self.gz_at_30:.3f} m\n")
        FreeCAD.Console.PrintMessage("\n")
        
        FreeCAD.Console.PrintMessage("AREA UNDER GZ CURVE:\n")
        FreeCAD.Console.PrintMessage(f"  0-30°: {self.area_0_30:.4f} m·rad (min: 0.055)\n")
        FreeCAD.Console.PrintMessage(f"  0-40°/vanishing: {self.area_0_limit:.4f} m·rad (min: 0.09)\n")
        FreeCAD.Console.PrintMessage(f"  30-40°/vanishing: {self.area_30_limit:.4f} m·rad (min: 0.03)\n")
        FreeCAD.Console.PrintMessage("\n")
        
        FreeCAD.Console.PrintMessage("CRITERIA COMPLIANCE:\n")
        for name, crit in self.criteria.items():
            status = "✓ PASS" if crit['passed'] else "✗ FAIL"
            FreeCAD.Console.PrintMessage(f"  {name}: {crit['value']:.4f} {status}\n")
        
        FreeCAD.Console.PrintMessage(f"\nSUMMARY: {self.passed_count}/{self.total_criteria} criteria passed\n")
        
        if self.passed_count == self.total_criteria:
            FreeCAD.Console.PrintMessage("✓ VESSEL COMPLIES WITH SOLAS/IMO STABILITY REQUIREMENTS\n")
        else:
            FreeCAD.Console.PrintMessage("✗ VESSEL DOES NOT COMPLY WITH SOLAS/IMO STABILITY REQUIREMENTS\n")
        
        FreeCAD.Console.PrintMessage("="*60 + "\n")
        
        # Export to CSV if requested
        if hasattr(self, 'sheet'):
            self.export_solas_csv()
    
    def export_solas_csv(self):
        """Export SOLAS results to CSV in spreadsheet"""
        sheet = self.sheet
        
        # Add SOLAS results starting at column F
        sheet.set("F1", "SOLAS/IMO STABILITY ANALYSIS")
        sheet.set("F2", f"Max GZ: {self.max_gz:.3f} m")
        sheet.set("F3", f"Angle of Max GZ: {self.max_gz_angle:.1f} deg")
        sheet.set("F4", f"Vanishing Angle: {self.vanishing_angle:.1f} deg")
        sheet.set("F5", f"GZ at 30°: {self.gz_at_30:.3f} m")
        
        sheet.set("F7", "Area under GZ curve:")
        sheet.set("F8", f"0-30°: {self.area_0_30:.4f} m·rad")
        sheet.set("F9", f"0-40°/vanishing: {self.area_0_limit:.4f} m·rad")
        sheet.set("F10", f"30-40°/vanishing: {self.area_30_limit:.4f} m·rad")
        
        sheet.set("F12", "SOLAS Criteria:")
        row = 13
        for name, crit in self.criteria.items():
            status = "PASS" if crit['passed'] else "FAIL"
            sheet.set(f"F{row}", f"{name}: {crit['value']:.4f} ({status})")
            row += 1
        
        sheet.set(f"F{row+1}", f"Summary: {self.passed_count}/{self.total_criteria} passed")
        
        # Recompute
        FreeCAD.activeDocument().recompute()
    
    def update(self, roll, gz, draft, trim):
        roll_deg = [r.getValueAs('deg').Value for r in roll]
        gz_m = [l.getValueAs('m').Value for l in gz]
        draft_vals = [t.getValueAs('m').Value for t in draft]
        trim_vals = [t.getValueAs('deg').Value for t in trim]
        
        # Update calculations
        self.roll_deg = roll_deg
        self.gz_m = gz_m
        self.calculate_solas_criteria()
        
        # Update spreadsheet
        self.fillSpreadSheet(roll_deg, gz_m, draft_vals, trim_vals)
        
        # Update plot if available
        if self.plt is None:
            return
        self.gz.line.set_data(roll_deg, gz_m)
        for ax in self.plt.axesList:
            autolim(ax)
        self.plt.update()
        
        # Print updated results
        self.print_solas_results()
    
    # REST DES ORIGINALEN CODES (plot, fillSpreadSheet, spreadSheet Methoden)
    # bleiben unverändert wie in deiner Original-Datei
    

    def plot(self, roll, gz):
        """ Plot the GZ curve and stability work."""
        try:
            from FreeCAD.Plot import Plot
        except ImportError:
            try:
                from freecad.plot import Plot
            except ImportError:
                msg = FreeCAD.Qt.translate(
                    "ship_console",
                    "Plot module is disabled, so I cannot perform the plot")
                FreeCAD.Console.PrintWarning(
                    "Plot module is disabled, so I cannot perform the plot\n")
                return True
        plt = Plot.figure('GZ')
        self.plt = plt

        # Main GZ curve
        gz_plot = Plot.plot(roll, gz, 'GZ curve')
        gz_plot.line.set_linestyle('-')
        gz_plot.line.set_linewidth(2.0)
        gz_plot.line.set_color((0.0, 0.0, 1.0))  # Blue
        self.gz = gz_plot

        # Calculate and plot cumulative area (stability work)
        if len(roll) > 1:
            import numpy as np
            roll_rad = np.radians(roll)
            
            # Cumulative area (work)
            cumulative_work = []
            current_area = 0
            for i in range(len(roll)):
                if i == 0:
                    cumulative_work.append(0)
                else:
                    # Trapezoidal integration
                    area_segment = 0.5 * (gz[i-1] + gz[i]) * (roll_rad[i] - roll_rad[i-1])
                    current_area += area_segment
                    cumulative_work.append(current_area)
            
            # Plot stability work on secondary y-axis
            ax2 = plt.axes().twinx()
            work_plot = Plot.plot(roll, cumulative_work, 'Stability Work', axes=ax2)
            work_plot.line.set_linestyle('--')
            work_plot.line.set_linewidth(1.5)
            work_plot.line.set_color((1.0, 0.0, 0.0))  # Red
            ax2.set_ylabel(r'Work $[m \cdot rad]$', color='red')
            ax2.yaxis.label.set_fontsize(16)
            
            self.work_plot = work_plot

        ax = Plot.axes()
        Plot.xlabel(r'$\phi \; [\mathrm{deg}]$')
        Plot.ylabel(r'$GZ \; [\mathrm{m}]$')
        ax.xaxis.label.set_fontsize(20)
        ax.yaxis.label.set_fontsize(20)

        Plot.grid(True)
        plt.update()
        return False


    def fillSpreadSheet(self, roll, gz, draft, trim):
        s = self.sheet

        # Print the header
        s.set("A1", "roll [deg]")
        s.set("B1", "GZ [m]")
        s.set("C1", "draft [m]")
        s.set("D1", "trim [deg]")

        # Print the data
        for i in range(len(roll)):
            s.set("A{}".format(i + 2), str(roll[i]))
            s.set("B{}".format(i + 2), str(gz[i]))
            s.set("C{}".format(i + 2), str(draft[i]))
            s.set("D{}".format(i + 2), str(trim[i]))

        # Recompute
        FreeCAD.activeDocument().recompute()

    def spreadSheet(self, roll, gz, draft, trim):
        """ Create a Spreadsheet with the results

        Position arguments:
        roll -- List of roll angles (in degrees).
        gz -- List of GZ values (in meters).
        draft -- List of equilibrium drafts (in meters).
        trim -- List of equilibrium trim angles (in degrees).
        """
        self.sheet = FreeCAD.activeDocument().addObject('Spreadsheet::Sheet',
                                                        'GZ')
        self.fillSpreadSheet(roll, gz, draft, trim)
