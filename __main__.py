import os
import re
import subprocess
import sys

import psutil

from utils import PrintColours

G = PrintColours.GREEN
R = PrintColours.RED
W = PrintColours.WHITE

LINE = f"{G}==========================={W}"
bot_to_launch = 0
process_map = {
    "bot.py": False,
    "helper_bot.py": False,
    "rickroll_bot.py": False,
}

bot_map = {
    1: "bot.py",
    2: "helper_bot.py",
    3: "rickroll_bot.py",
}

v = sys.version_info
version = f"{v.major}.{v.minor}"


def generate_kwargs() -> dict[str, str | bool | int]:
    """
    Creating a new instance of `subprocess.Popen` requires
    different arguments to be passed through on Windows and Linux,
    so this function returns the correct arguments based on your system
    """

    if sys.platform == "win32":
        return {
            "args": f"py {bot_map[bot_to_launch]}",
            "shell": True,
            "creationflags": subprocess.CREATE_NEW_PROCESS_GROUP,
        }

    else:
        return {
            "args": f"python{version} {bot_map[bot_to_launch]}",
            "shell": True,
        }


def print_intro() -> None:
    print(
        "\n".join(
            [
                LINE,
                "Welcome to the launcher",
                LINE,
            ]
        )
    )

    processes = psutil.process_iter()
    proc_cmd_regex = re.compile(rf"py(?:thon{v.major}\.{v.minor})? ((?:rickroll_|helper_)?bot\.py)")
    for process in processes:
        try:
            proc_cmd = " ".join(process.cmdline())
        except psutil.AccessDenied:
            continue
        else:
            if match := proc_cmd_regex.search(proc_cmd):
                process_map[match[1]] = True

    bots = "\n".join(
        [
            f"{G}0.{W} Exit Launcher",
            "",
            f"{G}1.{W} GClass {R + '-- RUNNING' + W if process_map['bot.py'] else ''}",
            f"{G}2.{W} Helper Bot {R + '-- RUNNING' + W if process_map['helper_bot.py'] else ''}",
            f"{G}3.{W} Rickroll Bot {R + '-- RUNNING' + W if process_map['rickroll_bot.py'] else ''}",
        ]
    )

    print("Bots you can launch:", end="\n\n")
    print(bots, end="\n\n")
    print("Which bot would you like to launch? [0|1|2|3]")
    print(LINE)


def prompt():
    global bot_to_launch
    ask = ">>> "

    while True:
        user_input = input(ask)

        try:
            user_input = int(user_input)
            if user_input == 0:
                exit()

            if not user_input in [1, 2, 3]:
                raise TypeError

        except (ValueError, TypeError):
            print("Please enter either 0, 1, 2, or 3!")
            continue

        else:
            bot_to_launch = user_input
            if process_map[list(process_map)[user_input - 1]] is True:
                print("")
                print(f"{G + bot_map[user_input][:-3] + W} is already running - Start bot regardless? [y|n]")
                confirm = input(ask)

                if confirm.lower() in ["y", "yes", "true"]:
                    break

                else:
                    print("")
                    print("Which bot would you like to launch? [0|1|2|3]")
                    print(LINE)
                    continue

            break


def main():
    print_intro()
    prompt()

    while True:
        os.system("cls" if sys.platform == "win32" else "clear")  # Makes things look nicer

        proc = subprocess.Popen(**generate_kwargs())  # type: ignore

        code = proc.wait()
        proc.kill()  # Just in case

        if code != 69:
            break


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass  # shut up python
