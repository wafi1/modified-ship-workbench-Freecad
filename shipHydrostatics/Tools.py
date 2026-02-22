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
import random
from FreeCAD import Vector, Rotation, Matrix, Placement
import Part
from FreeCAD import Units
import FreeCAD as App
try:
    import FreeCADGui as Gui
except ImportError:
    pass
from .. import Instance
from ..shipUtils import Math


DENS = Units.parseQuantity("1025 kg/m^3")  # Salt water
COMMON_BOOLEAN_ITERATIONS = 10


def placeShipShape(shape, draft, roll, trim):
    """Move the ship shape such that the free surface matches with the plane
    z=0. The transformation will be applied on the input shape, so copy it
    before calling this method if it should be preserved.

    Position arguments:
    shape -- Ship shape
    draft -- Ship draft
    roll -- Roll angle
    trim -- Trim angle

    Returned values:
    shape -- The same transformed input shape. Just for debugging purposes, you
    can discard it.
    base_z -- The new base z coordinate (after applying the roll angle). Useful
    if you want to revert back the transformation
    """
    shape.rotate(Vector(0.0, 0.0, 0.0), Vector(1.0, 0.0, 0.0), roll)
    base_z = shape.BoundBox.ZMin
    shape.translate(Vector(0.0, draft * math.sin(math.radians(roll)), -base_z))
    shape.rotate(Vector(0.0, 0.0, 0.0), Vector(0.0, -1.0, 0.0), trim)
    shape.translate(Vector(draft * math.sin(math.radians(trim)), 0.0, 0.0))
    shape.translate(Vector(0.0, 0.0, -draft))

    return shape, base_z


def getUnderwaterSide(shape, force=True):
    """Get the underwater shape, simply cropping the provided shape by the z=0
    free surface plane.

    Position arguments:
    shape -- Solid shape to be cropped

    Keyword arguments:
    force -- True if in case the common boolean operation fails, i.e. returns
    no solids, the tool should retry it slightly moving the free surface. False
    otherwise. (True by default)

    Returned value:
    Cropped shape. It is not modifying the input shape
    """
    Part.show(shape)
    orig = App.ActiveDocument.Objects[-1]
    try:
        guiObj = Gui.ActiveDocument.getObject(orig.Name)
        guiObj.ShowInTree = False
    except:
        pass

    bbox = shape.BoundBox
    xmin = Units.Quantity(bbox.XMin, Units.Length)
    xmax = Units.Quantity(bbox.XMax, Units.Length)
    ymin = Units.Quantity(bbox.YMin, Units.Length)
    ymax = Units.Quantity(bbox.YMax, Units.Length)
    zmin = Units.Quantity(bbox.ZMin, Units.Length)
    zmax = Units.Quantity(bbox.ZMax, Units.Length)

    L = xmax - xmin
    B = ymax - ymin
    H = zmax - zmin

    box = App.ActiveDocument.addObject("Part::Box","Box")
    box.Placement = Placement(Vector(xmin - L, ymin - B, zmin - H),
                              Rotation(App.Vector(0,0,1),0))
    box.Length = 3.0 * L
    box.Width = 3.0 * B
    box.Height = -zmin + H
    try:
        guiObj = Gui.ActiveDocument.getObject(box.Name)
        guiObj.ShowInTree = False
    except:
        pass

    App.ActiveDocument.recompute()
    common = App.activeDocument().addObject("Part::MultiCommon",
                                            "UnderwaterSideHelper")
    common.Shapes = [orig, box]
    try:
        guiObj = Gui.ActiveDocument.getObject(common.Name)
        guiObj.ShowInTree = False
    except:
        pass
    App.ActiveDocument.recompute()
    if force and len(common.Shape.Solids) == 0:
        msg = App.Qt.translate(
            "ship_console",
            "Boolean operation failed when trying to get the underwater side."
            " The tool is retrying such operation slightly moving the free"
            " surface position")
        App.Console.PrintWarning(msg + '\n')
        random_bounds = 0.01 * H.Value
        i = 0
        while len(common.Shape.Solids) == 0 and i < COMMON_BOOLEAN_ITERATIONS:
            i += 1
            dH = Units.Quantity(random.uniform(-random_bounds, random_bounds),
                                Units.Length)
            box.Height = -zmin + H + dH
            App.ActiveDocument.recompute()

    out = common.Shape
    App.ActiveDocument.removeObject(common.Name)
    App.ActiveDocument.removeObject(orig.Name)
    App.ActiveDocument.removeObject(box.Name)
    App.ActiveDocument.recompute()
    return out


def areas(ship, n, draft=None,
                   roll=Units.parseQuantity("0 deg"),
                   trim=Units.parseQuantity("0 deg")):
    """Compute the ship transversal areas

    Position arguments:
    ship -- Ship object (see createShip)
    n -- Number of points to compute

    Keyword arguments:
    draft -- Ship draft (Design ship draft by default)
    roll -- Roll angle (0 degrees by default)
    trim -- Trim angle (0 degrees by default)

    Returned value:
    List of sections, each section contains 2 values, the x longitudinal
    coordinate, and the transversal area. If n < 2, an empty list will be
    returned.
    """
    if n < 2:
        return []

    if draft is None:
        draft = ship.Draft

    shape, _ = placeShipShape(ship.Shape.copy(), draft, roll, trim)
    shape = getUnderwaterSide(shape)

    bbox = shape.BoundBox
    xmin = Units.Quantity(bbox.XMin, Units.Length)
    xmax = Units.Quantity(bbox.XMax, Units.Length)
    dx = (xmax - xmin) / (n - 1.0)

    areas = [(xmin, Units.Quantity(0.0, Units.Area))]
    App.Console.PrintMessage("Computing transversal areas...\n")
    App.Console.PrintMessage("Some Inventor representation errors can be"
                             " shown, please ignore them.\n")
    for i in range(1, n - 1):
        App.Console.PrintMessage("{0} / {1}\n".format(i, n - 2))
        x = xmin + i * dx
        try:
            f = Part.Face(shape.slice(Vector(1,0,0), x))
        except Part.OCCError:
            msg = App.Qt.translate(
                "ship_console",
                "Part.OCCError: Area computation failed (x={})").format(
                    x.UserString)
            App.Console.PrintError(msg + '\n')
            areas.append((Units.Quantity(x, Units.Length),
                          Units.Quantity(0.0, Units.Area)))
            continue
        areas.append((Units.Quantity(x, Units.Length),
                      Units.Quantity(f.Area, Units.Area)))
    areas.append((Units.Quantity(xmax, Units.Length),
                  Units.Quantity(0.0, Units.Area)))
    App.Console.PrintMessage("Done!\n")
    return areas


def displacement(ship, draft=None,
                       roll=Units.parseQuantity("0 deg"),
                       trim=Units.parseQuantity("0 deg"),
                       precomputed_shape=None,
                       precomputed_base_z=None):
    """Compute the ship displacement

    Position arguments:
    ship -- Ship object (see createShip)

    Keyword arguments:
    draft -- Ship draft (Design ship draft by default)
    roll -- Roll angle (0 degrees by default)
    trim -- Trim angle (0 degrees by default)
    precomputed_shape -- Already placed and cropped underwater shape (optional).
                         If provided, placeShipShape + getUnderwaterSide are
                         skipped, saving a costly Boolean operation.
    precomputed_base_z -- base_z value from placeShipShape (required when
                          precomputed_shape is provided)

    Returned values:
    disp -- The ship displacement (a density of the water of 1025 kg/m^3 is
    assumed)
    B -- Bouyance application point, i.e. Center of mass of the underwater side
    Cb -- Block coefficient

    The Bouyance center is referred to the original ship position.
    """
    if draft is None:
        draft = ship.Draft

    if precomputed_shape is not None:
        # --- OPTIMIZED PATH: reuse already computed shape ---
        shape = precomputed_shape
        base_z = precomputed_base_z if precomputed_base_z is not None else 0.0
    else:
        shape, base_z = placeShipShape(ship.Shape.copy(), draft, roll, trim)
        shape = getUnderwaterSide(shape)

    vol = 0.0
    cog = Vector()
    if len(shape.Solids) > 0:
        for solid in shape.Solids:
            vol += solid.Volume
            sCoG = solid.CenterOfMass
            cog.x = cog.x + sCoG.x * solid.Volume
            cog.y = cog.y + sCoG.y * solid.Volume
            cog.z = cog.z + sCoG.z * solid.Volume
        cog.x = cog.x / vol
        cog.y = cog.y / vol
        cog.z = cog.z / vol

    bbox = shape.BoundBox
    Vol = (bbox.XMax - bbox.XMin) * (bbox.YMax - bbox.YMin) * abs(bbox.ZMin)

    B = Part.Point(Vector(cog.x, cog.y, cog.z))
    m = Matrix()
    m.move(Vector(0.0, 0.0, draft))
    m.move(Vector(-draft * math.sin(trim.getValueAs("rad")), 0.0, 0.0))
    m.rotateY(trim.getValueAs("rad"))
    m.move(Vector(0.0,
                  -draft * math.sin(roll.getValueAs("rad")),
                  base_z))
    m.rotateX(-roll.getValueAs("rad"))
    B.transform(m)

    try:
        cb = vol / Vol
    except ZeroDivisionError:
        msg = App.Qt.translate(
            "ship_console",
            "ZeroDivisionError: Null volume found during the displacement"
            " computation!")
        App.Console.PrintError(msg + '\n')
        cb = 0.0

    return (DENS * Units.Quantity(vol, Units.Volume),
            Vector(B.X, B.Y, B.Z),
            cb)


def wettedArea(shape, draft, roll=Units.parseQuantity("0 deg"),
                             trim=Units.parseQuantity("0 deg")):
    """Compute the ship wetted area

    Position arguments:
    shape -- External faces of the ship hull
    draft -- Ship draft

    Keyword arguments:
    roll -- Roll angle (0 degrees by default)
    trim -- Trim angle (0 degrees by default)

    Returned value:
    The wetted area, i.e. The underwater surface area
    """
    shape, _ = placeShipShape(shape.copy(), draft, roll, trim)
    shape = getUnderwaterSide(shape, force=False)
    submerged_length = shape.BoundBox.ZLength

    area = 0.0
    for f in shape.Faces:
        if f.BoundBox.ZLength < 0.01 * submerged_length and \
           abs(f.BoundBox.ZMin) < 0.01 * submerged_length:
            continue
        area = area + f.Area
    return Units.Quantity(area, Units.Area)


def floatingArea(ship, draft=None,
                       roll=Units.parseQuantity("0 deg"),
                       trim=Units.parseQuantity("0 deg"),
                       precomputed_placed_shape=None):
    """Compute the ship floating area

    Position arguments:
    ship -- Ship object (see createShip)

    Keyword arguments:
    draft -- Ship draft (Design ship draft by default)
    roll -- Roll angle (0 degrees by default)
    trim -- Trim angle (0 degrees by default)
    precomputed_placed_shape -- Already placed (but NOT cropped) ship shape.
                                If provided, placeShipShape is skipped.

    Returned values:
    area -- Ship floating area
    cf -- Floating area coefficient
    """
    if draft is None:
        draft = ship.Draft

    if precomputed_placed_shape is not None:
        shape = precomputed_placed_shape
    else:
        shape, _ = placeShipShape(ship.Shape.copy(), draft, roll, trim)

    try:
        f = Part.Face(shape.slice(Vector(0,0,1), 0.0))
        area = Units.Quantity(f.Area, Units.Area)
    except Part.OCCError:
        msg = App.Qt.translate(
            "ship_console",
            "Part.OCCError: Floating area cannot be computed")
        App.Console.PrintError(msg + '\n')
        f = None
        area = Units.Quantity(0.0, Units.Area)

    bbox = shape.BoundBox
    Area = Units.Quantity(
        (bbox.XMax - bbox.XMin) * (bbox.YMax - bbox.YMin), Units.Area)
    try:
        cf = (area / Area).Value
    except ZeroDivisionError:
        msg = App.Qt.translate(
            "ship_console",
            "ZeroDivisionError: Null area found during the floating area"
            " computation!")
        App.Console.PrintError(msg + '\n')
        cf = 0.0

    return area, cf, f


def BML(ship, fs, draft=None,
                  roll=Units.parseQuantity("0 deg"),
                  trim=Units.parseQuantity("0 deg"),
                  precomputed_disp=None):
    """Compute the moment required to trim the ship 1cm

    Position arguments:
    ship -- Ship object (see createShip)
    fs -- The shape of the free surface

    Keyword arguments:
    draft -- Ship draft (Design ship draft by default)
    roll -- Roll angle (0 degrees by default)
    trim -- Trim angle (0 degrees by default)
    precomputed_disp -- Pre-computed (disp, B, cb) tuple to avoid redundant
                        displacement calculation.

    Returned value:
    BML radius and the displacement
    """
    if precomputed_disp is not None:
        disp = precomputed_disp[0]
    else:
        disp, _, _ = displacement(ship, draft, roll, trim)
    vol = disp / DENS
    inertia_unit = (Units.Quantity(1, Units.Length)**4).Unit
    return Units.Quantity(fs.MatrixOfInertia.A22, inertia_unit) / vol, disp


def TMC(ship, fs, draft=None,
                  roll=Units.parseQuantity("0 deg"),
                  trim=Units.parseQuantity("0 deg"),
                  precomputed_disp=None):
    """Compute the moment required to trim the ship 1cm

    Position arguments:
    ship -- Ship object (see createShip)
    fs -- The shape of the free surface. If None is passed, the BML will be
          computed heuristically.

    Keyword arguments:
    draft -- Ship draft (Design ship draft by default)
    roll -- Roll angle (0 degrees by default)
    trim -- Trim angle (0 degrees by default)
    precomputed_disp -- Pre-computed (disp, B, cb) tuple (optional).

    Returned value:
    Moment required to trim the ship 1cm.
    """
    if draft is None:
        draft = ship.Draft

    if fs is not None:
        bml, disp = BML(ship, fs, draft=draft, roll=roll, trim=trim,
                        precomputed_disp=precomputed_disp)
        return disp * bml / ship.Length.getValueAs('cm').Value

    if precomputed_disp is not None:
        disp_orig, B_orig, _ = precomputed_disp
    else:
        disp_orig, B_orig, _ = displacement(ship, draft, roll, trim)

    factor = 10.0
    x = 0.5 * ship.Length.getValueAs('cm').Value
    y = 1.0
    angle = math.atan2(y, x) * Units.Radian
    trim_new = trim + factor * angle
    disp_new, B_new, _ = displacement(ship, draft, roll, trim_new)

    mom0 = disp_orig * Units.Quantity(B_orig.x, Units.Length)
    mom1 = disp_new * Units.Quantity(B_new.x, Units.Length)
    return (mom1 - mom0) / factor


def BMT(ship, fs, draft=None,
                  trim=Units.parseQuantity("0 deg"),
                  precomputed_disp=None):
    """Calculate "ship Bouyance center" - "transversal metacenter" radius

    Position arguments:
    ship -- Ship object (see createShip)
    fs -- The shape of the free surface. If None is passed, the BMT will be
          computed heuristically.

    Keyword arguments:
    draft -- Ship draft (Design ship draft by default)
    trim -- Trim angle (0 degrees by default)
    precomputed_disp -- Pre-computed (disp, B, cb) tuple (optional).

    Returned value:
    BMT radius
    """
    if draft is None:
        draft = ship.Draft

    roll = Units.parseQuantity("0 deg")

    if precomputed_disp is not None:
        disp, B0, _ = precomputed_disp
    else:
        disp, B0, _ = displacement(ship, draft, roll=roll, trim=trim)

    if fs is not None:
        vol = disp / DENS
        inertia_unit = (Units.Quantity(1, Units.Length)**4).Unit
        return Units.Quantity(fs.MatrixOfInertia.A11, inertia_unit) / vol

    nRoll = 2
    maxRoll = Units.parseQuantity("7 deg")

    BM = 0.0
    for i in range(nRoll):
        roll = (maxRoll / nRoll) * (i + 1)
        _, B1, _ = displacement(ship, draft, roll, trim)
        BB = B1 - B0
        BB.x = 0.0
        BM += 0.5 * BB.Length / math.sin(math.radians(0.5 * roll)) / nRoll
    return Units.Quantity(BM, Units.Length)


def mainFrameCoeff(ship, draft=None,
                         precomputed_underwater=None):
    """Compute the main frame coefficient

    Position arguments:
    ship -- Ship object (see createShip)

    Keyword arguments:
    draft -- Ship draft (Design ship draft by default)
    precomputed_underwater -- Already placed + cropped underwater shape.
                              If provided, the Boolean operation is skipped.

    Returned value:
    Ship main frame area coefficient
    """
    if draft is None:
        draft = ship.Draft

    if precomputed_underwater is not None:
        shape = precomputed_underwater
    else:
        shape, _ = placeShipShape(ship.Shape.copy(), draft,
                                  Units.parseQuantity("0 deg"),
                                  Units.parseQuantity("0 deg"))
        shape = getUnderwaterSide(shape)

    try:
        f = Part.Face(shape.slice(Vector(1,0,0), 0.0))
        area = f.Area
    except Part.OCCError:
        msg = App.Qt.translate(
            "ship_console",
            "Part.OCCError: Main frame area cannot be computed")
        App.Console.PrintError(msg + '\n')
        area = 0.0

    bbox = shape.BoundBox
    Area = (bbox.YMax - bbox.YMin) * (bbox.ZMax - bbox.ZMin)

    try:
        cm = area / Area
    except ZeroDivisionError:
        msg = App.Qt.translate(
            "ship_console",
            "ZeroDivisionError: Null area found during the main frame area"
            " coefficient computation!")
        App.Console.PrintError(msg + '\n')
        cm = 0.0

    return cm


class Point:
    """Hydrostatics point, that contains the following members:

    draft -- Ship draft
    trim -- Ship trim
    disp -- Ship displacement
    xcb -- Bouyance center X coordinate
    wet -- Wetted ship area
    mom -- Trimming 1cm ship moment
    farea -- Floating area
    KBt -- Transversal KB height
    BMt -- Transversal BM height
    Cb -- Block coefficient.
    Cf -- Floating coefficient.
    Cm -- Main frame coefficient.

    The moment to trim the ship 1 cm is positive when is resulting in a positive
    trim angle.
    """
    def __init__(self, ship, faces, draft, trim):
        """Compute all the hydrostatics.

        OPTIMIZED: The ship shape is placed and the Boolean underwater
        intersection is performed only ONCE per Point. All sub-functions
        receive the pre-computed shapes to avoid redundant operations.

        Position argument:
        ship -- Ship instance
        faces -- Ship external faces
        draft -- Ship draft
        trim -- Trim angle
        """
        roll = Units.parseQuantity("0 deg")

        # ------------------------------------------------------------------ #
        # ONE-TIME: place shape and compute underwater intersection           #
        # Previously this was done 4-5 times per Point (once in each of      #
        # displacement / wettedArea / floatingArea / mainFrameCoeff / TMC).  #
        # ------------------------------------------------------------------ #
        placed_shape, base_z = placeShipShape(
            ship.Shape.copy(), draft, roll, trim)
        # Keep a separate copy for floatingArea (must NOT be cropped)
        placed_shape_for_fs = placed_shape.copy()

        underwater_shape = getUnderwaterSide(placed_shape)

        # Displacement (uses cached underwater shape)
        disp, B, cb = displacement(
            ship, draft=draft, roll=roll, trim=trim,
            precomputed_shape=underwater_shape,
            precomputed_base_z=base_z)

        precomputed_disp = (disp, B, cb)

        # Wetted area (needs its own crop because wettedArea works on faces)
        if not faces:
            wet = Units.Quantity(0.0, Units.Area)
        else:
            wet = wettedArea(faces, draft=draft, trim=trim)

        # Floating area (uses the placed-but-not-cropped copy)
        farea, cf, fshape = floatingArea(
            ship, draft=draft, trim=trim,
            precomputed_placed_shape=placed_shape_for_fs)

        # TMC: BML path uses fs + pre-computed displacement → no extra Boolean
        mom = TMC(ship, fshape, draft=draft, trim=trim,
                  precomputed_disp=precomputed_disp)

        # BMT: uses fs + pre-computed displacement → no extra Boolean
        bm = BMT(ship, fshape, draft=draft, trim=trim,
                 precomputed_disp=precomputed_disp)

        # Main frame coefficient (uses cached underwater shape)
        cm = mainFrameCoeff(ship, draft=draft,
                            precomputed_underwater=underwater_shape)

        # Store final data
        self.draft = draft
        self.trim = trim
        self.disp = disp
        self.xcb = Units.Quantity(B.x, Units.Length)
        self.wet = wet
        self.farea = farea
        self.mom = mom
        self.KBt = Units.Quantity(B.z, Units.Length)
        self.BMt = bm
        self.Cb = cb
        self.Cf = cf
        self.Cm = cm
