# LELE 0.9.3 validation

Date: 2026-10-26

## Changes

- Pose and horizontal position now update together every 800 ms. There is
  no interpolation or movement while a frame is held.
- Remove the overhead 乐乐 badge. Retain the caption below the animation.
- Keep the 24-second left-to-right loop and stop the timer when hidden.

## Checks

- Full regression suite: **126 tests passed, 61 subtests passed**, with no
  failures or skipped cases.
- The live timing regression confirms the initial pose and X position remain
  unchanged before the first timer tick, both change at the next frame, and
  the new X position remains unchanged during the following hold.
- Hidden animation remains stationary. The step sequence crosses the canvas,
  loops to the left, and stays inside the canvas after responsive resizing.
- The startup check confirms no overhead label is present. The rendered PNG
  was visually inspected for the same change.
- The GIF preview contains 30 frames, each held for exactly 800 ms, with the
  same 24-second loop as the application.

## Environment and limits

Linux, Python 3.12.14, PySide6 6.12.0, VTK 9.7.1 and ASE 3.29.0. Qt uses the
offscreen platform and standalone VTK rendering uses EGL. The prior native
Windows and embedded OpenGL validation limits remain as documented in
`VALIDATION_v0.9.2.md`. No Windows EXE was built or GitHub changes pushed.

```text
QT_QPA_PLATFORM=offscreen VTK_DEFAULT_OPENGL_WINDOW=vtkEGLRenderWindow python -m pytest tests -q
```
