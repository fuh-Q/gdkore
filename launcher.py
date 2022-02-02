import os
import psutil
import subprocess
import sys

import re

bot_to_launch = 0

def generate_kwargs() -> dict[str, str]:
    """
    Creating a new instance of `subprocess.Popen` requires
    different arguments to be passed through on Windows and Linux,
    so this function returns the correct arguments based on your system
    """
    
    bot_map = {
        1: "bot.py",
        2: "rickroll_bot.py",
        3: "hc_bot.py",
    }
    
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
    LINE = "==========================="
    
    print("\n".join([
        LINE,
        "Welcome to the launcher",
        LINE,
    ]))
    
    process_map = {
        "bot.py": False,
        "rickroll_bot.py": False,
        "hc_bot.py": False,
    }
    
    processes = list(psutil.process_iter())
    proc_cmd_regex = re.compile(r"py(?:thon3\.9)? ((?:hc_|rickroll_)?bot\.py)")
    access_denied = []
    for process in processes:
        try:
            proc_cmd = " ".join(process.cmdline())
        except psutil.AccessDenied:
            access_denied.append(process)
            continue
        else:
            if match := proc_cmd_regex.search(proc_cmd):
                process_map[match[1]] = True
    
    bots = "\n".join([
        "0. Exit Launcher",
        "",
        f"1. Not GDKID {'-- RUNNING' if process_map['bot.py'] else ''}",
        f"2. Rickroll Bot {'-- RUNNING' if process_map['rickroll_bot.py'] else ''}",
        f"3. HC Utility {'-- RUNNING' if process_map['hc_bot.py'] else ''}"
    ])
    
    print("Bots you can launch:", end="\n\n")
    print(bots, end="\n\n")


def main():
    global bot_to_launch
    
    print_intro()
    while True:
        user_input = input("Which bot would you like to launch? [0|1|2|3]\n>>> ")
        
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
            break
    
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
