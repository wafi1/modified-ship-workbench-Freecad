# PlotAux.py – Combined GZ stability report: text summary + chart in one figure
#
# Layout:
#   ┌─────────────────────────────────────────┐
#   │  Load Case Summary                      │  (top)
#   ├─────────────────────────────────────────┤
#   │  SOLAS Stability Criteria Table         │  (middle)
#   ├─────────────────────────────────────────┤
#   │  GZ Curve  +  Cumulative Area           │  (bottom, large)
#   │  (left Y-axis / right Y-axis)           │
#   └─────────────────────────────────────────┘
#
# Clicking the toolbar "Save" button defaults to PDF and saves all three sections.

import numpy as np
import FreeCAD
import FreeCADGui


# ---------------------------------------------------------
# Trapezoidal integration – compatible with all NumPy versions
# ---------------------------------------------------------
if hasattr(np, 'trapezoid'):
    _trapz = np.trapezoid
elif hasattr(np, 'trapz'):
    _trapz = np.trapz
else:
    def _trapz(y, x):
        return np.sum((x[1:] - x[:-1]) * (y[1:] + y[:-1]) / 2.0)


def _integrate(roll_rad, gz_m, a0_deg, a1_deg, vanishing_deg=None):
    if vanishing_deg is not None:
        a1_deg = min(a1_deg, vanishing_deg)
    if a1_deg <= a0_deg:
        return 0.0
    angles    = np.linspace(np.radians(a0_deg), np.radians(a1_deg), 200)
    interp_gz = np.interp(angles, roll_rad, gz_m)
    return float(_trapz(interp_gz, angles))


# ---------------------------------------------------------
# Safe matplotlib import
# ---------------------------------------------------------
def _get_matplotlib():
    try:
        import matplotlib
        import matplotlib.pyplot as plt
        return matplotlib, plt
    except ImportError:
        return None, None


# ---------------------------------------------------------
# Main class
# ---------------------------------------------------------
class Plot:
    def __init__(self, roll, gz, draft, trim, lc_info=None):
        self.lc_info  = lc_info or {}
        self.roll_deg = [r.getValueAs('deg').Value for r in roll]
        self.gz_m     = [g.getValueAs('m').Value   for g in gz]
        self.draft_m  = [d.getValueAs('m').Value   for d in draft]
        self.trim_deg = [t.getValueAs('deg').Value for t in trim]
        self.disp_kg  = []

        self.sheet = None

        # 1) SOLAS calculation
        self._recalculate()

        # 2) Spreadsheet (must finish before plot)
        self.spreadSheet()

        # 3) Combined report figure
        self._create_report_figure()

        # 4) Console summary
        self.print_solas_results()

    # ------------------------------------------------------------------
    # Set displacement
    # ------------------------------------------------------------------
    def set_displacement(self, disp_list):
        self.disp_kg = [float(d) for d in disp_list]
        self.spreadSheet()

    # ------------------------------------------------------------------
    # SOLAS calculation
    # ------------------------------------------------------------------
    def _recalculate(self):
        roll_rad = np.radians(np.array(self.roll_deg))
        gz_m     = np.array(self.gz_m)
        if len(gz_m) == 0:
            self._init_empty_solas()
            return

        max_idx = int(np.argmax(gz_m))
        self.max_gz          = float(gz_m[max_idx])
        self.max_gz_angle    = float(self.roll_deg[max_idx])
        self.vanishing_angle = float(self.roll_deg[-1])

        for i in range(max_idx + 1, len(gz_m)):
            if gz_m[i] <= 0.0 and gz_m[i - 1] > 0.0:
                x1, y1 = roll_rad[i - 1], gz_m[i - 1]
                x2, y2 = roll_rad[i],     gz_m[i]
                self.vanishing_angle = float(
                    np.degrees(x1 + (x2 - x1) * (-y1) / (y2 - y1))
                )
                break

        vd = self.vanishing_angle
        self.area_0_30     = _integrate(roll_rad, gz_m, 0,  30, vd)
        self.area_0_limit  = _integrate(roll_rad, gz_m, 0,  40, vd)
        self.area_30_limit = _integrate(roll_rad, gz_m, 30, 40, vd)
        self.gz_at_30      = float(np.interp(np.radians(30), roll_rad, gz_m))

        # ── GM₀: prefer the value explicitly passed via lc_info ──────────
        # lc_info['gm'] should be KM - KG (corrected for free surfaces)
        # as calculated in the FreeCAD spreadsheet (e.g. cell G4).
        # The curve-fit fallback (GZ/phi slope at small angles) is kept
        # only when no spreadsheet value is available, and triggers a
        # console warning so the discrepancy is immediately visible.
        gm_from_lc = self.lc_info.get('gm', None)
        if gm_from_lc is not None:
            self.GM0        = float(gm_from_lc)
            self.gm_source  = 'spreadsheet'
        else:
            # Fallback: linear regression GZ/phi in 0-10 deg range
            self.GM0       = 0.0
            small = (np.array(self.roll_deg) > 0) & (np.array(self.roll_deg) < 10)
            if np.sum(small) >= 2:
                A        = np.vstack([roll_rad[small], np.ones(np.sum(small))]).T
                self.GM0 = float(
                    np.linalg.lstsq(A, np.array(gz_m)[small], rcond=None)[0][0]
                )
            if self.GM0 == 0.0:
                pos = np.where(np.array(self.roll_deg) > 0)[0]
                if len(pos):
                    phi      = roll_rad[pos[0]]
                    self.GM0 = float(gz_m[pos[0]] / phi) if phi > 1e-6 else 0.0
            self.gm_source = 'curve fit (fallback)'
            FreeCAD.Console.PrintWarning(
                f"GM0 not supplied via lc_info['gm'] – "
                f"estimated from GZ curve slope: {self.GM0:.3f} m. "
                f"Pass the spreadsheet GM to get the correct value.\n"
            )

        self.cumulative_areas = [0.0]
        for i in range(1, len(roll_rad)):
            self.cumulative_areas.append(
                _integrate(roll_rad, gz_m, 0,
                           float(np.degrees(roll_rad[i])), vd)
            )

        self.criteria = {
            'Area  0-30 deg >= 0.055 m*rad':              {'value': self.area_0_30,     'required': 0.055},
            'Area  0-40 deg / vanishing >= 0.090 m*rad':  {'value': self.area_0_limit,  'required': 0.090},
            'Area 30-40 deg / vanishing >= 0.030 m*rad':  {'value': self.area_30_limit, 'required': 0.030},
            'GZ at 30 deg >= 0.200 m':                    {'value': self.gz_at_30,      'required': 0.200},
            'Max GZ angle >= 25 deg':                     {'value': self.max_gz_angle,  'required': 25.0 },
            'Initial GM >= 0.150 m':                      {'value': self.GM0,           'required': 0.150},
        }
        for v in self.criteria.values():
            v['passed'] = v['value'] >= v['required']

        self.passed_count   = sum(1 for c in self.criteria.values() if c['passed'])
        self.total_criteria = len(self.criteria)

    def _init_empty_solas(self):
        self.max_gz = self.max_gz_angle = self.vanishing_angle = 0.0
        self.area_0_30 = self.area_0_limit = self.area_30_limit = 0.0
        self.gz_at_30  = self.GM0 = 0.0
        self.cumulative_areas = []
        self.criteria         = {}
        self.passed_count     = self.total_criteria = 0

    # ------------------------------------------------------------------
    # Combined report figure
    # ------------------------------------------------------------------
    def _create_report_figure(self):
        mpl, plt = _get_matplotlib()
        if plt is None:
            FreeCAD.Console.PrintWarning(
                "Matplotlib not available - plot skipped.\n"
            )
            return

        try:
            # Default save format -> PDF
            mpl.rcParams['savefig.format'] = 'pdf'

            import matplotlib.gridspec as gridspec
            from matplotlib.patches import FancyBboxPatch
            import datetime

            # ── Figure & GridSpec ────────────────────────────────────────
            fig = plt.figure(figsize=(11, 14))
            fig.canvas.manager.set_window_title(
                "GZ Stability Report  –  click Save (toolbar) to export as PDF"
            )
            fig.patch.set_facecolor('#f8f9fa')

            gs = gridspec.GridSpec(
                3, 1,
                figure=fig,
                height_ratios=[0.18, 0.28, 0.54],
                hspace=0.06,
                left=0.08, right=0.95,
                top=0.94, bottom=0.06
            )

            ax_header   = fig.add_subplot(gs[0])   # Load case summary
            ax_criteria = fig.add_subplot(gs[1])   # SOLAS criteria table
            ax_plot     = fig.add_subplot(gs[2])   # GZ chart

            for ax in (ax_header, ax_criteria):
                ax.axis('off')
                ax.set_xlim(0, 1)
                ax.set_ylim(0, 1)

            # ── Helper: draw a rounded box with section title ────────────
            def _section_box(ax, title):
                rect = FancyBboxPatch(
                    (0, 0), 1, 1,
                    boxstyle="round,pad=0.01",
                    linewidth=1.2, edgecolor='#adb5bd',
                    facecolor='white', transform=ax.transAxes,
                    zorder=0, clip_on=False
                )
                ax.add_patch(rect)
                ax.text(
                    0.012, 0.94, title,
                    transform=ax.transAxes,
                    fontsize=10, fontweight='bold', color='#343a40',
                    va='top'
                )

            # ── HEADER: report title + load case fields ──────────────────
            _section_box(ax_header, "GZ STABILITY ANALYSIS REPORT")

            date_str = datetime.datetime.now().strftime("%Y-%m-%d  %H:%M")

            lc_fields = [
                ("Date",             date_str),
                ("Vessel",           str(self.lc_info.get('vessel',     '-'))),
                ("Load case",        str(self.lc_info.get('load_case',  '-'))),
                ("Displacement",     f"{self.lc_info.get('displacement','-')} t"),
                ("VCG",              f"{self.lc_info.get('vcg',  '-')} m"),
                ("KG",               f"{self.lc_info.get('kg',   '-')} m"),
                ("Initial GM",       f"{self.GM0:.3f} m  [{self.gm_source}]"),
                ("Vanishing angle",  f"{self.vanishing_angle:.1f} deg"),
                ("Max GZ",           f"{self.max_gz:.3f} m  @  {self.max_gz_angle:.1f} deg"),
            ]

            # Two-column layout
            col_width = 0.50
            n_rows    = (len(lc_fields) + 1) // 2
            row_h     = 0.68 / max(n_rows, 1)
            fs        = 8.5

            for idx, (label, value) in enumerate(lc_fields):
                col   = idx % 2
                row   = idx // 2
                x_lbl = 0.015 + col * col_width
                x_val = 0.015 + col * col_width + 0.19
                y     = 0.82 - row * row_h * 1.28
                ax_header.text(x_lbl, y, label + ":",
                               fontsize=fs, color='#6c757d',
                               transform=ax_header.transAxes, va='top')
                ax_header.text(x_val, y, value,
                               fontsize=fs, fontweight='bold', color='#212529',
                               transform=ax_header.transAxes, va='top')

            # PASS / FAIL badge (top-right)
            all_pass   = self.passed_count == self.total_criteria
            badge_col  = '#28a745' if all_pass else '#dc3545'
            badge_text = (f"PASS  {self.passed_count}/{self.total_criteria}"
                          if all_pass else
                          f"FAIL  {self.passed_count}/{self.total_criteria}")
            ax_header.text(
                0.976, 0.94, badge_text,
                transform=ax_header.transAxes,
                fontsize=11, fontweight='bold', color='white',
                ha='right', va='top',
                bbox=dict(boxstyle='round,pad=0.40',
                          facecolor=badge_col, edgecolor='none')
            )

            # ── CRITERIA TABLE ───────────────────────────────────────────
            _section_box(ax_criteria, "IMO / SOLAS Intact Stability Criteria  (IS Code 2008)")

            col_labels = ["Criterion", "Required", "Calculated", "Status"]
            col_x      = [0.012, 0.56, 0.72, 0.875]
            header_y   = 0.875
            row_step   = 0.118

            # Column headers
            for lbl, cx in zip(col_labels, col_x):
                ax_criteria.text(
                    cx, header_y, lbl,
                    transform=ax_criteria.transAxes,
                    fontsize=8.5, fontweight='bold', color='#495057',
                    va='top'
                )
            # Separator line below header
            line_y = header_y - 0.058
            ax_criteria.plot(
                [0.008, 0.992], [line_y, line_y],
                transform=ax_criteria.transAxes,
                color='#ced4da', linewidth=0.8, clip_on=False
            )

            for r_idx, (crit_name, crit) in enumerate(self.criteria.items()):
                y_row  = header_y - 0.068 - r_idx * row_step
                bg_col = '#f4fff6' if crit['passed'] else '#fff4f4'
                st_col = '#28a745' if crit['passed'] else '#dc3545'
                st_txt = 'PASS'   if crit['passed'] else 'FAIL'

                # Alternating row background
                ax_criteria.fill_between(
                    [0.005, 0.995],
                    [y_row - row_step * 0.44] * 2,
                    [y_row + row_step * 0.44] * 2,
                    facecolor=bg_col, alpha=0.55,
                    transform=ax_criteria.transAxes,
                    zorder=1
                )

                row_cells = [
                    (col_x[0], crit_name,                '#212529', 8.2, 'normal'),
                    (col_x[1], f"{crit['required']:.3f}", '#495057', 8.2, 'normal'),
                    (col_x[2], f"{crit['value']:.4f}",   '#212529', 8.4, 'bold'  ),
                    (col_x[3], st_txt,                   st_col,    8.5, 'bold'  ),
                ]
                for cx, txt, fc, fs2, fw in row_cells:
                    ax_criteria.text(
                        cx, y_row, txt,
                        transform=ax_criteria.transAxes,
                        fontsize=fs2, fontweight=fw, color=fc,
                        va='center', zorder=2
                    )

            # ── GZ CHART ─────────────────────────────────────────────────
            COLOR_GZ   = '#1f77b4'
            COLOR_AREA = '#2ca02c'

            ax_plot.set_facecolor('#fdfdfd')

            x  = np.array(self.roll_deg)
            y1 = np.array(self.gz_m)
            y2 = np.array(self.cumulative_areas)
            mask = x >= 0
            x, y1, y2 = x[mask], y1[mask], y2[mask]

            if len(x) > 0:
                # Left axis: GZ curve + fill
                line1, = ax_plot.plot(
                    x, y1, color=COLOR_GZ, linewidth=2.2, label='GZ [m]'
                )
                ax_plot.fill_between(x, 0, y1, where=(y1 >= 0),
                                     alpha=0.09, color=COLOR_GZ)
                ax_plot.axhline(0, color='black', linewidth=0.7)
                ax_plot.axhline(
                    y=0.20, color=COLOR_GZ, linewidth=1.0,
                    linestyle=':', alpha=0.55,
                    label='Min GZ = 0.20 m'
                )

                # Right axis: cumulative area
                ax2    = ax_plot.twinx()
                line2, = ax2.plot(
                    x, y2, color=COLOR_AREA, linewidth=2.0,
                    linestyle='--', label='Cumulative area [m*rad]'
                )
                ax2.set_ylabel('Cumulative area [m*rad]',
                               color=COLOR_AREA, fontsize=10)
                ax2.tick_params(axis='y', labelcolor=COLOR_AREA)

                # Vertical SOLAS reference lines
                x_max = float(x[-1])
                vlines = [
                    (30.0,                 '#e377c2', '-',   'IMO limit 30 deg'),
                    (40.0,                 '#d62728', '--',  'IMO limit 40 deg'),
                    (self.max_gz_angle,    '#ff7f0e', ':',   f'Max GZ ({self.max_gz_angle:.1f} deg)'),
                    (self.vanishing_angle, '#9467bd', '-.',  f'Vanishing ({self.vanishing_angle:.1f} deg)'),
                ]
                vline_handles = []
                for angle, col, ls, lbl in vlines:
                    if 0 < angle <= x_max + 1:
                        h = ax_plot.axvline(
                            x=angle, color=col, linewidth=1.4,
                            linestyle=ls, alpha=0.85, label=lbl
                        )
                        vline_handles.append(h)

                # Unified legend
                all_lines = [line1, line2] + vline_handles
                ax_plot.legend(
                    handles=all_lines, loc='upper right',
                    fontsize=8.5, framealpha=0.92
                )

            ax_plot.set_xlabel('Heel angle [deg]', fontsize=10)
            ax_plot.set_ylabel('GZ [m]', color=COLOR_GZ, fontsize=10)
            ax_plot.tick_params(axis='y', labelcolor=COLOR_GZ)
            ax_plot.set_xlim(left=0)
            ax_plot.grid(True, linestyle=':', alpha=0.45)
            ax_plot.set_title('GZ Righting Lever Curve', fontsize=10,
                              color='#343a40', pad=6)

            # Figure super-title
            fig.suptitle("GZ Stability Analysis", fontsize=14,
                         fontweight='bold', color='#212529', y=0.975)

            plt.show(block=False)
            FreeCAD.Console.PrintMessage(
                "Report figure ready. Use toolbar Save button to export as PDF.\n"
            )

        except Exception as e:
            FreeCAD.Console.PrintError(f"Error in _create_report_figure: {e}\n")
            import traceback
            traceback.print_exc()

    # ------------------------------------------------------------------
    # Spreadsheet
    # ------------------------------------------------------------------
    def spreadSheet(self):
        doc = FreeCAD.ActiveDocument
        if doc is None:
            return
        sheet_obj = doc.getObject("GZ_Results")
        if sheet_obj is None:
            sheet_obj = doc.addObject("Spreadsheet::Sheet", "GZ_Results")
        self.sheet = sheet_obj
        self._fill_sheet()
        doc.recompute()

    def _fill_sheet(self):
        s  = self.sheet
        n  = len(self.roll_deg)
        hd = bool(self.disp_kg)

        headers = ['Roll [deg]', 'GZ [m]', 'Draft [m]', 'Trim [deg]',
                   'Cumulative area [m*rad]']
        if hd:
            headers.append('Displacement [t]')
        for ci, lbl in enumerate(headers):
            s.set(f"{chr(ord('A') + ci)}1", lbl)

        for i in range(n):
            row = i + 2
            s.set(f"A{row}", "{:.4f}".format(self.roll_deg[i]))
            s.set(f"B{row}", "{:.6f}".format(self.gz_m[i]))
            s.set(f"C{row}", "{:.4f}".format(
                self.draft_m[i] if i < len(self.draft_m) else 0.0))
            s.set(f"D{row}", "{:.4f}".format(
                self.trim_deg[i] if i < len(self.trim_deg) else 0.0))
            s.set(f"E{row}", "{:.6f}".format(
                self.cumulative_areas[i] if i < len(self.cumulative_areas) else 0.0))
            if hd and i < len(self.disp_kg):
                s.set(f"F{row}", "{:.2f}".format(self.disp_kg[i] / 1000))

        FreeCAD.Console.PrintMessage(
            f"Spreadsheet created with {n} rows.\n"
        )

    # ------------------------------------------------------------------
    # Console summary
    # ------------------------------------------------------------------
    def print_solas_results(self):
        sep = "-" * 62
        FreeCAD.Console.PrintMessage(f"\n{sep}\n")
        FreeCAD.Console.PrintMessage("  GZ STABILITY ANALYSIS - SOLAS / IS CODE CRITERIA\n")
        FreeCAD.Console.PrintMessage(f"{sep}\n")
        for name, crit in self.criteria.items():
            status = "PASS" if crit['passed'] else "FAIL"
            FreeCAD.Console.PrintMessage(
                f"  [{status}]  {name}\n"
                f"           Actual: {crit['value']:.4f}  |  "
                f"Required: {crit['required']:.3f}\n"
            )
        FreeCAD.Console.PrintMessage(f"{sep}\n")
        FreeCAD.Console.PrintMessage(
            f"  Result       : {self.passed_count}/{self.total_criteria} criteria passed\n"
            f"  Max GZ       : {self.max_gz:.3f} m  @  {self.max_gz_angle:.1f} deg\n"
            f"  Initial GM   : {self.GM0:.3f} m\n"
            f"  Vanishing    : {self.vanishing_angle:.1f} deg\n"
        )
        FreeCAD.Console.PrintMessage(f"{sep}\n\n")
