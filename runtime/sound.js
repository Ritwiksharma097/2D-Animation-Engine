// Sound hooks: character events and states map to sound ids; until real sounds exist each id is a placeholder WebAudio
// beep. Mute is remembered per browser. Works without audio (Node, blocked autoplay): `log` still records what played.
//
// Map keys per actor (FORMAT.md "Sounds"): "<event>" (a named clip event such as "pickup", or "bump", "turn"),
// "state:<to>" (entering a state: "walk", "jump", "climb"...), "frame:<clip key>:<0-based frame>".

export class Sounds {
  constructor({ defs = {}, storageKey = "workbench.muted" } = {}) {
    this.defs = defs; this.storageKey = storageKey; this.log = []; this.ac = null;
    let m = false; try { m = globalThis.localStorage?.getItem(storageKey) === "1"; } catch { /* storage blocked */ }
    this.muted = m;
  }
  setMuted(m) { this.muted = !!m; try { globalThis.localStorage?.setItem(this.storageKey, m ? "1" : "0"); } catch { /* storage blocked */ } }
  /** Create the AudioContext on a user gesture (browsers block audio before one). */
  unlock() {
    if (this.ac || !globalThis.AudioContext) return;
    try { this.ac = new AudioContext(); } catch { this.ac = null; }
  }
  play(id) {
    this.log.push(id);
    if (this.log.length > 200) this.log.shift();
    if (this.muted || !this.ac) return;
    const d = this.defs[id] ?? { freq: 440, ms: 80 };
    const t = this.ac.currentTime, o = this.ac.createOscillator(), g = this.ac.createGain();
    o.type = d.type ?? "square"; o.frequency.setValueAtTime(d.freq, t);
    if (d.slide) o.frequency.linearRampToValueAtTime(d.freq + d.slide, t + d.ms / 1000);
    g.gain.setValueAtTime(d.gain ?? 0.05, t); g.gain.exponentialRampToValueAtTime(0.0001, t + d.ms / 1000);
    o.connect(g).connect(this.ac.destination); o.start(t); o.stop(t + d.ms / 1000 + 0.02);
  }
  /** Subscribe a character's events to sounds by a map {key: soundId}. Returns the character. */
  bind(ch, map) {
    for (const [key, id] of Object.entries(map)) {
      if (key.startsWith("state:")) { const to = key.slice(6); ch.on("state", e => { if (e.to === to) this.play(id); }); }
      else if (key.startsWith("frame:")) {
        const k = key.lastIndexOf(":"), clip = key.slice(6, k), frame = +key.slice(k + 1);
        ch.on("frame", e => { if (e.clip === clip && e.frame === frame) this.play(id); });
      } else ch.on(key, () => this.play(id));
    }
    return ch;
  }
}
