#!/usr/bin/env node
/**
 * Hackathon Timer — one countdown, every screen, the same second.
 *
 * Run:  node server.js  [--port 3000]  [--key INNOVATE]
 *
 * Columns open   http://<this-machine-ip>:3000/column
 * Other screens  http://<this-machine-ip>:3000/display?mode=hd
 * Admin opens    http://<this-machine-ip>:3000/admin   (passkey required)
 *
 * Sync design: the server never streams a ticking number. It broadcasts an
 * absolute end timestamp in *server* time, and every client measures its own
 * clock offset against the server (/time round-trips). Each screen then renders
 * `endsAt - (Date.now() + offset)`, so screens stay in step to within a few ms
 * even if their own clocks are wrong or they joined late.
 */

'use strict';

const http = require('http');
const fs = require('fs');
const path = require('path');
const os = require('os');
const { spawnSync } = require('child_process');

// ---------------------------------------------------------------- arguments

function arg(name, fallback) {
  const i = process.argv.indexOf('--' + name);
  return i !== -1 && process.argv[i + 1] ? process.argv[i + 1] : fallback;
}

const PORT = parseInt(arg('port', process.env.PORT || '3000'), 10);
const PASSKEY = arg('key', process.env.TIMER_KEY || 'INNOVATE');
const PUBLIC_DIR = path.join(__dirname, 'public');
const MANIFEST = path.join(PUBLIC_DIR, 'screens', 'manifest.json');

// ------------------------------------------------------ screen artwork

// The design JPEGs have to be prepared once (digits painted out, geometry
// measured). Do it on first run rather than making it a separate ritual.
function ensureScreens() {
  if (fs.existsSync(MANIFEST)) return;
  console.log('\n  Preparing the screen artwork — this runs once, ~1 minute…\n');
  const r = spawnSync('python3', [path.join(__dirname, 'tools', 'prepare.py')], { stdio: 'inherit' });
  if (r.status !== 0 || !fs.existsSync(MANIFEST)) {
    console.error('\n  Could not prepare the artwork. Run it by hand to see why:');
    console.error('      python3 tools/prepare.py');
    console.error('  It needs Python 3 with Pillow and NumPy (pip3 install pillow numpy).\n');
    process.exit(1);
  }
}

ensureScreens();
const SCREENS = JSON.parse(fs.readFileSync(MANIFEST, 'utf8')).screens;

/** Screens the admin may pick for a program, in the order they run. */
const MENU = {
  hacking: ['hold', 'started', 'mentoring1', 'build', 'mentoring2', 'prototype'],
  presentation: ['hold', 'demo', 'judges', 'teams'],
};
const SEGMENT_SCREEN = { demo: 'demo', judges: 'judges' };

// ------------------------------------------------------------------- state

const DEFAULT_HACK_MS = 6 * 60 * 60 * 1000 + 30 * 60 * 1000; // 6h 30m
const DEFAULT_SEGMENT_MS = 5 * 60 * 1000;                    // 5m demo, 5m judges
const DEFAULT_TEAMS = 13;

// The screen shape the artwork is drawn for: 0.60 m x 2.70 m, which is 1:4.5.
// Any unit will do — only the ratio is ever used.
const DEFAULT_PANEL_W = 0.6;
const DEFAULT_PANEL_H = 2.7;

const state = {
  rev: 0,
  program: 'hacking',
  screen: 'hold',

  status: 'idle',          // idle | running | paused | finished
  endsAt: null,            // epoch ms in server time — only while running
  remainingMs: DEFAULT_HACK_MS,
  durationMs: DEFAULT_HACK_MS,

  hackMs: DEFAULT_HACK_MS,
  demoMs: DEFAULT_SEGMENT_MS,
  judgesMs: DEFAULT_SEGMENT_MS,
  teams: DEFAULT_TEAMS,
  team: 1,
  segment: 'demo',         // demo | judges

  message: '',
  blackout: false,

  // How the displays should lay themselves out. A browser can measure the frame
  // it was given but never the wall that frame ends up on, so the shape of the
  // screen is something only the operator knows — this is where they say it.
  panelW: DEFAULT_PANEL_W,
  panelH: DEFAULT_PANEL_H,
  panelFill: true,         // paint corner to corner rather than letterboxing

  updatedAt: Date.now(),
};

const segmentMs = () => (state.segment === 'judges' ? state.judgesMs : state.demoMs);
const programDefaultMs = () => (state.program === 'presentation' ? segmentMs() : state.hackMs);

function remainingNow() {
  if (state.status === 'running') return Math.max(0, state.endsAt - Date.now());
  return Math.max(0, state.remainingMs);
}

function snapshot() {
  return {
    rev: state.rev,
    program: state.program,
    screen: state.screen,
    status: state.status,
    endsAt: state.endsAt,
    remainingMs: remainingNow(),
    durationMs: state.durationMs,
    hackMs: state.hackMs,
    demoMs: state.demoMs,
    judgesMs: state.judgesMs,
    teams: state.teams,
    team: state.team,
    segment: state.segment,
    message: state.message,
    blackout: state.blackout,
    panelW: state.panelW,
    panelH: state.panelH,
    panelFill: state.panelFill,
    serverTime: Date.now(),
    displays: countClients('display'),
    admins: countClients('admin'),
  };
}

function touch() {
  state.rev += 1;
  state.updatedAt = Date.now();
  broadcast();
}

/** Put the clock back to a stopped, fully-wound `ms`. */
function arm(ms) {
  state.durationMs = Math.max(0, ms);
  state.remainingMs = state.durationMs;
  state.endsAt = null;
  state.status = 'idle';
}

// -------------------------------------------------------------- SSE clients

/** @type {Set<{res: http.ServerResponse, role: string}>} */
const clients = new Set();

function countClients(role) {
  let n = 0;
  for (const c of clients) if (c.role === role) n++;
  return n;
}

function broadcast() {
  const payload = `event: state\ndata: ${JSON.stringify(snapshot())}\n\n`;
  for (const c of clients) {
    try {
      c.res.write(payload);
    } catch {
      clients.delete(c);
    }
  }
}

// Heartbeat: keeps proxies from closing the stream, re-syncs any drifted screen,
// and refreshes the connected-screen count on the admin page.
setInterval(broadcast, 5000);

// Flip to "finished" the instant the clock hits zero, so every screen agrees.
setInterval(() => {
  if (state.status === 'running' && Date.now() >= state.endsAt) {
    state.status = 'finished';
    state.remainingMs = 0;
    state.endsAt = null;
    touch();
  }
}, 200);

// ------------------------------------------------------------------ actions

const num = (v, d = 0) => (Number.isFinite(Number(v)) ? Number(v) : d);
const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

function applyAction(action, payload = {}) {
  switch (action) {
    case 'program': {
      const p = payload.program === 'presentation' ? 'presentation' : 'hacking';
      if (p === state.program) break;
      state.program = p;
      state.screen = 'hold';          // both programs open on the holding art
      state.team = 1;
      state.segment = 'demo';
      arm(programDefaultMs());
      break;
    }

    case 'screen': {
      // Picking a screen never disturbs the clock — that is the whole point of
      // having the two controls separate.
      const id = String(payload.screen || '');
      if (MENU[state.program].includes(id)) state.screen = id;
      break;
    }

    case 'configure': {
      if (payload.hackMs != null) {
        state.hackMs = Math.max(0, num(payload.hackMs));
        if (state.program === 'hacking' && state.status !== 'running') arm(state.hackMs);
      }
      if (payload.demoMs != null) state.demoMs = Math.max(0, num(payload.demoMs));
      if (payload.judgesMs != null) state.judgesMs = Math.max(0, num(payload.judgesMs));
      if (payload.teams != null) state.teams = clamp(Math.round(num(payload.teams, DEFAULT_TEAMS)), 1, 99);
      if (state.program === 'presentation' && state.status !== 'running'
          && (payload.demoMs != null || payload.judgesMs != null)) {
        arm(segmentMs());
      }
      state.team = clamp(state.team, 1, state.teams);
      break;
    }

    // Presentation running order: team 1 demo, team 1 judges, team 2 demo, …
    case 'segment': {
      if (state.program !== 'presentation') break;
      if (payload.team != null) state.team = clamp(Math.round(num(payload.team, 1)), 1, state.teams);
      if (payload.segment === 'demo' || payload.segment === 'judges') state.segment = payload.segment;
      state.screen = SEGMENT_SCREEN[state.segment];
      arm(segmentMs());
      break;
    }

    case 'advance': {
      if (state.program !== 'presentation') break;
      const dir = num(payload.dir, 1) < 0 ? -1 : 1;
      let index = (state.team - 1) * 2 + (state.segment === 'judges' ? 1 : 0) + dir;
      index = clamp(index, 0, state.teams * 2 - 1);
      state.team = Math.floor(index / 2) + 1;
      state.segment = index % 2 ? 'judges' : 'demo';
      state.screen = SEGMENT_SCREEN[state.segment];
      arm(segmentMs());
      break;
    }

    case 'start': {
      if (state.status === 'running') break;
      const dur = state.status === 'paused' ? state.remainingMs : (state.remainingMs || programDefaultMs());
      state.endsAt = Date.now() + dur;
      state.remainingMs = dur;
      state.status = 'running';
      // The holding art has no clock on it; move on to the screen that does.
      if (state.screen === 'hold') {
        state.screen = state.program === 'presentation' ? SEGMENT_SCREEN[state.segment] : 'started';
      }
      break;
    }

    case 'pause': {
      if (state.status !== 'running') break;
      state.remainingMs = remainingNow();
      state.endsAt = null;
      state.status = 'paused';
      break;
    }

    case 'reset': {
      // Back to the length that was configured, not to any time added since.
      arm(programDefaultMs());
      break;
    }

    case 'adjust': {
      // Add or remove time without breaking the running clock.
      const delta = num(payload.deltaMs, 0);
      if (state.status === 'running') {
        state.endsAt = Math.max(Date.now(), state.endsAt + delta);
      } else {
        state.remainingMs = Math.max(0, state.remainingMs + delta);
        if (state.remainingMs > 0 && state.status === 'finished') state.status = 'paused';
      }
      state.durationMs = Math.max(state.durationMs, remainingNow());
      break;
    }

    case 'finish': {
      state.status = 'finished';
      state.remainingMs = 0;
      state.endsAt = null;
      break;
    }

    case 'message':
      state.message = String(payload.message ?? '').slice(0, 280);
      break;

    case 'blackout':
      state.blackout = !!payload.blackout;
      break;

    case 'panel': {
      // Only the ratio matters, so the numbers are kept as given — metres,
      // millimetres or pixels all read back to the operator unchanged.
      if (payload.panelW != null) state.panelW = clamp(num(payload.panelW, DEFAULT_PANEL_W), 0.01, 10000);
      if (payload.panelH != null) state.panelH = clamp(num(payload.panelH, DEFAULT_PANEL_H), 0.01, 10000);
      if (payload.panelFill != null) state.panelFill = !!payload.panelFill;
      break;
    }

    default:
      return { ok: false, error: 'Unknown action: ' + action };
  }

  touch();
  return { ok: true, state: snapshot() };
}

// ------------------------------------------------------------------ helpers

const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.jpg': 'image/jpeg',
  '.png': 'image/png',
};

function send(res, code, body, type = 'application/json; charset=utf-8', extra = {}) {
  res.writeHead(code, Object.assign({ 'Content-Type': type, 'Cache-Control': 'no-store' }, extra));
  res.end(typeof body === 'string' || Buffer.isBuffer(body) ? body : JSON.stringify(body));
}

/** Serve a file from public/, refusing anything that tries to climb out of it. */
function serveStatic(res, rel) {
  const file = path.resolve(PUBLIC_DIR, '.' + path.posix.normalize('/' + rel));
  if (!file.startsWith(PUBLIC_DIR + path.sep)) return send(res, 403, { error: 'Forbidden' });
  fs.readFile(file, (err, buf) => {
    if (err) return send(res, 404, { error: 'Not found' });
    const ext = path.extname(file);
    // Artwork never changes once prepared; the pages must not be cached.
    const cache = ext === '.jpg' || ext === '.png' ? 'public, max-age=86400' : 'no-store';
    send(res, 200, buf, TYPES[ext] || 'application/octet-stream', { 'Cache-Control': cache });
  });
}

function readBody(req) {
  return new Promise((resolve) => {
    let data = '';
    req.on('data', (c) => {
      data += c;
      if (data.length > 1e5) req.destroy();
    });
    req.on('end', () => {
      try {
        resolve(JSON.parse(data || '{}'));
      } catch {
        resolve({});
      }
    });
  });
}

/** Constant-time-ish comparison so the passkey can't be probed by timing. */
function keyOk(supplied) {
  const a = String(supplied ?? '');
  if (a.length !== PASSKEY.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ PASSKEY.charCodeAt(i);
  return diff === 0;
}

// ------------------------------------------------------------------- server

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, 'http://localhost');
  const route = url.pathname;

  if (route === '/') {
    res.writeHead(302, { Location: '/display' });
    return res.end();
  }
  if (route === '/display') return serveStatic(res, 'display.html');
  // The same page on a second path. A media server's embedded browser cannot
  // have a cached entry for a path it has never fetched, so this is also the
  // way to be certain a display is running the current file — on an old server
  // it 404s instead of quietly showing a stale page.
  if (route === '/column') return serveStatic(res, 'display.html');
  if (route === '/admin') return serveStatic(res, 'admin.html');
  if (route === '/screen.js') return serveStatic(res, 'screen.js');
  if (route.startsWith('/screens/')) return serveStatic(res, route);

  // Clock calibration probe — deliberately tiny so the round-trip is honest.
  if (route === '/time') return send(res, 200, { t: Date.now() });

  if (route === '/state') return send(res, 200, snapshot());
  if (route === '/screens.json') return send(res, 200, { screens: SCREENS, menu: MENU });

  if (route === '/events') {
    const role = url.searchParams.get('role') === 'admin' ? 'admin' : 'display';
    res.writeHead(200, {
      'Content-Type': 'text/event-stream; charset=utf-8',
      'Cache-Control': 'no-cache, no-transform',
      Connection: 'keep-alive',
      'X-Accel-Buffering': 'no',
    });
    res.write('retry: 1000\n\n');
    const client = { res, role };
    clients.add(client);
    res.write(`event: state\ndata: ${JSON.stringify(snapshot())}\n\n`);
    broadcast(); // let the admin see the new screen appear
    req.on('close', () => {
      clients.delete(client);
      broadcast();
    });
    return;
  }

  if (route === '/api/auth' && req.method === 'POST') {
    const body = await readBody(req);
    if (!keyOk(body.key)) return send(res, 401, { ok: false, error: 'Incorrect passkey' });
    return send(res, 200, { ok: true, state: snapshot() });
  }

  if (route === '/api/control' && req.method === 'POST') {
    const body = await readBody(req);
    if (!keyOk(body.key)) return send(res, 401, { ok: false, error: 'Incorrect passkey' });
    const result = applyAction(body.action, body.payload || {});
    return send(res, result.ok ? 200 : 400, result);
  }

  send(res, 404, { error: 'Not found' });
});

// --------------------------------------------------------------- start-up

function lanAddresses() {
  const out = [];
  for (const list of Object.values(os.networkInterfaces())) {
    for (const net of list || []) {
      if (net.family === 'IPv4' && !net.internal) out.push(net.address);
    }
  }
  return out;
}

server.listen(PORT, '0.0.0.0', () => {
  const addrs = lanAddresses();
  const host = addrs[0] || 'localhost';
  const line = '─'.repeat(54);
  console.log('\n  ⏱  HACKATHON TIMER');
  console.log('  ' + line);
  console.log('  Column screens →  http://' + host + ':' + PORT + '/column');
  console.log('  HD screens     →  http://' + host + ':' + PORT + '/display?mode=hd');
  console.log('  Admin          →  http://' + host + ':' + PORT + '/admin');
  console.log('  Passkey        →  ' + PASSKEY);
  console.log('  ' + line);
  if (addrs.length > 1) console.log('  Other addresses: ' + addrs.slice(1).join(', '));
  console.log('  /column forces the column layout and cannot be overridden —');
  console.log('  use it for LED processors and media servers.  Ctrl+C to stop.\n');
});
