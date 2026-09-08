/**
 * Shared screen rendering — used by the display walls and by the admin preview.
 *
 * The design artwork ships with its countdown baked in. tools/prepare.py paints
 * those digits out and records where they were; this module puts live ones back
 * in the same place, in the same seven-segment face.
 */
(() => {
  'use strict';

  // --- the seven-segment face, measured off the artwork ---------------------
  // One digit cell is 350 x 612 with an 88-unit stroke. Segment ends are cut at
  // 45°; where a segment meets the corner of the cell it also picks up the
  // silhouette's chamfer, which is what gives this face its notched look.
  const W = 350, H = 612, T = 88, P = 20, C = 65, G = 67, S = 2, M = H / 2;

  const mirX = (pts) => pts.map(([x, y]) => [W - x, y]);
  const mirY = (pts) => pts.map(([x, y]) => [x, H - y]);

  const TOP = [[C, 0], [W - C, 0], [W - C + P, P], [W - C + 2 * P - T, T], [C - 2 * P + T, T], [C - P, P]];
  const UPPER_LEFT = [[0, C], [P, C - P], [T, C - 2 * P + T], [T, M - S - T + P], [P, M - S], [0, M - S - P]];
  const MIDDLE = [[G, M], [G + T / 2, M - T / 2], [W - G - T / 2, M - T / 2], [W - G, M], [W - G - T / 2, M + T / 2], [G + T / 2, M + T / 2]];

  const SEGMENTS = {
    a: TOP,
    d: mirY(TOP),
    f: UPPER_LEFT,
    b: mirX(UPPER_LEFT),
    e: mirY(UPPER_LEFT),
    c: mirX(mirY(UPPER_LEFT)),
    g: MIDDLE,
  };
  const DIGITS = {
    '0': 'abcdef', '1': 'bc', '2': 'abged', '3': 'abgcd', '4': 'fgbc',
    '5': 'afgcd', '6': 'afgedc', '7': 'abc', '8': 'abcdefg', '9': 'abcdfg',
    '-': 'g', ' ': '',
  };
  const path = (pts) => 'M' + pts.map((p) => p.join(' ')).join('L') + 'Z';

  /**
   * SVG markup for a run of digits sized to a slot.
   * `gapFrac` is the dark gap between cells as a fraction of the whole block,
   * exactly as the artwork had it.
   */
  function digitsSVG(text, gapFrac, count) {
    const n = count || text.length;
    // blockW = n cells + (n-1) gaps, where a gap is gapFrac of the whole block.
    const blockW = (n * W) / (1 - gapFrac * (n - 1));
    const gap = gapFrac * blockW;
    let d = '';
    for (let i = 0; i < n; i++) {
      const ch = text[i] || ' ';
      const ox = i * (W + gap);
      for (const key of DIGITS[ch] || '') {
        d += path(SEGMENTS[key].map(([x, y]) => [(x + ox).toFixed(1), y]));
      }
    }
    return { viewBox: `0 0 ${blockW.toFixed(1)} ${H}`, d, ratio: blockW / H };
  }

  // --- clock ---------------------------------------------------------------
  /**
   * Split a duration across the units a screen has rows for.
   *
   * `units` is the screen's own list, in order, from the manifest — e.g.
   * ['hours','minutes','seconds'] on the challenge screens and
   * ['minutes','seconds'] on the presentation ones. A screen with no hours row
   * rolls the hours into its minutes rather than losing them.
   */
  function faces(ms, units) {
    const list = Array.isArray(units) ? units.map((u) => String(u).toUpperCase())
               : units >= 2 ? ['HOURS', 'MINUTES'] : ['MINUTES'];
    const total = Math.max(0, Math.floor(ms / 1000));
    const pad = (n) => String(Math.min(99, n)).padStart(2, '0');
    const v = {
      HOURS: Math.floor(total / 3600),
      MINUTES: list.includes('HOURS') ? Math.floor((total % 3600) / 60) : Math.floor(total / 60),
      SECONDS: total % 60,
    };
    return list.map((u) => ({ v: pad(v[u] || 0), unit: u }));
  }

  // --- server clock offset -------------------------------------------------
  // Screens are notoriously badly set. Measure this device against the server so
  // every display resolves the same absolute end time to the same digit; keep the
  // fastest round-trip, as it is the least polluted by network jitter.
  function createClock() {
    let offset = 0, bestRtt = Infinity;
    async function calibrate(samples = 5) {
      for (let i = 0; i < samples; i++) {
        const t0 = performance.timeOrigin + performance.now();
        try {
          const { t } = await (await fetch('/time', { cache: 'no-store' })).json();
          const t1 = performance.timeOrigin + performance.now();
          const rtt = t1 - t0;
          if (rtt < bestRtt) { bestRtt = rtt; offset = t + rtt / 2 - t1; }
        } catch { /* offline — keep the previous offset */ }
        await new Promise((r) => setTimeout(r, 120));
      }
    }
    calibrate();
    // Laptops that sleep come back with a jumped clock.
    setInterval(() => { bestRtt = Infinity; calibrate(3); }, 5 * 60 * 1000);
    return {
      now: () => Date.now() + offset,
      get offset() { return offset; },
      remaining(state) {
        if (!state) return 0;
        if (state.status === 'running' && state.endsAt) return Math.max(0, state.endsAt - (Date.now() + offset));
        return Math.max(0, state.remainingMs || 0);
      },
    };
  }

  window.Screen7 = { digitsSVG, faces, createClock, CELL: { W, H } };
})();
