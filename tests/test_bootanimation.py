import subprocess, sys, zipfile, io
from pathlib import Path
from PIL import Image

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "make_bootanimation.py"

def test_generates_valid_bootanimation(tmp_path):
    out = tmp_path / "bootanimation.zip"
    subprocess.run([sys.executable, str(SCRIPT), str(out), "--text", "Google TV"], check=True)
    with zipfile.ZipFile(out) as z:
        names = z.namelist()
        assert names[0] == "desc.txt"
        assert z.read("desc.txt").decode().splitlines() == ["1920 1080 30", "p 1 0 part0", "p 0 0 part1"]
        assert all(i.compress_type == zipfile.ZIP_STORED for i in z.infolist())
        assert len([n for n in names if n.startswith("part0/")]) == 30
        assert len([n for n in names if n.startswith("part1/")]) == 60
        img = Image.open(io.BytesIO(z.read("part1/0000.png")))
        assert img.size == (1920, 1080)
