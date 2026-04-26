import sys
import subprocess
from pathlib import Path
import shutil

def main():
    if len(sys.argv) < 2:
        print("Usage: python split_stems.py your_song.mp3")
        return

    song = Path(sys.argv[1])

    if not song.exists():
        print(f"Could not find file: {song}")
        return

    print("Splitting song into stems using Demucs...")
    print("This can take a few minutes the first time.")

    command = [
        sys.executable,
        "-m",
        "demucs",
        "-n",
        "htdemucs",
        "--out",
        "separated",
        str(song)
    ]

    subprocess.run(command, check=True)

    output_root = Path("separated") / "htdemucs" / song.stem
    stems_folder = Path("stems")
    stems_folder.mkdir(exist_ok=True)

    expected = ["vocals.wav", "drums.wav", "bass.wav", "other.wav"]

    for filename in expected:
        source = output_root / filename
        destination = stems_folder / filename

        if source.exists():
            shutil.copy(source, destination)
            print(f"Copied {filename} to stems folder.")
        else:
            print(f"Missing expected stem: {filename}")

    print()
    print("Done. Now run:")
    print("python server.py")

if __name__ == "__main__":
    main()
