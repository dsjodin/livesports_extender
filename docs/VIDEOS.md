# Team videos: how to make your own

The wall plays three kinds of short, silent videos per team (behaviour in
`docs/SCREENS.md`, Team videos). The service ships generated defaults
(`tools/make_stingers.py`); a file of your own with the right name replaces the default
for that team.

| Kind | Where it plays | When | Size | Default length |
|---|---|---|---|---|
| `goal` | the scoring team's portrait screen (left = home, right = away) | at the goal's `play_at`, as the goal scene starts | 1080×1920 | 2.2 s |
| `intro` | both portrait screens, each its own team | once per game: the scheduled start on TV time, or else at puck drop | 1080×1920 | 4.5 s |
| `pp` | the bar | when **my team's** power play begins | 1920×360 | 4.0 s |

## The format

| Property | Value |
|---|---|
| Container | WebM (`.webm`). Other containers are not served. |
| Video codec | **VP9** with an alpha channel. VP8 with alpha also plays. AV1 and H.264 cannot carry alpha in Chromium. |
| Pixel format | `yuva420p` (8-bit 4:2:0 plus a full-resolution alpha plane), alpha **straight** (unmatted), not premultiplied |
| Resolution | exactly **1080×1920** (portrait, 9:16) or **1920×360** (bar, 16:3). Other sizes are scaled to fit and leave transparent bars. |
| Pixel aspect | square (1:1). The real screens are square too: portrait 299×531 mm (3.6 px/mm), bar 700×132 mm (2.7 px/mm). |
| Frame rate | 30 fps (the defaults). 60 fps works too; there is nothing to gain above 60 (the screens run at 60 Hz). |
| Colour | sRGB / BT.709, 8-bit. Design on a dark background: the screens are near black (`#070A10`). |
| Audio | none. Videos play muted; Home Assistant plays the horn and sound (decided 2026-10-21). Strip any audio track (`-an`). |
| Bitrate | constant quality (`-crf 30–36 -b:v 0`). The defaults are 0.4–1 Mbit/s, 200–700 kB per file. |
| File size | keep it under about 3 MB. Each screen fetches its videos into memory when the page loads. |
| Length | `goal` 1.5–3 s, `intro` up to 6 s, `pp` up to 5 s. Longer hides the graphics underneath for longer. |

## How a video plays

- Frame 0 is shown at `play_at` on the synced clock, the same moment the TV shows the
  goal (or the power play, or the drop). A screen that is late jumps that far into the
  video; one that is later than the whole video shows none. Do not put the key moment
  in the first 100 ms.
- The video plays **over** the scene. The goal scene's graphics build underneath it
  during the first 2 s, and the gold goal band sweeps across above it. Wherever the
  video is transparent the scene shows through.
- When the video ends it is hidden at once. **End on a fully transparent frame** (sweep
  or fade out). An opaque last frame vanishes with a hard cut.
- An opaque video (no alpha) works, but it covers the whole screen until it ends.
- Text in a video should follow the 3 m rule (`docs/SCREENS.md`, Type): at least 11 mm
  cap height, which is about 40 px of cap height (a 55 px font) on a portrait screen and
  30 px (a 42 px font) on the bar.

## Making one

Export from your editor with alpha, not as H.264:

- **After Effects / Premiere:** QuickTime, codec Apple ProRes 4444 (or Animation), channels
  RGB + Alpha, alpha **Straight (Unmatted)**. Or a PNG sequence with alpha.
- **DaVinci Resolve:** QuickTime ProRes 4444 with "Export Alpha", or a PNG/TIFF sequence.
- **Blender:** PNG, RGBA, Film > Transparent on.

Then encode with ffmpeg (needs `libvpx-vp9`, check with `ffmpeg -encoders | grep vp9`):

```
# from a ProRes 4444 / Animation .mov with alpha
ffmpeg -i in.mov -an -r 30 -c:v libvpx-vp9 -pix_fmt yuva420p \
  -b:v 0 -crf 32 -auto-alt-ref 0 -row-mt 1 -deadline good -cpu-used 1 out.webm

# from a PNG sequence (frame0000.png, frame0001.png, ...)
ffmpeg -framerate 30 -i frame%04d.png -c:v libvpx-vp9 -pix_fmt yuva420p \
  -b:v 0 -crf 32 -auto-alt-ref 0 -row-mt 1 out.webm

# a source of another size: fit it into 1080x1920 with transparent padding, cut at 2.5 s
ffmpeg -i in.mov -an -t 2.5 -r 30 \
  -vf "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=0x00000000,format=yuva420p" \
  -c:v libvpx-vp9 -pix_fmt yuva420p -b:v 0 -crf 32 -auto-alt-ref 0 -row-mt 1 out.webm
```

- `-crf`: lower is better and larger. 30–36 is the useful range; the defaults use 36.
- `-auto-alt-ref 0` keeps libvpx from using alt-ref frames, which older libvpx versions
  cannot combine with alpha. Leave it in.
- `-pix_fmt yuva420p` is what carries the alpha. Without it the result is opaque.

Check the result:

```
ffprobe -v error -show_entries stream=codec_name,width,height,r_frame_rate:stream_tags=alpha_mode:format=duration,size out.webm
# expect codec_name=vp9, the right width/height, TAG:alpha_mode=1

# look at one frame with its transparency (force the libvpx decoder: ffmpeg's own VP9
# decoder drops the alpha plane, and ffprobe's pix_fmt says yuv420p for the same reason)
ffmpeg -c:v libvpx-vp9 -i out.webm -vf "select=eq(n\,30)" -frames:v 1 frame30.png
```

## Installing

On the Docker host, put the file in `data/media/<kind>/<team uuid>.webm` (that is
`./data/media/...` next to `compose.yaml`):

```
data/media/goal/82eb-82ebmgaJ8.webm     # Örebro's goal stinger
data/media/intro/82eb-82ebmgaJ8.webm    # Örebro's intro
data/media/pp/82eb-82ebmgaJ8.webm       # Örebro's power-play video on the bar
```

No restart is needed. The screens fetch the videos when the page loads, revalidating
every time (`Cache-Control: no-cache`). Reload them (restart the kiosk on the display
box, or reload `/sim`) to pick up a new file. Delete your file to go back to the default.

Test it in `/sim`: "Goal video home/away", "Intro (both)" and "PP video (my team)" play the
video alone; "Test goal home/away" runs the whole goal sequence. With "Debug overlay on
screens" on, each screen shows whether it holds its videos (`video goal ready · intro ready`).

Team uuids (`config/teams.json`):

| Team | uuid |
|---|---|
| Björklöven | `4519-4519Rdei6` |
| Brynäs IF | `1ab8-1ab8bfj7N` |
| Djurgårdens IF | `2459-2459QTs1f` |
| Frölunda HC | `087a-087aTQv9u` |
| Färjestad BK | `752c-752c12zB7Z` |
| HV71 | `3db0-3db09jXTE` |
| Linköping HC | `41c4-41c4BiYZU` |
| Luleå Hockey | `1a71-1a71gTHKh` |
| Malmö Redhawks | `8e6f-8e6fUXJvi` |
| Rögle BK | `ee93-ee93uy4oW` |
| Skellefteå AIK | `50e6-50e6DYeWM` |
| Timrå IK | `31d1-31d1NbSlR` |
| Växjö Lakers | `fe02-fe02mf1FN` |
| Örebro Hockey | `82eb-82ebmgaJ8` |

## The defaults

`tools/make_stingers.py` draws every frame in Chromium on a transparent page (a GSAP
timeline in `tools/stinger.html`, seeked frame by frame, so the result does not depend on
the machine's speed) with the team's colours from `config/teams.json` and its logo from
the logo cache, and encodes the frames with the ffmpeg command above (`-crf 36`). They
live in `web/media/<kind>/` and ship with the image. Make them again after changing team
colours:

```
uv run --project server python tools/make_stingers.py                      # all
uv run --project server python tools/make_stingers.py --kind pp --team 82eb-82ebmgaJ8
```
