import os
import platform
import sys
from pathlib import Path

if sys.platform != "linux":
    raise OSError("what no not here")

version_tuple = platform.python_version_tuple()[:2]
plat = "cp" + "".join(version_tuple)

machine = platform.machine()
match machine:
    case "x86_64" | "aarch64" | "armv7" | "s390x" | "ppc64le":
        mlinux = ("2_17", "2014")
    case "i686":
        mlinux = ("2_12", "2010")
    case _:
        raise ValueError("idk what %s is supposed to be" % machine)

if len(sys.argv) < 2:
    ver = "0.1.0"
else:
    ver = sys.argv[1]

asset_name = f"maze-{ver}-{plat}-{plat}-manylinux_{mlinux[0]}_{machine}.manylinux{mlinux[1]}_{machine}.whl"
url = f"https://github.com/fuh-Q/maze/releases/download/maze/{asset_name}"

cwd = Path.cwd()
py = ".".join(version_tuple)
interpreter = cwd / "venv" / "bin" / f"python{py}"
os.system(f"{interpreter} -m pip install -U pip {url}")

print(f"successfully installed to the venv found in this current directory ({cwd})")
