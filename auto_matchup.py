import subprocess
import re
import os
import sys
from dotenv import load_dotenv
from data_parser import get_matchup

load_dotenv()


def generate_matchup_pcsp(pitcher, batter):
    matchup = get_matchup(pitcher, batter)

    with open("baseball_template.pcsp", "r") as f:
        content = f.read()

    for key, val in matchup.items():
        content = content.replace(f"{{{{{key}}}}}", str(val))

    with open("matchup.pcsp", "w") as f:
        f.write(content)

    print(
        f"Updated matchup.pcsp with real probabilities for "
        f"{pitcher} vs {batter}!"
    )


def run_pat_model():
    print("Running PAT...")

    PROJECT_DIR = os.getenv("PROJECT_DIR")
    PAT_EXE = os.getenv("PAT_EXE")

    if not PROJECT_DIR or not PAT_EXE:
        raise Exception("Please set PROJECT_DIR and PAT_EXE in your .env file")

    import platform
    system = platform.system()

    PROJECT_DIR = os.getenv("PROJECT_DIR")
    PAT_EXE = os.getenv("PAT_EXE")

    if not PROJECT_DIR or not PAT_EXE:
        raise Exception("Please set PROJECT_DIR and PAT_EXE in your .env file")

    if system == "Windows":
        # Convert Windows path to WSL path
        def to_wsl_path(win_path):
            return (
                "/mnt/" +
                win_path.replace("\\", "/")
                .replace(":", "")
                .lower()
            )

        command = [
            "wsl",
            "mono",
            to_wsl_path(PAT_EXE),
            "-pcsp",
            to_wsl_path(os.path.join(PROJECT_DIR, "matchup.pcsp")),
            to_wsl_path(os.path.join(PROJECT_DIR, "matchup_output.txt"))
        ]

    elif system == "Darwin":  # macOS
        command = [
            "mono",
            PAT_EXE,
            "-pcsp",
            os.path.join(PROJECT_DIR, "matchup.pcsp"),
            os.path.join(PROJECT_DIR, "matchup_output.txt")
        ]

    else:  # Linux
        command = [
            "mono",
            PAT_EXE,
            "-pcsp",
            os.path.join(PROJECT_DIR, "matchup.pcsp"),
            os.path.join(PROJECT_DIR, "matchup_output.txt")
        ]

    # result = subprocess.run(command, capture_output=True, text=True)
    # output = result.stdout

    subprocess.run(command, capture_output=True, text=True)
    with open(os.path.join(PROJECT_DIR, "matchup_output.txt"), "r") as f:
        output = f.read()

    probs = re.findall(r"Probability \[([0-9.]+),", output)

    if len(probs) >= 2:
        return {
            "pitcherWinProb": float(probs[0]),
            "batterWinProb": float(probs[1])
        }
    else:
        print("Captured Output:", output)
        raise Exception("Could not find probabilities.")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python auto_matchup.py \"Pitcher Name\" \"Batter Name\"")
        sys.exit(1)

    pitcher = sys.argv[1]
    batter = sys.argv[2]

    generate_matchup_pcsp(pitcher, batter)

    try:
        result = run_pat_model()
        print("Final Result:", result)
    except Exception as e:
        print(f"Failed: {e}")
