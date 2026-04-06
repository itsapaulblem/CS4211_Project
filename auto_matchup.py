import subprocess
import re
import os
import sys
from dotenv import load_dotenv
from data_parser import get_matchup, load_matchup_json

load_dotenv()

def _find_mono_exe() -> str:
    import shutil
    mono = shutil.which("mono")
    if mono:
        return mono
    candidates = [
        os.path.join(os.environ.get("ProgramFiles", ""), "Mono", "bin", "mono.exe"),
        os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Mono", "bin", "mono.exe"),
    ]
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    raise FileNotFoundError(
        "Mono runtime not found. Install Mono from "
        "https://www.mono-project.com/download/stable/"
    )


def delete_matchup_output(project_dir: str | None = None) -> str:
    if project_dir is None:
        project_dir = os.getenv("PROJECT_DIR") or os.getcwd()
    output_path = os.path.join(project_dir, "matchup_output.txt")
    if os.path.exists(output_path):
        os.remove(output_path)
    return output_path


def generate_matchup_pcsp(pitcher, batter, matchup=None):
    if matchup is None:
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
    output_path = delete_matchup_output(PROJECT_DIR)
    pcsp_path = os.path.join(PROJECT_DIR, "matchup.pcsp")

    if system == "Windows":
        command = [_find_mono_exe(), PAT_EXE, "-pcsp", pcsp_path, output_path]
    else:
        command = ["mono", PAT_EXE, "-pcsp", pcsp_path, output_path]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=120,
        cwd=os.path.dirname(PAT_EXE) or None,
    )
    if result.returncode != 0:
        raise Exception(
            f"PAT exited with code {result.returncode}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    if not os.path.exists(output_path):
        raise Exception(
            "PAT did not produce matchup_output.txt.\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    with open(output_path, "r") as f:
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
    use_cached = "--use-cached" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--use-cached"]

    if len(args) != 2:
        print("Usage: python auto_matchup.py \"Pitcher Name\" \"Batter Name\" [--use-cached]")
        sys.exit(1)

    pitcher = args[0]
    batter = args[1]

    matchup = load_matchup_json() if use_cached else None
    generate_matchup_pcsp(pitcher, batter, matchup)

    try:
        result = run_pat_model()
        print("Final Result:", result)
    except Exception as e:
        print(f"Failed: {e}")
