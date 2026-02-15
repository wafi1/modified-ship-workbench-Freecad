# ERWEITERTE PlotAux.py - Mit grafischer Flächendarstellung und SOLAS-Kriterien
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
        # WICHTIG: Initialisiere plt vor allem anderen!
        self.plt = None
        self.sheet = None
        self.gz_plot_line = None
        self.ax2 = None
        self.roll_data = None
        self.gz_data = None

        self.roll_deg = [r.getValueAs('deg').Value for r in roll]
        self.gz_m = [l.getValueAs('m').Value for l in gz]
        draft_vals = [t.getValueAs('m').Value for t in draft]
        trim_vals = [t.getValueAs('deg').Value for t in trim]
        self.lc_info = lc_info or {}

        # Calculate SOLAS criteria
        self.calculate_solas_criteria()

        # Plot GZ curve mit grafischer Flächendarstellung
        plot_failed = self.plot_with_area(self.roll_deg, self.gz_m)

        if plot_failed:
            FreeCAD.Console.PrintWarning(
                "Plot creation failed, but continuing with spreadsheet...\n")

        # FIX 1: war self.spreadSheet(...) -> korrekt: self.fillSpreadSheet(...)
        #         aber wir rufen spreadSheet() auf, das zuerst das Sheet anlegt
        self.spreadSheet(self.roll_deg, self.gz_m, draft_vals, trim_vals)

        # Show SOLAS results in console
        self.print_solas_results()

    # ------------------------------------------------------------------
    # SOLAS calculations
    # ------------------------------------------------------------------

    def calculate_solas_criteria(self):
        """Calculate SOLAS/IMO stability criteria"""
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
                    x1 = roll_rad[i - 1]
                    y1 = gz_m[i - 1]
                    x2 = roll_rad[i]
                    y2 = gz_m[i]
                    if y1 > 0 and y2 <= 0:
                        vanishing_rad = x1 + (x2 - x1) * (0 - y1) / (y2 - y1)
                        vanishing_angle = np.degrees(vanishing_rad)
                break
        self.vanishing_angle = vanishing_angle

        # 3. Calculate areas
        self.calculate_areas(roll_rad, gz_m)

        # 4. Calculate cumulative areas for each point
        self.calculate_cumulative_areas(roll_rad, gz_m)

        # 5. Check criteria
        self.check_criteria()

    def manual_trapz(self, y, x):
        """Manual trapezoidal integration as fallback for np.trapz"""
        total = 0.0
        for i in range(len(x) - 1):
            dx = x[i + 1] - x[i]
            avg_y = (y[i] + y[i + 1]) / 2.0
            total += dx * avg_y
        return total

    def calculate_cumulative_areas(self, roll_rad, gz_m):
        """Calculate cumulative area from 0° to each roll angle"""
        use_numpy_trapz = hasattr(np, 'trapz')

        self.cumulative_areas = []
        self.incremental_areas = []

        if use_numpy_trapz:
            for i in range(len(roll_rad)):
                if i == 0:
                    self.cumulative_areas.append(0.0)
                    self.incremental_areas.append(0.0)
                else:
                    area = np.trapz(gz_m[:i + 1], roll_rad[:i + 1])
                    self.cumulative_areas.append(area)
                    inc_area = np.trapz(gz_m[i - 1:i + 1], roll_rad[i - 1:i + 1])
                    self.incremental_areas.append(inc_area)
        else:
            cumulative = 0.0
            self.cumulative_areas.append(0.0)
            self.incremental_areas.append(0.0)

            for i in range(1, len(roll_rad)):
                dx = roll_rad[i] - roll_rad[i - 1]
                avg_gz = (gz_m[i - 1] + gz_m[i]) / 2.0
                inc_area = dx * avg_gz
                cumulative += inc_area
                self.cumulative_areas.append(cumulative)
                self.incremental_areas.append(inc_area)

    def calculate_areas(self, roll_rad, gz_m):
        """Calculate areas under GZ curve"""
        use_numpy_trapz = hasattr(np, 'trapz')

        # Area 0-30°
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
                    self.area_30_limit = np.trapz(
                        gz_m[idx_30:idx_limit], roll_rad[idx_30:idx_limit])
                else:
                    self.area_30_limit = self.manual_trapz(
                        gz_m[idx_30:idx_limit], roll_rad[idx_30:idx_limit])
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
            x1, y1 = roll_rad[idx - 1], gz_m[idx - 1]
            x2, y2 = roll_rad[idx],     gz_m[idx]
            self.gz_at_30 = y1 + (y2 - y1) * (target_angle - x1) / (x2 - x1)

    def check_criteria(self):
        """Check SOLAS criteria"""
        self.criteria = {
            'Area 0-30° >= 0.055 m·rad': {
                'value':    self.area_0_30,
                'required': 0.055,
                'passed':   self.area_0_30 >= 0.055
            },
            'Area 0-40°/vanishing >= 0.09 m·rad': {
                'value':    self.area_0_limit,
                'required': 0.09,
                'passed':   self.area_0_limit >= 0.09
            },
            'Area 30-40°/vanishing >= 0.03 m·rad': {
                'value':    self.area_30_limit,
                'required': 0.03,
                'passed':   self.area_30_limit >= 0.03
            },
            'GZ at 30° >= 0.20 m': {
                'value':    self.gz_at_30,
                'required': 0.20,
                'passed':   self.gz_at_30 >= 0.20
            },
            'Max GZ angle >= 25°': {
                'value':    self.max_gz_angle,
                'required': 25.0,
                'passed':   self.max_gz_angle >= 25.0
            }
        }

        self.passed_count  = sum(1 for c in self.criteria.values() if c['passed'])
        self.total_criteria = len(self.criteria)

    def print_solas_results(self):
        """Print SOLAS results to FreeCAD console"""
        FreeCAD.Console.PrintMessage("\n" + "=" * 60 + "\n")
        FreeCAD.Console.PrintMessage("SOLAS/IMO STABILITY CRITERIA CHECK\n")
        FreeCAD.Console.PrintMessage("=" * 60 + "\n")

        FreeCAD.Console.PrintMessage(
            f"Max GZ: {self.max_gz:.3f} m at {self.max_gz_angle:.1f}°\n")
        FreeCAD.Console.PrintMessage(
            f"Vanishing Stability Angle: {self.vanishing_angle:.1f}°\n")
        FreeCAD.Console.PrintMessage(
            f"GZ at 30°: {self.gz_at_30:.3f} m\n\n")

        FreeCAD.Console.PrintMessage("AREA UNDER GZ CURVE:\n")
        FreeCAD.Console.PrintMessage(
            f"  0-30°: {self.area_0_30:.4f} m·rad (min: 0.055)\n")
        FreeCAD.Console.PrintMessage(
            f"  0-40°/vanishing: {self.area_0_limit:.4f} m·rad (min: 0.09)\n")
        FreeCAD.Console.PrintMessage(
            f"  30-40°/vanishing: {self.area_30_limit:.4f} m·rad (min: 0.03)\n\n")

        FreeCAD.Console.PrintMessage("CRITERIA COMPLIANCE:\n")
        for name, crit in self.criteria.items():
            status = "PASS" if crit['passed'] else "FAIL"
            FreeCAD.Console.PrintMessage(
                f"  {name}: {crit['value']:.4f}  [{status}]\n")

        FreeCAD.Console.PrintMessage(
            f"\nSUMMARY: {self.passed_count}/{self.total_criteria} criteria passed\n")

        if self.passed_count == self.total_criteria:
            FreeCAD.Console.PrintMessage(
                "VESSEL COMPLIES WITH SOLAS/IMO STABILITY REQUIREMENTS\n")
        else:
            FreeCAD.Console.PrintMessage(
                "VESSEL DOES NOT COMPLY WITH SOLAS/IMO STABILITY REQUIREMENTS\n")

        FreeCAD.Console.PrintMessage("=" * 60 + "\n")

        # CSV export (only if spreadsheet was created)
        if self.sheet is not None:
            self.export_solas_csv()

    # ------------------------------------------------------------------
    # Plot
    # ------------------------------------------------------------------

    def plot_with_area(self, roll, gz):
        """ Plot the GZ curve with filled area and cumulative area.

        Returns True if plot failed, False if successful.
        """
        # FIX 2: PlotAxes removed – it does not exist in modern FreeCAD.
        #         Axes are obtained via plt.figure.gca() instead.
        try:
            from FreeCAD.Plot import Plot
            FreeCAD.Console.PrintMessage("Using FreeCAD.Plot module\n")
        except ImportError as e:
            try:
                from freecad.plot import Plot
                FreeCAD.Console.PrintMessage("Using freecad.plot module\n")
            except ImportError as e2:
                FreeCAD.Console.PrintWarning(
                    f"Plot module is disabled or not found: {e}, {e2}\n")
                return True

        roll = np.array(roll)
        gz   = np.array(gz)

        positive_mask = roll >= 0
        roll_pos = roll[positive_mask]
        gz_pos   = gz[positive_mask]

        if len(roll_pos) == 0:
            FreeCAD.Console.PrintError("No positive roll angles found!\n")
            return True

        x_max = max(90.0, np.max(roll_pos))
        x_min = 0.0

        # --- Create figure ---
        try:
            plt = Plot.figure('GZ Curve with Areas')
            self.plt = plt
            FreeCAD.Console.PrintMessage(f"Plot figure created: {plt}\n")
        except Exception as e:
            FreeCAD.Console.PrintError(f"Failed to create plot figure: {e}\n")
            self.plt = None
            return True

        # --- Get matplotlib axes via plt.figure.gca() (no PlotAxes needed) ---
        ax1 = None
        try:
            ax1 = plt.figure.gca()
            FreeCAD.Console.PrintMessage(
                f"Got primary axes via plt.figure.gca(): {ax1}\n")
        except Exception as e:
            FreeCAD.Console.PrintWarning(
                f"Could not get matplotlib axes: {e}\n")
            ax1 = None

        # --- GZ curve (thick blue line) ---
        try:
            gz_plot = Plot.plot(roll_pos, gz_pos, 'GZ [m]')
            gz_plot.line.set_linestyle('-')
            gz_plot.line.set_linewidth(2.5)
            gz_plot.line.set_color((0.0, 0.2, 0.8))
            self.gz_plot_line = gz_plot
            FreeCAD.Console.PrintMessage("GZ curve plotted successfully\n")
        except Exception as e:
            FreeCAD.Console.PrintError(f"Failed to plot GZ curve: {e}\n")
            return True

        # --- Filled area under GZ curve ---
        try:
            zero_crossings = np.where(gz_pos <= 0)[0]
            fill_end_idx = zero_crossings[0] if len(zero_crossings) > 0 else len(gz_pos)

            if fill_end_idx > 0:
                roll_fill = roll_pos[:fill_end_idx]
                gz_fill   = gz_pos[:fill_end_idx]

                if ax1 is not None:
                    ax1.fill_between(roll_fill, 0, gz_fill,
                                     alpha=0.3, color='blue',
                                     label='Area under GZ')
                    FreeCAD.Console.PrintMessage("Filled area under curve\n")
                else:
                    area_line = Plot.plot(roll_fill, gz_fill, '_area_')
                    area_line.line.set_linewidth(8.0)
                    area_line.line.set_alpha(0.3)
                    area_line.line.set_color((0.4, 0.6, 1.0))
                    FreeCAD.Console.PrintMessage(
                        "Plotted area as thick line (fallback)\n")
        except Exception as e:
            FreeCAD.Console.PrintWarning(f"Could not fill area: {e}\n")

        # --- Secondary Y-axis for cumulative area ---
        if (hasattr(self, 'cumulative_areas') and
                len(self.cumulative_areas) == len(roll)):
            try:
                cum_areas = np.array(self.cumulative_areas)[positive_mask]

                if ax1 is not None:
                    ax2 = ax1.twinx()
                    ax2.plot(roll_pos, cum_areas, 'r--', linewidth=1.5,
                             label='Cumulative Area [m·rad]')
                    ax2.set_ylabel('Cumulative Area [m·rad]', color='red')
                    ax2.tick_params(axis='y', labelcolor='red')
                    ax2.set_ylim(0, max(cum_areas) * 1.1)
                    self.ax2 = ax2
                    FreeCAD.Console.PrintMessage(
                        "Secondary Y-axis for area created\n")
                else:
                    raise Exception("No ax1 available")

            except Exception as e:
                FreeCAD.Console.PrintWarning(f"Using scaled area fallback: {e}\n")
                try:
                    cum_areas = np.array(self.cumulative_areas)[positive_mask]
                    max_gz    = max(gz_pos)
                    max_area  = max(cum_areas) if len(cum_areas) > 0 else 1.0
                    if max_area > 0:
                        scale_factor  = max_gz / max_area * 0.8
                        scaled_areas  = cum_areas * scale_factor
                        area_plot = Plot.plot(roll_pos, scaled_areas,
                                             f'Area (x{1 / scale_factor:.1f})')
                        area_plot.line.set_linestyle('--')
                        area_plot.line.set_linewidth(1.5)
                        area_plot.line.set_color((0.8, 0.0, 0.0))
                        FreeCAD.Console.PrintMessage(
                            "Plotted scaled area on primary axis\n")
                except Exception as e2:
                    FreeCAD.Console.PrintWarning(
                        f"Scaled area fallback also failed: {e2}\n")

        # --- Reference lines at 30°, 40°, vanishing angle ---
        try:
            max_y = max(gz_pos) * 1.1 if len(gz_pos) > 0 else 1.0

            if x_max >= 30:
                l30 = Plot.plot([30, 30], [0, max_y], '30 deg')
                l30.line.set_linestyle('--')
                l30.line.set_color((0.0, 0.7, 0.0))
                l30.line.set_linewidth(1.0)

            if x_max >= 40:
                l40 = Plot.plot([40, 40], [0, max_y], '40 deg')
                l40.line.set_linestyle('--')
                l40.line.set_color((0.8, 0.5, 0.0))
                l40.line.set_linewidth(1.0)

            if self.vanishing_angle < 90 and self.vanishing_angle <= x_max:
                lv = Plot.plot(
                    [self.vanishing_angle, self.vanishing_angle],
                    [0, max_y],
                    f'Vanishing ({self.vanishing_angle:.1f} deg)')
                lv.line.set_linestyle('--')
                lv.line.set_color((0.8, 0.0, 0.0))
                lv.line.set_linewidth(1.5)

            FreeCAD.Console.PrintMessage("Added reference lines\n")
        except Exception as e:
            FreeCAD.Console.PrintWarning(f"Could not add reference lines: {e}\n")

        # --- Zero line ---
        try:
            zl = Plot.plot([x_min, x_max], [0, 0], '_zero_')
            zl.line.set_linestyle('-')
            zl.line.set_color('black')
            zl.line.set_linewidth(0.5)
        except Exception:
            pass

        # --- Axis labels and limits ---
        try:
            Plot.xlabel('Roll Angle [deg]')
            Plot.xlim(x_min, x_max)
        except Exception as e:
            FreeCAD.Console.PrintWarning(f"Could not set X limits: {e}\n")

        try:
            Plot.ylabel('GZ [m]')
            y_min = min(0, min(gz_pos) * 1.1) if len(gz_pos) > 0 else 0
            y_max = max(gz_pos) * 1.2         if len(gz_pos) > 0 else 1
            Plot.ylim(y_min, y_max)
        except Exception as e:
            FreeCAD.Console.PrintWarning(f"Could not set Y limits: {e}\n")

        # --- Title ---
        try:
            title = (f'GZ Stability Curve\n'
                     f'Max GZ: {self.max_gz:.3f} m at {self.max_gz_angle:.1f} deg | '
                     f'Area 0-30 deg: {self.area_0_30:.4f} m*rad')
            Plot.title(title)
        except Exception as e:
            FreeCAD.Console.PrintWarning(f"Could not set title: {e}\n")

        # --- Grid & legend ---
        try:
            Plot.grid(True)
        except Exception:
            pass

        try:
            Plot.legend(loc='best')
        except Exception:
            pass

        # --- Update ---
        try:
            plt.update()
            FreeCAD.Console.PrintMessage("Plot updated successfully\n")
        except Exception as e:
            FreeCAD.Console.PrintWarning(f"Could not update plot: {e}\n")

        self.roll_data = roll_pos
        self.gz_data   = gz_pos
        return False  # success

    # ------------------------------------------------------------------
    # update  (called by TaskPanel.py after the object is created)
    # ------------------------------------------------------------------

    def update(self, roll, gz, draft, trim):
        """Update the plot and spreadsheet with new data.

        This method is called by TaskPanel.py:
            plt.update(rolls, gzs, drafts, trims)

        Parameters have the same types as __init__:
        roll  -- List of roll angles (FreeCAD quantities, deg)
        gz    -- List of GZ values   (FreeCAD quantities, m)
        draft -- List of drafts      (FreeCAD quantities, m)
        trim  -- List of trim angles (FreeCAD quantities, deg)
        """
        # Convert FreeCAD quantities to plain floats
        self.roll_deg = [r.getValueAs('deg').Value for r in roll]
        self.gz_m     = [l.getValueAs('m').Value   for l in gz]
        draft_vals    = [t.getValueAs('m').Value   for t in draft]
        trim_vals     = [t.getValueAs('deg').Value for t in trim]

        # Recalculate SOLAS criteria with new data
        self.calculate_solas_criteria()

        # Refresh the plot
        plot_failed = self.plot_with_area(self.roll_deg, self.gz_m)
        if plot_failed:
            FreeCAD.Console.PrintWarning(
                "Plot update failed, but continuing with spreadsheet...\n")

        # Refresh the spreadsheet
        self.spreadSheet(self.roll_deg, self.gz_m, draft_vals, trim_vals)

        # Print updated SOLAS results
        self.print_solas_results()

    # ------------------------------------------------------------------
    # Spreadsheet
    # ------------------------------------------------------------------

    def spreadSheet(self, roll, gz, draft, trim):
        """Create (or retrieve) the FreeCAD spreadsheet, then fill it."""
        doc = FreeCAD.ActiveDocument
        if doc is None:
            FreeCAD.Console.PrintError("No active FreeCAD document!\n")
            return

        # Reuse existing sheet or create a new one
        sheet_obj = doc.getObject("GZ_Results")
        if sheet_obj is None:
            sheet_obj = doc.addObject("Spreadsheet::Sheet", "GZ_Results")
            FreeCAD.Console.PrintMessage("Created new spreadsheet 'GZ_Results'\n")
        else:
            FreeCAD.Console.PrintMessage("Reusing existing spreadsheet 'GZ_Results'\n")

        self.sheet = sheet_obj
        self.fillSpreadSheet(roll, gz, draft, trim)

        doc.recompute()

    def fillSpreadSheet(self, roll, gz, draft, trim):
        """Fill the spreadsheet with GZ data and SOLAS summary."""
        if self.sheet is None:
            FreeCAD.Console.PrintError("No spreadsheet available to fill\n")
            return

        s = self.sheet

        # ---------- Header row ----------
        s.set("A1", "roll [deg]")
        s.set("B1", "GZ [m]")
        s.set("C1", "draft [m]")
        s.set("D1", "trim [deg]")
        s.set("E1", "Cumulative Area [m*rad]")

        # ---------- Data rows ----------
        for i, (r, g, d, t) in enumerate(zip(roll, gz, draft, trim)):
            row = i + 2  # data starts at row 2
            s.set(f"A{row}", str(r))
            s.set(f"B{row}", str(g))
            s.set(f"C{row}", str(d))
            s.set(f"D{row}", str(t))
            if hasattr(self, 'cumulative_areas') and i < len(self.cumulative_areas):
                s.set(f"E{row}", str(self.cumulative_areas[i]))
            else:
                s.set(f"E{row}", "")

        # ---------- SOLAS summary block (offset below data) ----------
        offset = len(roll) + 4  # leave two blank rows

        s.set(f"A{offset}",     "SOLAS/IMO CRITERIA")
        s.set(f"A{offset + 1}", "Criterion")
        s.set(f"B{offset + 1}", "Value")
        s.set(f"C{offset + 1}", "Required")
        s.set(f"D{offset + 1}", "Result")

        row = offset + 2
        for name, crit in self.criteria.items():
            s.set(f"A{row}", name)
            s.set(f"B{row}", f"{crit['value']:.4f}")
            s.set(f"C{row}", f"{crit['required']:.4f}")
            s.set(f"D{row}", "PASS" if crit['passed'] else "FAIL")
            row += 1

        # Summary line
        s.set(f"A{row + 1}", "Max GZ [m]")
        s.set(f"B{row + 1}", f"{self.max_gz:.4f}")
        s.set(f"A{row + 2}", "Max GZ angle [deg]")
        s.set(f"B{row + 2}", f"{self.max_gz_angle:.2f}")
        s.set(f"A{row + 3}", "Vanishing angle [deg]")
        s.set(f"B{row + 3}", f"{self.vanishing_angle:.2f}")
        s.set(f"A{row + 4}", "GZ at 30 deg [m]")
        s.set(f"B{row + 4}", f"{self.gz_at_30:.4f}")
        s.set(f"A{row + 5}", "Criteria passed")
        s.set(f"B{row + 5}", f"{self.passed_count}/{self.total_criteria}")

        FreeCAD.Console.PrintMessage(
            f"Spreadsheet filled with {len(roll)} data rows + SOLAS summary\n")

    # ------------------------------------------------------------------
    # CSV export
    # ------------------------------------------------------------------

    def export_solas_csv(self):
        """Export SOLAS results to a CSV file next to the FreeCAD document."""
        try:
            doc = FreeCAD.ActiveDocument
            if doc is None or not doc.FileName:
                FreeCAD.Console.PrintWarning(
                    "Cannot export CSV: document has no file path yet\n")
                return

            base_dir  = os.path.dirname(doc.FileName)
            csv_path  = os.path.join(base_dir, "GZ_SOLAS_results.csv")

            with open(csv_path, 'w', encoding='utf-8') as f:
                f.write("SOLAS/IMO Stability Criteria Results\n\n")
                f.write("Criterion,Value,Required,Result\n")
                for name, crit in self.criteria.items():
                    result = "PASS" if crit['passed'] else "FAIL"
                    f.write(f"{name},{crit['value']:.4f},"
                            f"{crit['required']:.4f},{result}\n")

                f.write(f"\nMax GZ [m],{self.max_gz:.4f}\n")
                f.write(f"Max GZ angle [deg],{self.max_gz_angle:.2f}\n")
                f.write(f"Vanishing angle [deg],{self.vanishing_angle:.2f}\n")
                f.write(f"GZ at 30 deg [m],{self.gz_at_30:.4f}\n")
                f.write(f"Criteria passed,{self.passed_count}/{self.total_criteria}\n")

                f.write("\nRoll [deg],GZ [m],Cumulative Area [m*rad]\n")
                for i, (r, g) in enumerate(zip(self.roll_deg, self.gz_m)):
                    ca = self.cumulative_areas[i] if i < len(self.cumulative_areas) else ""
                    f.write(f"{r:.2f},{g:.4f},{ca:.5f}\n")

            FreeCAD.Console.PrintMessage(f"SOLAS results exported to: {csv_path}\n")

        except Exception as e:
            FreeCAD.Console.PrintWarning(f"CSV export failed: {e}\n")
