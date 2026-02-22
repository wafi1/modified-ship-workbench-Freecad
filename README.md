# modified-ship-workbench-Freecad
modifications to FreeCAD ship workbench
Main difference to the old one, now own projects can be loaded and imported and the main difference for calculation is a central spreadsheet to modify tank filling but also to be able to read packing lists and to import cargo and to move it on board.

* New features:
* changing the method to import STL files to create less faces to update hydrostatic calculation speed
* new crane part with ability to add cranes to vessels model and to create a load situation single or tandem hook lift, for tandem hook lift with a rough possibility check
* new calculations for stability check also for situation while loading by crane
* GZ curve with IMO/SOLAS check and pdf report

  a ship model ShipDesign1.FCStd incl cranes and a pdf report is added GZ_Stability_Report__–__click_Save_(toolbar)_to_export_as_PDF.pdf

still a problem is to create the hull. Up to now no idea to use nurb or Bspline surfaces on imported structures.
