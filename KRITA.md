# Krita round trip

Krita is on the owner's PC, not in the cloud, so **this was tested only up to the file level**: the
folder layout, image sizes and the return path through the intake (a unit test simulates the drawing
step with Krita's render file names and checks every frame comes back pixel-identical). Krita itself
was never run.

1. Export:
   ```
   python workbench/krita_export.py ren walk_keypose --spec specs/ren_walk_inbetweens.json
   python workbench/krita_export.py guard walk --spec specs/guard_walk.json
   ```
   This writes `out/krita/<character>_<action>/`: `frames/` (kept drawings plus blank cells to draw),
   `targets/`, `onion/`, `ghost/`, `ground.png`, `pack.json`, and step-by-step `KRITA_STEPS.md`. Every
   image is the game cell size (640 x 576).
2. In Krita, use File > Import Animation Frames for `frames/`, then for each guide folder on its own
   layer. Draw the blank frames, hide the guides, then File > Render Animation > Image Sequence (PNG).
3. Bring the rendered folder back:
   ```
   python workbench/intake.py <folder> --character ren --action walk_8 --replaces walk_keypose --spec specs/ren_walk_inbetweens.json --as-is
   ```
   It lands in `incoming/` and on the review page as "new, awaiting owner".

**Why no `.kra` file.** A `.kra` is a zip (`mimetype`, `maindoc.xml`, `documentinfo.xml`, layer data),
but animated paint layers are stored in Krita's own tiled raster format (LZF-compressed 64 px tiles)
plus per-layer keyframe XML. That format is documented only in Krita's source. Without Krita to open
the result, a hand-written `.kra` could fail to load or load wrongly, and nothing here could detect
either. The PNG sequence plus Import Animation Frames uses only Krita's standard import, so I
stopped there. Writing `.kra` directly is worth trying on the owner's PC, where each file can be
opened and checked.
