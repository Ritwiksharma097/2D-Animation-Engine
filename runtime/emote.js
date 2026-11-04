// Emote bubbles drawn by the engine, so a game can tell its story with little text: "!", "?", "heart", "...", "zZz".
// Logic is DOM-free; draw() takes a canvas 2D context in world coordinates.

export const EMOTE_KINDS = ["!", "?", "heart", "...", "zZz"];

export class Emotes {
  /** actors: {id: Character}; headroom: px above the feet where the bubble's tail points (per actor, default 170). */
  constructor(actors = {}, { headroom = {} } = {}) { this.actors = actors; this.headroom = headroom; this.active = []; this.log = []; }
  /** Show an emote over an actor for `ms` (replaces that actor's current one). */
  show(who, kind, ms = 1200) {
    if (!EMOTE_KINDS.includes(kind)) throw new Error(`unknown emote "${kind}" (use ${EMOTE_KINDS.join(" ")})`);
    this.active = this.active.filter(e => e.who !== who);
    this.active.push({ who, kind, ms, t: 0 }); this.log.push(`${who}:${kind}`);
  }
  clear() { this.active = []; }
  of(who) { return this.active.find(e => e.who === who)?.kind ?? null; }
  update(dt) { for (const e of this.active) e.t += dt; this.active = this.active.filter(e => e.t < e.ms); }
  draw(ctx) {
    for (const e of this.active) {
      const a = this.actors[e.who]; if (!a) continue;
      const pop = Math.min(1, e.t / 120), fade = Math.min(1, (e.ms - e.t) / 200);
      const x = a.x, y = a.y - (this.headroom[e.who] ?? 170) - 8 * (1 - pop), w = 44, h = 34;
      ctx.save(); ctx.globalAlpha = fade;
      ctx.fillStyle = "#fff"; ctx.strokeStyle = "#333"; ctx.lineWidth = 2;
      ctx.beginPath(); if (ctx.roundRect) ctx.roundRect(x - w / 2, y - h, w, h, 10); else ctx.rect(x - w / 2, y - h, w, h);
      ctx.moveTo(x - 6, y); ctx.lineTo(x, y + 9); ctx.lineTo(x + 6, y); ctx.fill(); ctx.stroke();
      ctx.fillStyle = "#fff"; ctx.fillRect(x - 5, y - 2, 10, 3);   // hide the bubble edge where the tail joins
      const cy = y - h / 2;
      if (e.kind === "heart") {
        ctx.fillStyle = "#d6336c"; ctx.beginPath();
        ctx.moveTo(x, cy + 9); ctx.bezierCurveTo(x - 16, cy - 2, x - 8, cy - 14, x, cy - 5); ctx.bezierCurveTo(x + 8, cy - 14, x + 16, cy - 2, x, cy + 9); ctx.fill();
      } else {
        ctx.fillStyle = e.kind === "!" ? "#c81e28" : "#222"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
        ctx.font = e.kind === "zZz" ? "bold 15px system-ui" : "bold 22px system-ui"; ctx.fillText(e.kind, x, cy + 1);
      }
      ctx.restore();
    }
  }
}
