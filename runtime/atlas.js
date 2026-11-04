// Atlas loading and per-level clip lists. `workbench/atlas.py` merges a character's exports into a few pages plus
// <character>/_atlas.json (clip JSON embedded, with each sheet's offset on its page). Loading a set of clips fetches one
// JSON per character and only the pages those clips are on; clips already loaded are kept.
import { makeClip, loadImage, loadClip } from "./anim.js";

const manifests = new Map(), pages = new Map();

async function manifest(base, character) {
  const k = `${base}/${character}`;
  if (!manifests.has(k)) manifests.set(k, fetch(`${base}/${character}/_atlas.json`).then(r => (r.ok ? r.json() : null)).catch(() => null));
  return manifests.get(k);
}

/** Shift a clip JSON's frame rects onto its atlas page. */
export function onPage(json, offset) {
  return { ...json, frames: json.frames.map(f => ({ ...f, rect: [f.rect[0] + offset[0], f.rect[1] + offset[1], f.rect[2], f.rect[3]] })) };
}

/**
 * Load `keys` ("ren/walk_keypose", ...) into `into` (a clips object, kept across calls) from atlases where they exist,
 * else per clip. `onProgress(done, total, what)` counts images. Returns {clips, pagesLoaded, requests}.
 */
export async function loadAtlasClips(base, keys, { into = {}, onProgress = null } = {}) {
  const need = keys.filter(k => !into[k]);
  const byChar = new Map();
  for (const k of need) { const c = k.split("/")[0]; if (!byChar.has(c)) byChar.set(c, []); byChar.get(c).push(k); }
  const jobs = [];   // {what, run}
  let requests = 0;
  for (const [c, ks] of byChar) {
    const m = await manifest(base, c); requests++;
    const fallback = [];
    if (m) {
      const want = new Map();
      for (const k of ks) { const e = m.clips[k]; if (!e) { fallback.push(k); continue; } if (!want.has(e.page)) want.set(e.page, []); want.get(e.page).push(k); }
      for (const [pg, list] of want) jobs.push({ what: `${c} atlas page ${pg}`, run: async () => {
        const pk = `${base}/${c}/${pg}`;
        if (!pages.has(pk)) { pages.set(pk, loadImage(`${base}/${c}/${m.pages[pg].image}`)); requests++; }
        const img = await pages.get(pk);
        for (const k of list) into[k] = makeClip(k, onPage(m.clips[k].json, m.clips[k].offset), img);
      } });
    } else fallback.push(...ks);
    for (const k of fallback) jobs.push({ what: k, run: async () => { into[k] = await loadClip(base, k); requests += 2; } });
  }
  let done = 0;
  onProgress?.(0, jobs.length, null);
  await Promise.all(jobs.map(async j => { await j.run(); onProgress?.(++done, jobs.length, j.what); }));
  return { clips: into, pagesLoaded: [...pages.keys()].length, requests };
}

/**
 * The clip keys a level needs, from the role names (`{ren: {idle: "ren/idle", ...}, guard: {...}}`): the player's basic
 * set always; climbs only with ledges, jumps only with gaps or platforms, ladders only with ladders, the caught pose and
 * the guard's set only with patrols, the guard's eating only when something can distract him.
 */
export function clipsForLevel(level, names) {
  const R = names.ren, Gd = names.guard, out = new Set([R.idle, R.walk, R.interact, R.look_around].filter(Boolean));
  if ((level.ledges || []).length) { out.add(R.climb_up); out.add(R.climb_down); }
  const floors = level.floors || [];
  if ((level.platforms || []).length || floors.length > 1) out.add(R.jump);
  if ((level.ladders || []).length && R.ladder) out.add(R.ladder);
  if ((level.patrols || []).length) {
    out.add(R.caught);
    for (const r of ["idle", "walk", "angry"]) out.add(Gd[r]);
    if ((level.hotspots || []).some(h => h.purpose === "distract") || (level.objects || []).some(o => o.purpose === "distract")) out.add(Gd.eat);
  }
  return [...out].filter(Boolean);
}
