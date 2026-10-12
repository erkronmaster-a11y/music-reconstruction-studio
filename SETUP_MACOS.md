# Setup on macOS — Sprint 0

You are Claude's hands on the Mac for this sprint. Each step below takes a
few minutes, and nothing in it changes your system or your Ableton settings.

## 1. Get the project onto the Mac (once)

1. Open **GitHub Desktop**.
2. Go to **File → Clone Repository…**, pick `music-reconstruction-studio`, and
   clone it into `~/Documents/GitHub`.

## 2. Check the Mac (about 1 minute)

1. In Finder, open `music-reconstruction-studio/mac/`.
2. Double-click **`1-check-mac.command`**.
   - If macOS says it "cannot be opened": **right-click → Open → Open**.
     macOS asks this once per script.
3. A Terminal window lists your macOS version, processor, Ableton, Max and
   tools, then sends the report to GitHub.
   - If the push fails, it says so. Open GitHub Desktop and click
     **Push origin**.

## 3. The Ableton test (about 5 minutes)

1. Open **Ableton Live 12** and choose **File → New Live Set**.
2. In Finder, open `music-reconstruction-studio/live/` and drag
   **`MRS Bridge.amxd`** onto a **MIDI track** in Live.
3. Click **`run`** in the device.
   - The device's status line should read `create: … (saved)`.
   - Live should now have two new tracks. One is a MIDI track with a 4-note
     clip at bar 2, the other an audio track with a tone at bar 2. The tempo
     should now be 117.5.
4. Choose **File → Save Live Set As…** and save it to your **Music** folder
   (*not* inside the project folder). Name it `MRS-Sprint0-Test`.
5. **Quit Live completely** (⌘Q). Open Live again, then open
   `MRS-Sprint0-Test`.
6. Click **`verify`** in the device. Its status line should read
   `verify_after_reopen: …`.
7. In Finder, double-click **`mac/2-send-live-results.command`**.
8. Tell Claude **"results pushed"**, and add anything odd you saw or heard.

> If something fails, that is a valid result. Don't fix it: send the results
> anyway. Claude reads exactly which step failed.

## 4. Sprint 1a — install + test + Traktor scan (≈10 min, mostly downloading)

1. In GitHub Desktop: **Fetch origin** → **Pull origin**.
2. Double-click **`mac/3-install.command`**.
   - It installs `uv` and a current `ffmpeg` with Homebrew, builds the Python
     environment and runs all the tests on your Mac.
   - It tries Basic Pitch.
   - It looks for Traktor stem files. It only reads; it never moves, changes
     or uploads anything.
3. When it says "Sent to GitHub", tell Claude **"install pushed"**.

## 5. Analyse a song (≈1 min per song)

1. Double-click **`mac/4-analyze-song.command`**.
2. Drag a **song folder** (the full mix plus stems) **or a Traktor `.stem.mp4`
   file** into the window, then press Enter.
   - In a folder, the mix's file name must contain `mix`, `master` or `full`.
3. A click track plays over your song: a high click marks each bar start, a
   low click each beat. Tell Claude whether the high click lands on "the one".
4. Results go to `~/Music/MRS Projects/<song>/`. Only a short text summary is
   sent to GitHub, never your audio.

## Fallback: build the device by hand (if Live won't load the .amxd)

This takes about 2 minutes, and only needs doing if step 3.2 fails, or if
Max's console says `js: can't find mrs_bridge.js`.

1. In Live's browser, choose **Max for Live → Max MIDI Effect** and drag it
   onto a MIDI track.
2. Click the device's **edit** button (the small pencil/window icon). Max opens.
3. In the Max window, click on an empty area and press **N**, then type
   `js mrs_bridge.js` and press Enter.
4. Press **M** and type `run`. Press **M** again and type `verify`.
5. Connect the bottom-left outlet of `run` and of `verify` to the left inlet
   of `js mrs_bridge.js`.
6. Press **M** for one more empty box and connect the `js` outlet to it. This
   box becomes the status line.
7. Choose **File → Save As…**, go to the project's **`live/`** folder, and
   save as `MRS Bridge (hand).amxd`.
   - The folder matters: the device finds the script and the reports folder
     from where it is saved.
8. Close Max and continue from step 3.3 above.
