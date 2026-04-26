# Stem Hand Controller with Auto Stem Splitting

This version adds a song upload button.

The app flow is:

1. Open the web app.
2. Upload a song file.
3. The Python server runs Demucs.
4. Demucs splits the song into:
   - vocals.wav
   - drums.wav
   - bass.wav
   - other.wav
5. The web app loads those stems.
6. Hand tracking controls the stems.
7. TouchDesigner receives the control values over UDP port 7000.

## Install

Open this folder in a terminal and run:

```bash
pip install -r requirements.txt
```

Or:

```bash
pip install flask demucs torchcodec
```

### Windows requirement for Demucs audio decoding

If you see an error about `torchcodec` or `Could not load libtorchcodec`, install shared FFmpeg DLLs:

```powershell
winget install --id Gyan.FFmpeg.Shared --exact --accept-package-agreements --accept-source-agreements
```

Then restart your terminal (or VS Code) so PATH updates take effect.

## Run

```bash
python server.py
```

Open:

```text
http://localhost:5050
```

## How to use

1. Click Choose File
2. Select a song, like an mp3 or wav
3. Click Upload + Auto Split
4. Wait until it says the split is finished
5. Click Play / Resume
6. Click Start Hand Tracking

## TouchDesigner

In TouchDesigner:

1. Create a UDP In DAT
2. Set the port to 7000
3. Turn Active On
4. Create a Constant CHOP named `controls`
5. Create a DAT Execute DAT watching the UDP In DAT
6. Paste the code from `touchdesigner_dat_execute.py`

## Important hackathon note

Auto splitting is not instant. It can take a few minutes, especially the first time, because Demucs may need to download model files.

For the cleanest demo, upload and split your song before judging starts, then use the hand tracking live during the demo.
