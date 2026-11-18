# Camera restoration regression check

Confirmed root cause: `vtkCamera.DeepCopy()` changes camera properties without advancing the destination camera MTime. When an intermediate redraw has populated OpenGL camera matrices, restoring a document leaves the previous view cached until a mouse gesture modifies the camera.

Fix: after copying a saved document camera, explicitly call `camera.Modified()`. Preserve the original live camera object so followers and the interactor keep their camera references.

Also fixed native trackball state surviving a focus/file switch: stop the VTK interaction state, release focus, clear Qt drag/button state, and finish any active fragment gesture before remembering the outgoing document.

Validation: 38 tests passed in camera_regression.log. Six new cases cover all four orthographic/perspective switch combinations using direct framebuffer pixels, a document switch with an intermediate paint plus first pointer movement, and a real QVTK focus-loss gesture. The four restored images equal saved images pixel-for-pixel.

The screenshot compares the saved view, the old DeepCopy-only behavior, and the fixed restore. Reads use GetRGBACharPixelData; vtkWindowToImageFilter is intentionally avoided because it invalidates render caches and masks this bug.
