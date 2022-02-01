import os
import subprocess
import sys


def generate_kwargs() -> dict[str, str]:
    """
    Creating a new instance of `subprocess.Popen` requires
    different arguments to be passed through on Windows and Linux,
    so this function returns the correct arguments based on your system
    """
    if sys.platform == "win32":
        return {
            "args": "py bot.py",
            "shell": True,
            "creationflags": subprocess.CREATE_NEW_PROCESS_GROUP,
        }

    else:
        return {
            "args": "python3.9 bot.py",
            "shell": True,
        }


def main():
    while True:
        proc = subprocess.Popen(**generate_kwargs())

        code = proc.wait()
        proc.kill()  # Just in case

        os.system(
            "cls" if sys.platform == "win32" else "clear"
        )  # Makes things look nicer

        if code != 69:
            break


if __name__ == "__main__":
    main()
