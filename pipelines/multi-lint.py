"""
This file is part of Showtimes Backend Project.
Copyright 2022-present naoTimes Project <https://github.com/naoTimesdev/showtimes>.

Showtimes is free software: you can redistribute it and/or modify it under the terms of the
Affero GNU General Public License as published by the Free Software Foundation, either
version 3 of the License, or (at your option) any later version.

Showtimes is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
See the Affero GNU General Public License for more details.

You should have received a copy of the Affero GNU General Public License along with Showtimes.
If not, see <https://www.gnu.org/licenses/>.
"""

import subprocess as sp
import sys
from pathlib import Path
from typing import Optional

to_be_linted = ["showtimes"]


def check_license_header(file: Path) -> bool:
    # Find the MIT License header on file that's not __init__.py
    with file.open("r") as fp:
        # Check until line 10
        for idx, line in enumerate(fp):
            if idx == 10:
                break
            if file.name == "__init__.py":
                if line.startswith(":copyright:") or line.startswith(":license:"):
                    return True
                return True
            else:
                if line.startswith("This file is part of Showtimes"):
                    return True
    return False


def missing_init_check(folder: Path):
    filenames = [file.name for file in folder.iterdir()]
    if len(filenames) < 1:
        # Ignore empty folder
        return False
    return "__init__.py" not in filenames


current_path = Path(__file__).absolute().parent.parent  # root dir
venv_dir = [
    current_path / ".venv",
    current_path / "venv",
    current_path / "env",
]
selected_venv_dir: Optional[Path] = None
for venv in venv_dir:
    if venv.exists():
        selected_venv_dir = venv

if selected_venv_dir is None:
    raise RuntimeError("No virtual environment found")


script_path = selected_venv_dir / "Scripts" if sys.platform == "win32" else selected_venv_dir / "bin"

print(f"[*] Running tests at {current_path}")

print("[*] Running isort test...")
isort_res = sp.Popen(
    [script_path / "isort", "-c", *to_be_linted],
).wait()
print("[*] Running ruff test...")
ruff_res = sp.Popen([script_path / "ruff", "check", "--statistics", "--show-fixes", *to_be_linted]).wait()
print("[*] Running black test...")
black_res = sp.Popen([script_path / "black", "--check", *to_be_linted]).wait()

results = [(isort_res, "isort"), (ruff_res, "ruff"), (black_res, "black")]
any_error = False

for res in results:
    if res[0] != 0:
        print(f"[-] {res[1]} returned an non-zero code")
        any_error = True
    else:
        print(f"[+] {res[1]} passed")


print("[*] Running license check test...")
any_license_error = False
folder_to_check: list[Path] = []
for folder in to_be_linted:
    if folder.endswith(".py"):
        files = [current_path / folder]
    else:
        files = (current_path / folder).glob("**/*.py")
    for file in files:
        parent = file.parent
        if parent not in folder_to_check:
            folder_to_check.append(parent)
        if not check_license_header(file):
            print(f"[?] {file} is missing license header")
            any_license_error = True
            any_error = True

print("[*] Running missing __init__.py check...")
any_missing_init_error = False
for folder in folder_to_check:
    if missing_init_check(folder):
        print(f"[?] {folder} is missing __init__.py")
        any_missing_init_error = True
        any_error = True

if any_license_error:
    print("[-] Please add the license header on the files above")
else:
    print("[+] License header check passed")
if any_missing_init_error:
    print("[-] Please add __init__.py on the folders above")
else:
    print("[+] Missing __init__.py check passed")

if any_error or any_license_error or any_missing_init_error:
    print("[-] Test finished, but some tests failed")
    exit(1)
print("[+] All tests passed")
exit(0)
