# Scalar-field planar slices

The Field page's **Planar slice…** dialog inspects the currently attached data field without modifying its values.

- Choose a plane parallel to two grid vectors; these are not assumed to be Cartesian x/y/z planes. Skewed cells retain their metric and physical shape.
- Position runs from 0% to 100%. Nonperiodic data span the first to last sampled plane. Periodic data span a full cell, wrapping the data at the boundary.
- Fractional positions use linear interpolation between adjacent grid planes. The heatmap interpolates sample colors for display, not new physical data.
- Toggle contour lines or a symmetric color range, or specify finite fixed color limits. The legend uses the source field's units.
- Slice statistics are nodal sample minimum, maximum and arithmetic mean. They are not integrated charge, probability or spatial averages over an arbitrary volume. Duplicate periodic display edges are excluded.
- CSV export contains Cartesian x/y/z in Å and each slice sample's value and unit. Periodic boundary samples are included in the exported displayed grid.

Slices are parallel to the grid vectors only; arbitrary Miller-index planes and arbitrary oblique Cartesian cuts are not implemented. A slice is limited to two million displayed samples to avoid excessive memory use.

CSV export runs in a cancellable background worker and replaces its destination only after a complete successful write. Large plots use at most 201 sampled points per in-plane axis and display an explicit reduction warning; this can hide fine features, but does not change exact slice statistics or exported samples.
