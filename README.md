# Hackathon Timer

One countdown, every screen, the same second — running inside the event's own
artwork. A small local server pushes state to any number of displays; a
passkey-locked control page drives them all.

## Run it

```bash
node server.js
```

The first run prepares the artwork (about a minute — see *How the screens are
built* below), then prints the URLs and the passkey:

```
Column screens →  http://192.168.1.24:3000/display
HD screens     →  http://192.168.1.24:3000/display
Admin          →  http://192.168.1.24:3000/admin
Passkey        →  INNOVATE
```

Options: `node server.js --port 8080 --key MYSECRET`

Needs Node.js, plus Python 3 with Pillow and NumPy for that one-off preparation
step (`pip3 install pillow numpy`). Once `public/screens/` exists it is never
needed again.

## On the day

1. Run the server on one laptop, kept awake and on the venue wifi.
2. Open `/display` on every column screen, TV, projector and laptop. Click once
   on each — that goes fullscreen and enables the countdown sound.
3. Open `/admin` on your own machine and enter the passkey.

Every screen must be on the same network as the server.

**The server holds the screen shape, so it has to be restarted after an update**
— and restarting also puts the timer back to its defaults, so do it before the
event rather than during it.

### The two programs

**Hacking time** — the challenge clock. Default 6 h 30 m, set in hours and
minutes. Screens, in the order they are usually shown:

| Screen | Artwork |
|---|---|
| Holding screen | `coloum-screen-01.jpg` |
| Challenge started | `coloum-screen-02.jpg` |
| Mentoring round 1 | `coloum-screen-03.jpg` |
| Build and develop | `coloum-screen-04.jpg` |
| Mentoring round 2 | `coloum-screen-05.jpg` |
| Prototype mode | `coloum-screen-06.jpg` |

The clock opens on the holding screen and moves to *Challenge started* the
moment you press Start. After that, **which screen is showing and what the clock
is doing are completely independent** — change the artwork as the day moves on
and the countdown never so much as flickers.

**Presentation time** — 5 minutes demo then 5 minutes judges, for 13 teams (all
three are editable). *Previous* and *Next* walk the running order team by team,
switching the artwork and re-winding the clock for each slot:

| Screen | Artwork |
|---|---|
| Holding screen | `coloum-screen-01.jpg` |
| Demo time | `coloum-screen(Teams)-01.jpg` |
| Judges time | `coloum-screen(Teams)-02.jpg` |
| Teams branding | `coloum-screen(Teams)-03.jpg` |

### Controls

| Control | What it does |
|---|---|
| Start / Resume | Starts the countdown on every screen at once |
| Pause | Freezes all screens; Resume picks up exactly where it stopped |
| Add time / Take off | Type a number of minutes — 60 for an extra hour — and it lands live |
| ±1 / ±5 min, +1 hour | The same thing, one press |
| Reset to full | Back to the configured length, stopped |
| End now | Jumps every screen straight to zero |
| Blackout | Hides every screen (useful during a keynote) |
| Message banner | Pushes a line of text across the bottom of every screen |

Keyboard on the admin page: `Space` start/pause, `R` reset, `←` `→` ∓1 minute.
Keyboard on a display: `F` fullscreen, `S` sound, `C` / `H` force a layout,
`D` diagnostics.

## The two layouts

A display picks its own layout from the shape of the screen it is on, so the
same URL works everywhere. A portrait screen gets the **column** layout — the
artwork exactly as designed. A landscape screen squarer than 2:1 gets the **HD**
layout, which takes the column apart and re-composes it for 16:9: the wordmark,
the phase headline and the strapline down one side, the clock across the other.
Force either with `?mode=column` or `?mode=hd`.

The column artwork is 1:4.5 — a 0.60 × 2.70 m panel exactly.

### Screen shape, from the admin page

A browser can measure the frame it was handed but never the wall that frame ends
up on. So the shape of the screen is something only you know, and the **Screen
shape** card on the admin page is where you say it — width and height in any
unit (only the ratio is read), and whether to stretch to fill the frame. It
lands on every display at once, live, like every other control.

It starts at **0.60 × 2.70 m, stretch on**, which is the artwork's own shape.
Leave it alone and the column screens are right without a single URL parameter.

*Stretch to fill the frame* is the setting that matters. Leave it **on** whenever
anything downstream — an LED processor, a media server — maps the browser's
frame onto the panel: the page then ignores the frame's shape entirely, takes its
layout from the size you typed, and paints the artwork corner to corner for the
processor to map. Turn it **off** when a browser is driving a screen directly and
you would rather see black bars than any stretch at all; each display then reads
its own frame, as it used to.

A mixed estate still works: the shape card is what the column screens follow, and
a TV or a laptop that should show the landscape composition is opened with
`?mode=hd`, which overrides it. `?fit=fill` and `?fit=contain` override the
stretch setting the same way, per screen.

### Driving a column through an LED processor or media server

Software like **NovaStar Kompass FX3** renders a web page onto a canvas of *its
own* size and then stretches that canvas onto the panel. The canvas is usually
landscape — 1920 × 1080 — so the browser is handed a 16:9 frame, picks the HD
layout for it, and the processor then squashes that landscape composition about
eight times sideways onto the column. The design ends up crushed into a strip
down the left of the panel with the blurred backdrop filling the rest.

The page cannot detect this: a stretched canvas looks exactly like an ordinary
one from inside the browser. It has to be told — which is what the **Screen
shape** card does, and why it is on by default. With it set to 0.60 × 2.70 m and
*stretch to fill the frame* ticked, plain `/display` is correct on the wall
whatever canvas Kompass renders it at. (`?fit=fill` on the URL does the same for
one screen on its own.)

Set the layer to cover the whole LED output, and don't letterbox it in Kompass
either.

**Better, if the option is there:** give the webpage layer a *tall* resolution —
the panel's own pixel count, or something like 480 × 2160. Then nothing is
stretched at any point in the chain and no horizontal detail is thrown away.
`fit=fill` is correct either way, and is the one to reach for when the canvas
size is fixed or unknown.

### When a screen looks wrong

Add **`?debug`** (or press `D` on the display) for a readout of the frame size
the browser was actually given, the ratio it works out to, and which layout it
picked, with centre lines and a border showing the frame's true edges. That is
usually enough to tell a media-server canvas problem from a page problem.

## How the screens are built

The design artwork has its countdown *painted in* — every screen carries a
static "20 HOURS / 30 MINUTES". `tools/prepare.py` takes those digits back out
so a live clock can go in their place. For each image it:

1. finds the seven-segment digit blocks and their unit labels,
2. paints the digits out — filling the hole by growing the surrounding artwork
   into it, which follows the background's gradients and glows rather than
   flattening them,
3. records the exact position, size, gap and colour of every block,
4. cuts out the pieces the HD layout re-composes,
5. writes it all to `public/screens/` with a `manifest.json`.

The browser then redraws the digits as SVG in the same seven-segment face,
measured off the artwork: a 350 × 612 cell, an 88-unit stroke, ends mitred at
45°, and the cell's own corner chamfer where a segment meets it. Positioned from
the manifest, live digits land exactly where the designed ones were.

The unit words are left in the artwork and used as they are. Only when the
countdown has to change unit — under an hour, when *hours / minutes* becomes
*minutes / seconds* — does a screen cover the designed word with its own patch
and set the new one to match.

Re-run `python3 tools/prepare.py` if the artwork in `Assets/` ever changes.

## How the screens stay in sync

The server never streams a ticking number — that would drift and stutter. It
broadcasts an absolute **end timestamp** in server time over Server-Sent Events.
Each screen separately measures its own clock offset against the server (several
`/time` round-trips, keeping the fastest as the least jitter-polluted sample) and
renders `endsAt − (localNow + offset)`.

Screens then agree to within a few milliseconds even if their own clocks are
badly set, and one that joins late or reconnects lands on the right number
immediately. A heartbeat every 5 s re-syncs anything that drifted.

## Notes

- **Keep the server laptop awake.** Sleep stops the server. Plug it in and set
  "never sleep" in Energy Saver.
- Displays hold a screen wake-lock where the browser supports it, but TV
  screensavers are a separate setting worth checking.
- Displays reconnect on their own after a wifi blip and show a red
  "Reconnecting" bar meanwhile.
- The passkey only guards the admin page, and traffic is plain HTTP on the local
  network. That is the right level for a venue timer — don't reuse the passkey
  for anything that matters, and don't expose the port to the internet.
- Restarting the server puts the timer back to its defaults.
