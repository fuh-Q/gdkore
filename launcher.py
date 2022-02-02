import os
import re
import subprocess
import sys

import psutil

LINE = "==========================="
bot_to_launch = 0
process_map = {
    "bot.py": False,
    "rickroll_bot.py": False,
    "hc_bot.py": False,
}

bot_map = {
    1: "bot.py",
    2: "rickroll_bot.py",
    3: "hc_bot.py",
}


def generate_kwargs() -> dict[str, str]:
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
            "args": f"python3.9 {bot_map[bot_to_launch]}",
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

    processes = list(psutil.process_iter())
    proc_cmd_regex = re.compile(r"py(?:thon3\.9)? ((?:hc_|rickroll_)?bot\.py)")
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
            "0. Exit Launcher",
            "",
            f"1. Not GDKID {'-- RUNNING' if process_map['bot.py'] else ''}",
            f"2. Rickroll Bot {'-- RUNNING' if process_map['rickroll_bot.py'] else ''}",
            f"3. HC Utility {'-- RUNNING' if process_map['hc_bot.py'] else ''}",
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
                print(
                    f"{bot_map[user_input][:-3]} is already running - Start bot regardless? [y|n]"
                )
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
