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
Column screens →  http://192.168.1.24:3000/column
HD screens     →  http://192.168.1.24:3000/display?mode=hd
Admin          →  http://192.168.1.24:3000/admin
Passkey        →  INNOVATE
```

Options: `node server.js --port 8080 --key MYSECRET`

Needs Node.js, plus Python 3 with Pillow and NumPy for that one-off preparation
step (`pip3 install pillow numpy`). Once `public/screens/` exists it is never
needed again.

## On the day

1. Run the server on one laptop, kept awake and on the venue wifi.
2. Open `/column` on every column screen and LED processor, and
   `/display?mode=hd` on any TV, projector or laptop. Click once on each — that
   goes fullscreen and enables the countdown sound.
3. Open `/admin` on your own machine and enter the passkey.

Every screen must be on the same network as the server.

**Restart the server after an update** — it holds the screen shape, so the admin
card cannot change it until you do. The displays are right either way. Restarting
also puts the timer back to its defaults, so do it before the event rather than
during it.

**If a display looks stale, prove it.** `?debug` prints the build stamp of the
page that is actually running and whether it is talking to a server that knows
about screen shape. An LED media server's embedded browser caches harder than a
normal one — remove and re-add the webpage layer, or point it at
`/display?v=2`, to be certain it has fetched the current file.

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
| First place | `coloum-screen(winners)-01.jpg` |
| Second place | `coloum-screen(winners)-02.jpg` |
| Third place | `coloum-screen(winners)-03.jpg` |

The three winners screens carry no countdown — they are artwork, picked like any
other screen, and the clock keeps running behind them untouched.

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

## The layouts

### `/column` — the URL for the column screens

```
http://<server>:3000/column
```

Point every column screen and every LED processor at this. It forces the column
layout, filling the frame, and **nothing overrides it** — not `?mode=hd`, not
`?fit=`, not the admin page's screen-shape settings. There is nothing left to
negotiate and nothing to get wrong.

It is deliberately a different path from `/display`, which matters twice over.
A media server's embedded browser cannot be holding a cached copy of a path it
has never fetched, so pointing a layer at `/column` forces a fresh page. And on
a server that has not been restarted since the update, `/column` returns 404
rather than quietly serving a stale page — so it tells you which of the two
problems you have.

`/display` is the same page with everything still negotiable, described below.

## What each layout is

A display shows the **column** layout — the artwork exactly as designed — unless
it is told otherwise. The other one is the **HD** layout, which takes the column
apart and re-composes it for 16:9: the wordmark, the phase headline and the
strapline down one side, the clock across the other. A TV, a projector or a
laptop gets it with **`?mode=hd`** — the admin page's *Copy HD link* button.

It does not guess. A browser can measure the frame it was handed but has no way
to see the wall that frame ends up on, and every screen this is built for is a
column fed through an LED processor — which from inside the browser looks exactly
like an ordinary laptop. Guessing from the frame put the landscape composition on
a column wall, so the column is now simply the default and the landscape layout
is asked for by name.

The column artwork is 1:4.5 — a 0.60 × 2.70 m panel exactly.

### Screen shape, from the admin page

A browser can measure the frame it was handed but never the wall that frame ends
up on. So the shape of the screen is something only you know, and the **Screen
shape** card on the admin page is where you say it — width and height in any
unit (only the ratio is read), and whether to stretch to fill the frame. It
lands on every display at once, live, like every other control.

It starts at **0.60 × 2.70 m, stretch on**, which is the artwork's own shape —
and a display that cannot reach those settings assumes exactly the same thing.
Leave it alone and the column screens are right without a single URL parameter,
whatever canvas the media server renders them at.

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

Add **`?debug`** (or press `D` on the display) for a readout of the build stamp,
the frame size the browser was actually given, the ratio it works out to, the
screen shape in force and which layout it picked — with centre lines and a border
showing the frame's true edges. That is usually enough to tell a media-server
canvas problem from a page problem, and to catch a display running a cached copy
of an older page.

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
5. swaps the designed partner lockup for the current one,
6. writes it all to `public/screens/` with a `manifest.json`.

The browser then redraws the digits as SVG in the same seven-segment face,
measured off the artwork: a 350 × 612 cell, an 88-unit stroke, ends mitred at
45°, and the cell's own corner chamfer where a segment meets it. Positioned from
the manifest, live digits land exactly where the designed ones were.

It also does two things the artwork does not:

**A row per unit.** The design has two blocks — hours and minutes — and the
challenge screens run three: hours, minutes, seconds (the presentation screens
run minutes and seconds). A third row needs more height than the design left, so
the whole stack is scaled about its top until the last unit word clears whatever
the artwork draws underneath it, measured off the plate itself. Because every row
moves, the designed unit words can no longer be left where they are: each is
covered with a patch of its own background and all of them are re-drawn beside
the rows they now belong to.

**The strategic-partner row.** The design put PIF and the partners either side of
one strip across the top, and the partners have changed since it was signed off.
`Assets/logos2-04.png` is the current row — Site, Digital Saudi, Tuwaiq Academy,
HUMAIN under their Arabic and English heading. The designed lockup is lifted off
the top, leaving PIF that strip to itself, and the new row is set across the foot
of the column, where it gets the full width and ends up larger than it was.

It sits at the same height on every screen: the winners artwork runs far lower
than the rest, and a row that shifted as the screens changed would read as a
wobble on the wall. `PARTNER_WIDTH` and `PARTNER_BOTTOM` in `tools/prepare.py`
are its size and its margin from the foot; the row gives way and shrinks only if
a screen ever draws far enough down to touch it, and says so when it does. Drop a
new file in under that name and re-run to change the partners again.

Re-run `python3 tools/prepare.py` whenever anything in `Assets/` changes. Each
run stamps the manifest with a build id that every artwork URL carries, so the
new plates reach the screens immediately — without it they would sit on the
previous ones for a day, and a media server's embedded browser would never look
again at all.

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
