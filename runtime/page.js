// Shared page setup for demo / game pages: a sharp canvas at any devicePixelRatio that refits on resize, one tap/click
// handler in logical coordinates (mouse, pen, touch), and a preload bar. Browser only; the logic modules don't need it.
import { fitCanvas, loadClips } from "./anim.js";

/**
 * Set up `canvas` to draw in logical `w` x `h` px. `onTap(x, y, event)` gets logical coordinates (before any camera).
 * Returns a stage: {ctx, w, h, view, begin(camX), on("tap", fn)}; call `begin()` at the start of each draw (it resets the transform to
 * logical px, translated by -camX for side-scrolling).
 */
export function setupStage(canvas, w, h, { onTap = null } = {}) {
  canvas.style.touchAction = "manipulation";   // no double-tap zoom delay on touch screens
  const ctx = canvas.getContext("2d");
  const stage = {
    canvas, ctx, w, h, view: fitCanvas(canvas, w, h),
    begin(camX = 0) { stage.view.reset(ctx); if (camX) ctx.translate(-camX, 0); return ctx; },
    refit() { stage.view = fitCanvas(canvas, w, h); },
    taps: onTap ? [onTap] : [],
    on(evt, fn) { if (evt === "tap") stage.taps.push(fn); return stage; },
  };
  addEventListener("resize", stage.refit);   // also fires on browser zoom, which changes devicePixelRatio
  canvas.addEventListener("pointerup", ev => {
    if (ev.pointerType === "mouse" && ev.button !== 0) return;
    const p = stage.view.toLogical(ev.clientX, ev.clientY);
    for (const fn of stage.taps) fn(p.x, p.y, ev);
  });
  return stage;
}

/**
 * loadClips with a progress bar inserted before `before` (an element). The bar is removed when loading finishes; on
 * failure it stays and shows the error. Image loading never hangs on a background tab (see anim.js loadImage).
 */
export async function preloadClips(base, keys, before = document.querySelector("canvas")) {
  const box = document.createElement("div");
  box.className = "preload";
  box.style.cssText = "padding:6px 14px;font:13px system-ui,sans-serif;color:#444";
  box.innerHTML = `loading animations <progress max="${keys.length}" value="0"></progress> <span></span>`;
  before.parentNode.insertBefore(box, before);
  const bar = box.querySelector("progress"), txt = box.querySelector("span");
  try {
    const clips = await loadClips(base, keys, (n, total, key) => { bar.max = total; bar.value = n; txt.textContent = `${n}/${total}${key ? " " + key : ""}`; });
    box.remove();
    return clips;
  } catch (e) {
    txt.textContent = `failed: ${e.message}`; box.style.color = "#c81e28";
    throw e;
  }
}
