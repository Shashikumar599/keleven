# Fun UX ideas for the web app

A wish list of playful features for the demo. Not scheduled; picked up when the core app is stable.

## 1. The dodging video cutout

**Idea:** a small cut-out video of me (no background) floats in a corner of the page. When someone moves the cursor
close to it, it jumps away: to another corner at random, or sometimes to the center.

**Two videos:**
- **Reaction:** me reacting normally to Office memes (the default, while nobody chases it).
- **Intimidating:** me staring the user down, making clear they cannot click me (plays while it's being chased).

**Implementation notes:**
- **Cut-out video:** needs a transparent background. WebM (VP9) with an alpha channel works in Chrome and Firefox;
  Safari needs HEVC with alpha (`.mov`). Alternative: record on a green screen and remove it in the browser with a
  `<canvas>` (chroma key), one source for all browsers.
- **Playback:** `<video autoplay muted loop playsinline>`. Browsers only autoplay muted video; sound needs a click.
- **Dodging:** on `mousemove`, measure the distance from the cursor to the video's center; within a threshold
  (e.g. 120 px), pick a new position (another corner, or the center now and then) and move there with a CSS
  `transform` transition. Switch to the intimidating video while it's being chased, back to the reaction video
  after a few calm seconds.
- **Touch screens** have no cursor: trigger the dodge on tap near it instead.
- **Accessibility:** respect `prefers-reduced-motion` (jump without animation, or stay still), never cover the
  question box or answers, and give keyboard users a way to hide it (e.g. a setting or a key).
- **Size:** keep the videos short and small (a few MB) so the page stays fast.

## 2. Theme music when the site opens (built 2026-10-04)

**Idea:** an Office theme remix plays when the page opens
(source: https://www.101soundboards.com/sounds/712358-the-office-remix-ringtone, downloaded manually to
`app/static/audio/office-theme.mp3`).

**How it works:**
- Browsers block audio with sound until the visitor interacts with the page. The page tries to play on load; if
  the browser refuses, it plays on the first click, tap or key press.
- Plays once per page open, at moderate volume. A small mute button in the corner turns it off, and the choice is
  remembered in the browser.
- If the file is missing, the page stays silent and hides the button.

**Licensing:** the track is based on the show's copyrighted theme. Fine for the local app; keep the file out of the
repo (`app/static/audio/` git-ignored) and replace it with a licensed or original track, or leave it out, for the
public demo.

## 3. Random Office sound bites (later)

**Idea:** after a random pause of 30-60 seconds, play a short Office sound bite (catchphrases, jokes), sourced from
the same soundboard site. Then wait another random 30-60 s.

**Notes for later:** only after the visitor has interacted (same browser rule); obey the same mute button; never
play while an answer is loading or being read? (decide); keep a list of files in `app/static/audio/bites/`;
licensing as above.

## 4. Dwight backdrop (built 2026-10-04)

`app/static/image/dwight.png` as a fixed, very faint background (7% opacity in light mode, 5% in dark, partly
desaturated). Reading areas keep opaque panels, so the image only shows in the gaps and never behind text; it
doesn't scroll and ignores the mouse. Licensing as for the music: a still from the show, fine locally, keep it
out of the repo and rethink for the public demo.

## 5. Quote of the minute (built 2026-10-04)

A quote card (avatar, quote, character) in the idle view and while answers load; a new random quote every 30 s
(was 60 s; the longest quote, 45 words, reads in about 16 s),
paused while the tab is hidden, no repeats among the last 30. Quotes up to 220 characters only (3 lines max).
- **Quotes:** the 326 offline quotes from `gumadeiras/office-quotes-cli` (`data/quotes.json`, MIT; license copied to
  `app/static/quotes/LICENSE-office-quotes-cli.txt`), saved as `app/static/quotes/quotes.json`. 13 characters.
- **Avatars:** the 10 character images referenced by `AkashRajpurohit/the-office-api` (MIT code; the images are
  hotlinked third-party pictures of the show), downloaded once and resized to 160 px JPEGs in
  `app/static/image/avatars/` (~80 KB total); mapping in `app/static/quotes/avatars.json`. Oscar, Phyllis and Ryan
  have no avatar and show initials.
- Rejected: `zubyj/the-office-api` (full script, duplicates our data, hosted site down) and calling the Akash API
  live (rate-limited by Cloudflare at ~45 quick requests). Akash's `data/episodes.json` (air dates, IMDb ratings,
  directors, writers) is saved in `data/raw/` for later episode metadata.
- Licensing: quote text and avatars are from the show; fine locally, keep the images out of the public repo.
