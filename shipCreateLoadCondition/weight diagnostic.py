#!/usr/bin/env python3
"""
SHIP WEIGHT DIAGNOSTIC
Paste the entire contents of this file into the FreeCAD Python console.
It will print a full picture of what FreeCAD actually sees.
"""

import FreeCAD as App

doc = App.ActiveDocument
if not doc:
    print("ERROR: No active document!")
else:

    # ================================================================
    # 1. FIND THE SHIP OBJECT
    # ================================================================
    print("\n" + "="*70)
    print("1. ALL OBJECTS IN DOCUMENT")
    print("="*70)
    for obj in doc.Objects:
        print(f"  {obj.Name:25s}  TypeId={obj.TypeId:35s}  Label={obj.Label}")

    # ================================================================
    # 2. FIND THE SHIP
    # ================================================================
    ship = None
    for obj in doc.Objects:
        if obj.Label == "Ship" or obj.Name == "Ship":
            ship = obj
            break
    if not ship:
        for obj in doc.Objects:
            if "ship" in obj.Label.lower():
                ship = obj
                break

    print("\n" + "="*70)
    print("2. SHIP OBJECT")
    print("="*70)
    if not ship:
        print("  ✗  No Ship object found!")
    else:
        print(f"  Name  : {ship.Name}")
        print(f"  Label : {ship.Label}")
        print(f"  TypeId: {ship.TypeId}")

    # ================================================================
    # 3. ALL PROPERTIES OF THE SHIP
    # ================================================================
    if ship:
        print("\n" + "="*70)
        print("3. ALL SHIP PROPERTIES")
        print("="*70)
        for prop in ship.PropertiesList:
            try:
                val = getattr(ship, prop)
                # Shorten long values
                sval = str(val)
                if len(sval) > 80:
                    sval = sval[:80] + "…"
                prop_type = ship.getTypeIdOfProperty(prop)
                print(f"  {prop:30s}  [{prop_type:35s}]  = {sval}")
            except Exception as e:
                print(f"  {prop:30s}  ERROR: {e}")

    # ================================================================
    # 4. WEIGHTS PROPERTY — DEEP INSPECTION
    # ================================================================
    print("\n" + "="*70)
    print("4. ship.Weights — DEEP INSPECTION")
    print("="*70)
    if not ship:
        print("  No ship found")
    elif not hasattr(ship, 'Weights'):
        print("  ✗  ship.Weights property does NOT EXIST")
    else:
        weights_raw = ship.Weights
        try:
            prop_type = ship.getTypeIdOfProperty('Weights')
        except:
            prop_type = type(weights_raw).__name__
        print(f"  Property type : {prop_type}")
        print(f"  Python type   : {type(weights_raw)}")
        print(f"  Length        : {len(weights_raw)}")
        print()
        for i, ref in enumerate(weights_raw):
            print(f"  [{i}] raw value  : {repr(ref)}")
            print(f"       python type: {type(ref)}")
            # Try resolving
            if isinstance(ref, str):
                obj = doc.getObject(ref)
                print(f"       getObject  : {obj} ({'✓ '+obj.Label if obj else '✗ NOT FOUND'})")
            elif hasattr(ref, 'Name'):
                print(f"       .Name      : {ref.Name}")
                print(f"       .Label     : {ref.Label}")
                print(f"       Has Mass   : {hasattr(ref, 'Mass')} " +
                      (f"= {ref.Mass:.1f} kg" if hasattr(ref, 'Mass') else ""))
                print(f"       Has COG    : {hasattr(ref, 'COG')} " +
                      (f"= {ref.COG}" if hasattr(ref, 'COG') else ""))
            else:
                print(f"       ??? Unknown ref type: {type(ref)}")
            print()

    # ================================================================
    # 5. ALL OBJECTS WITH A "Mass" PROPERTY
    # ================================================================
    print("="*70)
    print("5. ALL OBJECTS WITH A 'Mass' PROPERTY")
    print("="*70)
    mass_objects = []
    for obj in doc.Objects:
        if hasattr(obj, 'Mass'):
            mass_objects.append(obj)
            in_weights = False
            if ship and hasattr(ship, 'Weights'):
                for ref in ship.Weights:
                    ref_name = ref if isinstance(ref, str) else getattr(ref, 'Name', None)
                    if ref_name == obj.Name or ref is obj:
                        in_weights = True
                        break
            status = "✓ IN ship.Weights" if in_weights else "✗ NOT in ship.Weights"
            print(f"  {obj.Name:25s}  Label={obj.Label:30s}  "
                  f"Mass={obj.Mass:10.1f} kg  {status}")

    if not mass_objects:
        print("  (no objects with Mass property found)")

    # ================================================================
    # 6. LOAD CONDITION SPREADSHEETS
    # ================================================================
    print("\n" + "="*70)
    print("6. LOAD CONDITION SPREADSHEET(S)")
    print("="*70)
    lc_sheets = [o for o in doc.Objects if o.TypeId == 'Spreadsheet::Sheet']
    if not lc_sheets:
        print("  (no spreadsheets found)")
    else:
        for lc in lc_sheets:
            print(f"\n  Sheet: {lc.Name}  Label={lc.Label}")
            # Check key result cells
            for cell in ['D4','E5','F5','G5','H4']:
                try:
                    val = lc.get(cell)
                    print(f"    {cell} = {val}")
                except:
                    print(f"    {cell} = (empty/error)")
            # Scan for Weight rows
            print(f"    Rows with 'Weight' in col B:")
            found_any = False
            for row in range(1, 100):
                try:
                    b = lc.get(f'B{row}')
                    a = lc.get(f'A{row}')
                    if str(b) == 'Weight':
                        d = lc.get(f'D{row}')
                        print(f"      Row {row:3d}: A={str(a)[:30]:30s}  D(mass)={d}")
                        found_any = True
                except:
                    pass
            if not found_any:
                print("      (none found — weights are missing from spreadsheet)")

    print("\n" + "="*70)
    print("DIAGNOSTIC COMPLETE — paste output here for analysis")
    print("="*70 + "\n")
