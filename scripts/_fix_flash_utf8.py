import pathlib
import subprocess

raw = subprocess.check_output(
    ["git", "show", "62690cb:templates/includes/flash_messages.html"],
    cwd=pathlib.Path(__file__).resolve().parent,
)
# git show may return UTF-16 if commit had it; decode safely
if raw.startswith(b"\xff\xfe"):
    text = raw.decode("utf-16")
elif raw.startswith(b"\xfe\xff"):
    text = raw.decode("utf-16-be")
else:
    text = raw.decode("utf-8")

out = pathlib.Path(__file__).resolve().parent / "templates/includes/flash_messages.html"
out.write_bytes(text.encode("utf-8"))
print(out.read_bytes()[:4].hex())
