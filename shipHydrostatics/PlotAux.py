#***************************************************************************
#*                                                                         *
#*   Copyright (c) 2011, 2016 Jose Luis Cercos Pita <jlcercos@gmail.com>   *
#*                                                                         *
#*   This program is free software; you can redistribute it and/or modify  *
#*   it under the terms of the GNU Lesser General Public License (LGPL)    *
#*   as published by the Free Software Foundation; either version 2 of     *
#*   the License, or (at your option) any later version.                   *
#*                                                                         *
#***************************************************************************
#
# Fixes vs. original:
#
#   FIX 1 - update() copy-paste bug
#     self.warea.line.set_data(draft, disp) used *draft* on the x-axis
#     instead of *warea*.  That made the wetted-area curve identical to
#     the draft curve.  All series in update() verified and corrected.
#
#   FIX 2 - spreadSheet() duplicate sheets
#     addObject() was called unconditionally, creating a new "Hydrostatics"
#     sheet on every run.  Now checks whether the sheet already exists.
#
#   FIX 3 - unused "import Spreadsheet" removed
#
#   FIX 4 - Plot.addNewAxes() / Plot.axesList() guarded
#     These methods can be absent in some FreeCAD builds.  Wrapped in
#     try/except so the code degrades gracefully.

import os
import sys
import math
import FreeCAD
from ..shipUtils import Paths


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def autolim(ax):
    """Auto-scale an axes object to the data extent of all its lines."""
    xmin, xmax = sys.float_info.max, -sys.float_info.max
    ymin, ymax = sys.float_info.max, -sys.float_info.max
    lines = ax.get_lines()
    if not lines:
        return
    for l in lines:
        xd, yd = l.get_xdata(), l.get_ydata()
        if len(xd) == 0 or len(yd) == 0:
            continue
        xmin = min(xmin, min(xd));  xmax = max(xmax, max(xd))
        ymin = min(ymin, min(yd));  ymax = max(ymax, max(yd))
    if xmin >= xmax or ymin >= ymax:
        return
    try:
        ax.set_xlim(xmin, xmax)
    except TypeError:
        pass
    try:
        ax.set_ylim(ymin, ymax)
    except TypeError:
        pass


def _get_plot():
    """Return the FreeCAD Plot module or raise ImportError."""
    for mod_path in ('FreeCAD.Plot.Plot', 'freecad.plot'):
        try:
            import importlib
            return importlib.import_module(mod_path)
        except ImportError:
            pass
    try:
        from FreeCAD import Plot
        return Plot
    except ImportError:
        pass
    raise ImportError("No FreeCAD Plot module available")


def _extract(points):
    """Return plain-float lists for all hydrostatic quantities."""
    disp  = [p.disp.getValueAs("kg").Value  / 1000.0 for p in points]
    draft = [p.draft.getValueAs("m").Value           for p in points]
    warea = [p.wet.getValueAs("m^2").Value           for p in points]
    t1cm  = [p.mom.getValueAs("kg*m").Value / 1000.0 for p in points]
    xcb   = [p.xcb.getValueAs("m").Value             for p in points]
    farea = [p.farea.getValueAs("m^2").Value         for p in points]
    kbt   = [p.KBt.getValueAs("m").Value             for p in points]
    bmt   = [p.BMt.getValueAs("m").Value             for p in points]
    cb    = [p.Cb                                    for p in points]
    cf    = [p.Cf                                    for p in points]
    cm    = [p.Cm                                    for p in points]
    return disp, draft, warea, t1cm, xcb, farea, kbt, bmt, cb, cf, cm


# ---------------------------------------------------------------------------
# Plot class
# ---------------------------------------------------------------------------

class Plot(object):
    def __init__(self, ship, points):
        self.points = points[:]
        self.plt1 = self.plt2 = self.plt3 = None
        self.sheet = None

        # Line references kept for update() -- use distinct names to avoid
        # shadowing the built-in "warea" variable in subclasses.
        self.draft1   = self.warea_s  = self.t1cm_s = self.xcb_s  = None
        self.draft2   = self.farea_s  = self.kbt_s  = self.bmt_s  = None
        self.draft3   = self.cb_s     = self.cf_s   = self.cm_s   = None

        self.plotVolume()
        self.plotStability()
        self.plotCoeffs()
        self.spreadSheet(ship)

    # ------------------------------------------------------------------
    # update
    # ------------------------------------------------------------------

    def update(self, ship, points):
        """Refresh existing figures and spreadsheet -- no new windows."""
        self.points = points[:]
        self.fillSpreadSheet(ship)

        if self.plt1 is None:
            return

        disp, draft, warea, t1cm, xcb, farea, kbt, bmt, cb, cf, cm = \
            _extract(self.points)

        # FIX 1: each series now uses its OWN x-data array.
        # The original had self.warea.line.set_data(draft, disp) -- wrong!

        for series, xd, yd in [
                (self.draft1,  draft, disp),
                (self.warea_s, warea, disp),   # was (draft, disp) -- BUG fixed
                (self.t1cm_s,  t1cm,  disp),
                (self.xcb_s,   xcb,   disp),
        ]:
            if series is not None:
                series.line.set_data(xd, yd)
        if self.plt1 is not None:
            try:
                for ax in self.plt1.axesList:
                    autolim(ax)
                self.plt1.update()
            except Exception:
                pass

        for series, xd, yd in [
                (self.draft2,  draft, disp),
                (self.farea_s, farea, disp),
                (self.kbt_s,   kbt,   disp),
                (self.bmt_s,   bmt,   disp),
        ]:
            if series is not None:
                series.line.set_data(xd, yd)
        if self.plt2 is not None:
            try:
                for ax in self.plt2.axesList:
                    autolim(ax)
                self.plt2.update()
            except Exception:
                pass

        for series, xd, yd in [
                (self.draft3, draft, disp),
                (self.cb_s,   cb,   disp),
                (self.cf_s,   cf,   disp),
                (self.cm_s,   cm,   disp),
        ]:
            if series is not None:
                series.line.set_data(xd, yd)
        if self.plt3 is not None:
            try:
                for ax in self.plt3.axesList:
                    autolim(ax)
                self.plt3.update()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------

    def _setup_figure(self, PlotMod, title, n_extra=3):
        """Create a figure and optional extra axes (FIX 4: guarded)."""
        plt = PlotMod.figure(title)
        try:
            PlotMod.grid(True)
            for i in range(n_extra):
                ax = PlotMod.addNewAxes()
                ax.yaxis.tick_right()
                ax.spines['right'].set_color((0.0, 0.0, 0.0))
                ax.spines['left'].set_color('none')
                ax.yaxis.set_ticks_position('right')
                ax.yaxis.set_label_position('right')
                for loc, spine in ax.spines.items():
                    if loc in ['bottom', 'top']:
                        spine.set_position(('outward', (i + 1) * 35))
                PlotMod.grid(True)
        except Exception as e:
            FreeCAD.Console.PrintWarning(
                "Could not add extra axes to '{}': {}\n".format(title, e))
        try:
            axes = PlotMod.axesList()
            for ax in axes:
                ax.set_position([0.1, 0.35, 0.8, 0.65])
        except Exception:
            axes = []
        return plt, axes

    def _sw(self, plt, axes, idx):
        if idx < len(axes):
            plt.axes = axes[idx]

    def _series(self, PlotMod, xd, yd, label, color,
                lw=2.0, ls='-', xlabel='', ylabel=''):
        s = PlotMod.plot(xd, yd, label)
        s.line.set_linestyle(ls)
        s.line.set_linewidth(lw)
        s.line.set_color(color)
        if xlabel:
            try:
                PlotMod.xlabel(xlabel)
                ax = PlotMod.axesList()[-1] if hasattr(PlotMod, 'axesList') else None
                if ax:
                    ax.xaxis.label.set_fontsize(15)
            except Exception:
                pass
        if ylabel:
            try:
                PlotMod.ylabel(ylabel)
                ax = PlotMod.axesList()[-1] if hasattr(PlotMod, 'axesList') else None
                if ax:
                    ax.yaxis.label.set_fontsize(15)
            except Exception:
                pass
        return s

    # ------------------------------------------------------------------
    # plotVolume
    # ------------------------------------------------------------------

    def plotVolume(self):
        try:
            PlotMod = _get_plot()
        except ImportError:
            FreeCAD.Console.PrintWarning(
                "Plot module unavailable -- skipping Volume plot\n")
            return True

        disp, draft, warea, t1cm, xcb, *_ = _extract(self.points)
        plt, axes = self._setup_figure(PlotMod, 'Volume')
        self.plt1 = plt

        self._sw(plt, axes, 0)
        self.draft1  = self._series(
            PlotMod, draft, disp, r'$T$', (0.0, 0.0, 0.0),
            xlabel=r'$T \; \left[ \mathrm{m} \right]$',
            ylabel=r'$\bigtriangleup \; \left[ \mathrm{tons} \right]$')

        self._sw(plt, axes, 1)
        self.warea_s = self._series(
            PlotMod, warea, disp, r'Wetted area', (1.0, 0.0, 0.0),
            xlabel=r'$Wetted \; area \; \left[ \mathrm{m}^2 \right]$',
            ylabel=r'$\bigtriangleup \; \left[ \mathrm{tons} \right]$')

        self._sw(plt, axes, 2)
        self.t1cm_s  = self._series(
            PlotMod, t1cm, disp, r'Moment to trim 1cm', (0.0, 0.0, 1.0),
            xlabel=(r'$Moment \; to \; trim \; 1\mathrm{cm} \; '
                    r'\left[ \mathrm{tons} \times \mathrm{m} \right]$'))

        self._sw(plt, axes, 3)
        self.xcb_s   = self._series(
            PlotMod, xcb, disp, r'$XCB$', (0.2, 0.8, 0.2),
            xlabel=r'$XCB \; \left[ \mathrm{m} \right]$')

        try:
            PlotMod.legend(True)
            plt.update()
        except Exception:
            pass
        return False

    # ------------------------------------------------------------------
    # plotStability
    # ------------------------------------------------------------------

    def plotStability(self):
        try:
            PlotMod = _get_plot()
        except ImportError:
            FreeCAD.Console.PrintWarning(
                "Plot module unavailable -- skipping Stability plot\n")
            return True

        disp, draft, _wa, _t1, _xcb, farea, kbt, bmt, *_ = _extract(self.points)
        plt, axes = self._setup_figure(PlotMod, 'Stability')
        self.plt2 = plt

        self._sw(plt, axes, 0)
        self.draft2  = self._series(
            PlotMod, draft, disp, r'$T$', (0.0, 0.0, 0.0),
            xlabel=r'$T \; \left[ \mathrm{m} \right]$',
            ylabel=r'$\bigtriangleup \; \left[ \mathrm{tons} \right]$')

        self._sw(plt, axes, 1)
        self.farea_s = self._series(
            PlotMod, farea, disp, r'Floating area', (1.0, 0.0, 0.0),
            xlabel=r'$Floating \; area \; \left[ \mathrm{m}^2 \right]$',
            ylabel=r'$\bigtriangleup \; \left[ \mathrm{tons} \right]$')

        self._sw(plt, axes, 2)
        self.kbt_s   = self._series(
            PlotMod, kbt, disp, r'$KB_T$', (0.0, 0.0, 1.0),
            xlabel=r'$KB_T \; \left[ \mathrm{m} \right]$')

        self._sw(plt, axes, 3)
        self.bmt_s   = self._series(
            PlotMod, bmt, disp, r'$BM_T$', (0.2, 0.8, 0.2),
            xlabel=r'$BM_T \; \left[ \mathrm{m} \right]$')

        try:
            PlotMod.legend(True)
            plt.update()
        except Exception:
            pass
        return False

    # ------------------------------------------------------------------
    # plotCoeffs
    # ------------------------------------------------------------------

    def plotCoeffs(self):
        try:
            PlotMod = _get_plot()
        except ImportError:
            FreeCAD.Console.PrintWarning(
                "Plot module unavailable -- skipping Coefficients plot\n")
            return True

        disp, draft, *_, cb, cf, cm = _extract(self.points)
        plt, axes = self._setup_figure(PlotMod, 'Coefficients')
        self.plt3 = plt

        self._sw(plt, axes, 0)
        self.draft3 = self._series(
            PlotMod, draft, disp, r'$T$', (0.0, 0.0, 0.0),
            xlabel=r'$T \; \left[ \mathrm{m} \right]$',
            ylabel=r'$\bigtriangleup \; \left[ \mathrm{tons} \right]$')

        self._sw(plt, axes, 1)
        self.cb_s   = self._series(
            PlotMod, cb, disp, r'$Cb$', (1.0, 0.0, 0.0),
            xlabel=r'$Cb$ (Block coefficient)',
            ylabel=r'$\bigtriangleup \; \left[ \mathrm{tons} \right]$')

        self._sw(plt, axes, 2)
        self.cf_s   = self._series(
            PlotMod, cf, disp, r'$Cf$', (0.0, 0.0, 1.0),
            xlabel=r'$Cf$ (Floating area coefficient)')

        self._sw(plt, axes, 3)
        self.cm_s   = self._series(
            PlotMod, cm, disp, r'$Cm$', (0.2, 0.8, 0.2),
            xlabel=r'$Cm$ (Main section coefficient)')

        try:
            PlotMod.legend(True)
            plt.update()
        except Exception:
            pass
        return False

    # ------------------------------------------------------------------
    # Spreadsheet
    # ------------------------------------------------------------------

    def spreadSheet(self, ship):
        """Create or reuse the Hydrostatics spreadsheet (FIX 2)."""
        doc = FreeCAD.activeDocument()
        sheet_obj = doc.getObject("Hydrostatics")
        if sheet_obj is None:
            sheet_obj = doc.addObject('Spreadsheet::Sheet', 'Hydrostatics')
            FreeCAD.Console.PrintMessage("Created spreadsheet 'Hydrostatics'\n")
        else:
            FreeCAD.Console.PrintMessage("Reusing spreadsheet 'Hydrostatics'\n")
        self.sheet = sheet_obj
        self.fillSpreadSheet(ship)

    def fillSpreadSheet(self, ship):
        if self.sheet is None:
            return
        s = self.sheet

        for cell, label in [
            ("A1", "displacement [ton]"),
            ("B1", "draft [m]"),
            ("C1", "wetted surface [m^2]"),
            ("D1", "1cm trimming ship moment [ton*m]"),
            ("E1", "Floating area [m^2]"),
            ("F1", "KBl [m]"),
            ("G1", "KBt [m]"),
            ("H1", "BMt [m]"),
            ("I1", "Cb"),
            ("J1", "Cf"),
            ("K1", "Cm"),
        ]:
            s.set(cell, label)

        for i, point in enumerate(self.points):
            row = i + 2
            s.set("A{}".format(row),
                  str(point.disp.getValueAs("kg").Value  / 1000.0))
            s.set("B{}".format(row),
                  str(point.draft.getValueAs("m").Value))
            s.set("C{}".format(row),
                  str(point.wet.getValueAs("m^2").Value))
            s.set("D{}".format(row),
                  str(point.mom.getValueAs("kg*m").Value / 1000.0))
            s.set("E{}".format(row),
                  str(point.farea.getValueAs("m^2").Value))
            s.set("F{}".format(row),
                  str(point.xcb.getValueAs("m").Value))
            s.set("G{}".format(row),
                  str(point.KBt.getValueAs("m").Value))
            s.set("H{}".format(row),
                  str(point.BMt.getValueAs("m").Value))
            s.set("I{}".format(row), str(point.Cb))
            s.set("J{}".format(row), str(point.Cf))
            s.set("K{}".format(row), str(point.Cm))

        FreeCAD.activeDocument().recompute()
