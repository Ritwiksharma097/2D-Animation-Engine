// Scenes and layering on top of runtime/level.js: parallax layers, foreground occluders, depth sorting, hiding spots,
// and doors with a fade between screens. Logic is DOM-free (Node-testable); draw helpers take a canvas 2D context.
// Level keys (FORMAT.md "Levels"): layers, occluders, hiding_spots, doors.

/** Pull the scene parts out of a level JSON, with defaults filled in. */
export function sceneFromLevel(level) {
  const floorY = id => (level.floors.find(f => f.id === id) ?? level.floors[0]).y;
  const surfY = on => level.floors.find(f => f.id === on)?.y ?? level.ledges?.find(l => l.id === on)?.top ?? level.platforms?.find(p => p.id === on)?.top ?? floorY(on.split("#")[0]);
  return {
    layers: (level.layers || []).map(l => ({ parallax: 1, depth: -100, rects: [], ...l })),
    occluders: (level.occluders || []).map(o => ({ depth: 50, alpha: 1, color: "#6b6b6b", blocks_sight: false, ...o })),
    hiding: (level.hiding_spots || []).map(h => {
      const y1 = surfY(h.on);
      return { kind: "behind", reveal_radius: 60, color: "#7a5a3a", ...h, y0: y1 - h.height, y1, depth: h.kind === "in" ? -5 : 5 };
    }),
    doors: (level.doors || []).map(d => ({ kind: "door", width: 60, height: 150, ...d, y1: surfY(d.on) })),
  };
}

/** Screen x of a world x on a layer with parallax factor p (0 = fixed to the screen, 1 = moves with the world). */
export const parallaxX = (x, camX, p) => x - camX * p;

/**
 * Sort drawables back to front: by `depth` (lower first), then by `y` (feet higher on screen first, so nearer things
 * overlap farther ones), then by `order` (insertion) so equal items keep a stable order.
 */
export function depthSort(items) {
  return items.map((it, order) => ({ it, order })).sort((a, b) =>
    (a.it.depth ?? 0) - (b.it.depth ?? 0) || (a.it.y ?? 0) - (b.it.y ?? 0) || a.order - b.order).map(x => x.it);
}

/** The hiding spot containing x on a surface (a region id like "A#0" matches spots on floor "A"), or null. */
export function hidingSpotAt(spots, surface, x) {
  const floor = String(surface).split("#")[0];
  return spots.find(h => (h.on === surface || h.on === floor) && x >= h.x0 && x <= h.x1) ?? null;
}

/**
 * Keep a character's hiding state in sync: hidden when holding a pose tagged "hide" inside a spot. Hidden characters are
 * silent and passable; GuardBrain.look sees them only within the spot's reveal_radius.
 */
export function updateHiding(ch, spots) {
  const spot = ch.holding && ch.cmd?.tag === "hide" ? hidingSpotAt(spots, ch.surface, ch.x) : null;
  ch.hidingIn = spot; ch.silent = ch.passable = !!spot;
  return spot;
}

/** Visibility of a hidden target: seen only when the viewer is within the spot's reveal radius. */
export function hiddenCheck(spot, viewerX, targetX) {
  const d = Math.abs(viewerX - targetX);
  return d <= spot.reveal_radius ? null : { seen: false, reason: `hidden (${spot.id})`, distance: d };
}

/** The door near x on a surface (within its width), or null. */
export function doorAt(doors, surface, x, slack = 0) {
  const floor = String(surface).split("#")[0];
  return doors.find(d => (d.on === surface || d.on === floor) && Math.abs(x - d.x) <= d.width / 2 + slack) ?? null;
}

/** A fade to black and back. start(onMid) fades out, calls onMid (switch screens there), fades in. */
export class Fader {
  constructor({ outMs = 350, inMs = 350 } = {}) { this.outMs = outMs; this.inMs = inMs; this.phase = null; this.t = 0; }
  start(onMid) { if (this.phase) return false; this.phase = "out"; this.t = 0; this.onMid = onMid; return true; }
  get busy() { return this.phase !== null; }
  get alpha() { return this.phase === "out" ? Math.min(1, this.t / this.outMs) : this.phase === "in" ? Math.max(0, 1 - this.t / this.inMs) : 0; }
  update(dt) {
    if (!this.phase) return;
    this.t += dt;
    if (this.phase === "out" && this.t >= this.outMs) { this.phase = "in"; this.t = 0; this.onMid?.(); }
    else if (this.phase === "in" && this.t >= this.inMs) { this.phase = null; this.t = 0; }
  }
}

// ------------------------------------------------------------------ drawing

/** Draw parallax layers with depth < 0 (background) or > 0 (foreground), in screen space after stage.begin(). */
export function drawLayers(ctx, layers, camX, front = false) {
  for (const l of layers) {
    if ((l.depth > 0) !== front) continue;
    ctx.save(); ctx.globalAlpha = l.alpha ?? 1;
    for (const r of l.rects) { ctx.fillStyle = r.color ?? l.color ?? "#ddd"; ctx.fillRect(parallaxX(r.x, camX, l.parallax), r.y, r.w, r.h); }
    ctx.restore();
  }
}

/**
 * The world-space drawables of a scene plus actors, depth-sorted. Each item is {depth, y, draw(ctx)}. Actors are runtime
 * Characters (depth 0, y = feet); a character hiding "behind" a spot is drawn before it, so the spot covers him.
 */
export function sceneDrawables(scene, actors, { label = true } = {}) {
  const items = actors.map(a => ({ depth: a.depth ?? 0, y: a.y, draw: ctx => a.draw(ctx), actor: a }));
  for (const h of scene.hiding) items.push({ depth: h.depth, y: h.y1 + 0.1, draw: ctx => {
    ctx.save(); ctx.globalAlpha = h.kind === "behind" ? 0.92 : 1; ctx.fillStyle = h.color; ctx.fillRect(h.x0, h.y0, h.x1 - h.x0, h.y1 - h.y0);
    if (label) { ctx.globalAlpha = 1; ctx.fillStyle = "#fff"; ctx.font = "11px system-ui"; ctx.fillText(`hide: ${h.id}`, h.x0 + 4, h.y0 + 13); }
    ctx.restore();
  } });
  for (const o of scene.occluders) items.push({ depth: o.depth, y: o.y1, draw: ctx => {
    ctx.save(); ctx.globalAlpha = o.alpha; ctx.fillStyle = o.color; ctx.fillRect(o.x0, o.y0, o.x1 - o.x0, o.y1 - o.y0); ctx.restore();
  } });
  for (const d of scene.doors) items.push({ depth: -2, y: d.y1, draw: ctx => {
    ctx.save(); ctx.fillStyle = d.kind === "exit" ? "rgba(27,175,122,0.35)" : "#8b6a4a"; ctx.fillRect(d.x - d.width / 2, d.y1 - d.height, d.width, d.height);
    ctx.fillStyle = d.kind === "exit" ? "#1baf7a" : "#fff"; ctx.font = "11px system-ui";
    ctx.fillText(d.kind === "exit" ? "EXIT" : `door > ${d.to?.level ?? "?"}`, d.x - d.width / 2 + 3, d.y1 - d.height + 13); ctx.restore();
  } });
  return depthSort(items);
}

/** Black fade overlay in screen space. */
export function drawFade(ctx, fader, w, h) {
  if (!fader.alpha) return;
  ctx.save(); ctx.globalAlpha = fader.alpha; ctx.fillStyle = "#000"; ctx.fillRect(0, 0, w, h); ctx.restore();
}
