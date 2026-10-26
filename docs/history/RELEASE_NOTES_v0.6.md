# ChemView Studio v0.6 release notes

- Set the first/opened frame to a parallel-projection isometric view (camera along [1,1,1]). Added an Isometric toolbar button. The Fit button preserves the current view orientation.
- Added `Ctrl+G` and `Edit > Select connected fragment(s)`. Components use displayed-cell bonds, including manual `Ctrl+B` bond overrides; periodic-image bonding is not inferred.
- Holding Alt while dragging **left**, **right**, or **middle** mouse buttons rotates selected fragment(s) in 3D, rolls around the viewing direction, or translates in the screen plane. Other atoms, the cell, and attached volume stay fixed.
- Alt dragging automatically expands an anchor-atom selection to the associated connected fragment(s). Plain mouse dragging still manipulates the camera. Plain right-click still clears the selection.
- Fragment drag creates one Undo entry per gesture, and the Coordinates table updates when the drag ends. The edited geometry can be exported through the existing Export structure command.
- Unit-cell-connected networks can contain most visible atoms. To separate an adsorbate attached to the surface, explicitly remove the connecting visual bonds with Ctrl+B first.
- Source includes regression tests for connected fragments, manual-bond overrides, rigid-body geometry, mouse events, and isometric camera orientation.
- GUI interactions have not been tested on Windows in this environment; Qt/PySide6 is not available here.
