"""
strategy_analysis.py — Pitch-Mix Strategy Analysis (Part C)
============================================================

Two modes of analysis for pitching strategy optimisation using
PAT (Process Analysis Toolkit) formal verification.

Sensitivity mode — test one pitch-mix perturbation:
    python strategy_analysis.py sensitivity "Gerrit Cole" "Aaron Judge" \
        --from fast --to break --step 5

Optimize mode — sweep all legal pitch mixes and find the best:
    python strategy_analysis.py optimize "Gerrit Cole" "Aaron Judge" \
        --step 5 --min-pct 5

Only P_FAST_PCT, P_BREAK_PCT, P_OFF_PCT are varied.
All other matchup parameters stay fixed at their baseline values.
"""

import argparse
import os
import re
import subprocess
import sys

from dotenv import load_dotenv
from data_parser import get_matchup, load_matchup_json

load_dotenv()

# ── Constants ────────────────────────────────────────────────────────────────

PITCH_TYPES = ("fast", "break", "off")

PITCH_MIX_KEYS: dict[str, str] = {
    "fast":  "P_FAST_PCT",
    "break": "P_BREAK_PCT",
    "off":   "P_OFF_PCT",
}


# ── Mono runtime detection ───────────────────────────────────────────────────

_MONO_SEARCH_PATHS = [
    os.path.join(os.environ.get("ProgramFiles", ""), "Mono", "bin", "mono.exe"),
    os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Mono", "bin", "mono.exe"),
]


def _find_mono() -> str:
    """Locate the Mono executable.  Checks PATH first, then common install dirs."""
    import shutil
    path = shutil.which("mono")
    if path:
        return path
    for candidate in _MONO_SEARCH_PATHS:
        if os.path.isfile(candidate):
            return candidate
    raise RuntimeError(
        "Mono runtime not found. PAT requires Mono to run.\n"
        "Download from https://www.mono-project.com/download/stable/"
    )


# ── Core helpers ─────────────────────────────────────────────────────────────

def write_matchup_pcsp(
    matchup: dict,
    template_path: str = "baseball_template.pcsp",
    output_path: str = "matchup.pcsp",
) -> None:
    """Substitute matchup values into the PCSP template and write to disk."""
    with open(template_path, "r") as f:
        content = f.read()
    for key, val in matchup.items():
        content = content.replace(f"{{{{{key}}}}}", str(val))
    with open(output_path, "w") as f:
        f.write(content)


def run_pat_on_matchup(
    matchup: dict,
    template_path: str = "baseball_template.pcsp",
    pcsp_path: str = "matchup.pcsp",
) -> dict[str, float]:
    """
    Write the PCSP model, run PAT verification, and return probabilities.

    Returns:
        {"pitcherWinProb": float, "batterWinProb": float}
    """
    write_matchup_pcsp(matchup, template_path, pcsp_path)

    project_dir = os.getenv("PROJECT_DIR")
    pat_exe = os.getenv("PAT_EXE")
    if not project_dir or not pat_exe:
        raise RuntimeError(
            "Set PROJECT_DIR and PAT_EXE in your .env file. "
            "See .env.example for reference."
        )

    output_file = os.path.join(project_dir, "matchup_output.txt")

    if os.path.exists(output_file):
        os.remove(output_file)

    abs_pcsp = os.path.join(project_dir, pcsp_path)
    pat_dir = os.path.dirname(pat_exe)

    mono_exe = _find_mono()
    command = [mono_exe, pat_exe, "-pcsp", abs_pcsp, output_file]

    try:
        proc = subprocess.run(
            command, capture_output=True, text=True,
            timeout=120, cwd=pat_dir,
        )
    except FileNotFoundError:
        raise RuntimeError(
            "Mono is not installed. PAT requires the Mono runtime.\n"
            "Download from https://www.mono-project.com/download/stable/"
        )

    if proc.returncode != 0:
        raise RuntimeError(
            f"PAT exited with code {proc.returncode}\n"
            f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
        )

    if not os.path.exists(output_file):
        raise RuntimeError(
            "PAT did not produce matchup_output.txt.\n"
            f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
        )

    with open(output_file, "r") as f:
        output = f.read()

    probs = re.findall(r"Probability \[([0-9.]+),", output)
    if len(probs) < 2:
        raise RuntimeError(
            f"Could not parse probabilities from PAT output:\n{output}"
        )

    return {
        "pitcherWinProb": float(probs[0]),
        "batterWinProb": float(probs[1]),
    }


def apply_pitch_mix_shift(
    matchup: dict,
    from_pitch: str,
    to_pitch: str,
    step: int = 5,
) -> dict:
    """
    Return a copy of matchup with *step*% moved from *from_pitch* to
    *to_pitch*.  Raises ValueError if the shift is illegal.
    """
    if from_pitch not in PITCH_TYPES:
        raise ValueError(f"from_pitch must be one of {PITCH_TYPES}")
    if to_pitch not in PITCH_TYPES:
        raise ValueError(f"to_pitch must be one of {PITCH_TYPES}")
    if from_pitch == to_pitch:
        raise ValueError("from_pitch and to_pitch must be different")

    from_key = PITCH_MIX_KEYS[from_pitch]
    new_from = matchup[from_key] - step
    if new_from < 1:
        raise ValueError(
            f"Cannot shift {step}% from {from_pitch} "
            f"(currently {matchup[from_key]}%): would drop below 1%"
        )

    shifted = dict(matchup)
    shifted[from_key] = new_from
    shifted[PITCH_MIX_KEYS[to_pitch]] = matchup[PITCH_MIX_KEYS[to_pitch]] + step
    return shifted


def generate_candidate_pitch_mixes(
    step: int = 5,
    min_pct: int = 5,
) -> list[dict[str, int]]:
    """
    All valid (fast, break, off) triples where each value >= *min_pct*,
    they sum to 100, and values lie on a grid with the given *step*.
    """
    candidates = []
    for fast in range(min_pct, 100 - 2 * min_pct + 1, step):
        for brk in range(min_pct, 100 - min_pct - fast + 1, step):
            off = 100 - fast - brk
            if off >= min_pct:
                candidates.append({"fast": fast, "break": brk, "off": off})
    return candidates


# ── Sensitivity mode ─────────────────────────────────────────────────────────

def run_sensitivity_analysis(
    pitcher: str,
    batter: str,
    from_pitch: str,
    to_pitch: str,
    step: int = 5,
    matchup: dict = None,
) -> dict:
    """
    Compute baseline pitcherWinProb, apply one pitch-mix perturbation,
    rerun PAT, and return a structured result with the delta.
    """
    if matchup is None:
        print(f"Fetching matchup data for {pitcher} vs {batter}...")
        matchup = get_matchup(pitcher, batter)
    baseline_mix = {k: matchup[PITCH_MIX_KEYS[k]] for k in PITCH_TYPES}

    print("Running baseline through PAT...")
    baseline_prob = run_pat_on_matchup(matchup)["pitcherWinProb"]

    shifted = apply_pitch_mix_shift(matchup, from_pitch, to_pitch, step)
    new_mix = {k: shifted[PITCH_MIX_KEYS[k]] for k in PITCH_TYPES}

    print(
        f"Running shifted mix "
        f"(fast={new_mix['fast']} break={new_mix['break']} off={new_mix['off']}) "
        f"through PAT..."
    )
    new_prob = run_pat_on_matchup(shifted)["pitcherWinProb"]
    delta = new_prob - baseline_prob

    return {
        "mode": "sensitivity",
        "pitcher": pitcher,
        "batter": batter,
        "baseline_mix": baseline_mix,
        "baseline_pitcherWinProb": round(baseline_prob, 5),
        "perturbation": {"from": from_pitch, "to": to_pitch, "step": step},
        "new_mix": new_mix,
        "new_pitcherWinProb": round(new_prob, 5),
        "delta": round(delta, 5),
        "improves": delta > 0,
    }


# ── Optimize mode ────────────────────────────────────────────────────────────

def run_optimization(
    pitcher: str,
    batter: str,
    step: int = 5,
    min_pct: int = 5,
    matchup: dict = None,
) -> dict:
    """
    Sweep all legal pitch-mix candidates and return the one that
    maximises pitcherWinProb.
    """
    if matchup is None:
        print(f"Fetching matchup data for {pitcher} vs {batter}...")
        matchup = get_matchup(pitcher, batter)
    baseline_mix = {k: matchup[PITCH_MIX_KEYS[k]] for k in PITCH_TYPES}

    print("Running baseline through PAT...")
    baseline_prob = run_pat_on_matchup(matchup)["pitcherWinProb"]

    candidates = generate_candidate_pitch_mixes(step, min_pct)
    total = len(candidates)
    print(f"\nTesting {total} candidate pitch mixes...\n")

    best_mix = dict(baseline_mix)
    best_prob = baseline_prob
    width = len(str(total))

    for i, mix in enumerate(candidates, 1):
        trial = dict(matchup)
        trial["P_FAST_PCT"] = mix["fast"]
        trial["P_BREAK_PCT"] = mix["break"]
        trial["P_OFF_PCT"] = mix["off"]

        prob = run_pat_on_matchup(trial)["pitcherWinProb"]
        tag = " *" if prob > best_prob else ""
        print(
            f"  [{i:>{width}}/{total}] "
            f"fast={mix['fast']:>2} break={mix['break']:>2} off={mix['off']:>2} "
            f"-> pitcherWinProb={prob:.5f}{tag}"
        )

        if prob > best_prob:
            best_prob = prob
            best_mix = dict(mix)

    return {
        "mode": "optimize",
        "pitcher": pitcher,
        "batter": batter,
        "baseline_mix": baseline_mix,
        "baseline_pitcherWinProb": round(baseline_prob, 5),
        "best_mix": best_mix,
        "best_pitcherWinProb": round(best_prob, 5),
        "improvement": round(best_prob - baseline_prob, 5),
        "num_candidates_tested": total,
    }


# ── Formatting ───────────────────────────────────────────────────────────────

def format_sensitivity_result(result: dict) -> str:
    """Format a sensitivity result dict as readable terminal output."""
    bm = result["baseline_mix"]
    nm = result["new_mix"]
    p = result["perturbation"]
    return "\n".join([
        "",
        "=" * 55,
        "  SENSITIVITY ANALYSIS",
        f"  {result['pitcher']} vs {result['batter']}",
        "=" * 55,
        f"  Baseline mix:        fast={bm['fast']} break={bm['break']} off={bm['off']}",
        f"  Baseline pitcherWin: {result['baseline_pitcherWinProb']:.5f}",
        "",
        f"  Perturbation:        -{p['step']}% {p['from']} -> +{p['step']}% {p['to']}",
        f"  New mix:             fast={nm['fast']} break={nm['break']} off={nm['off']}",
        f"  New pitcherWin:      {result['new_pitcherWinProb']:.5f}",
        f"  Delta:               {result['delta']:+.5f}",
        f"  Improves:            {'Yes' if result['improves'] else 'No'}",
        "=" * 55,
    ])


def format_optimization_result(result: dict) -> str:
    """Format an optimization result dict as readable terminal output."""
    bm = result["baseline_mix"]
    sm = result["best_mix"]
    labels = {"fast": "fastballs", "break": "breaking balls", "off": "offspeed"}

    changes = []
    for k in PITCH_TYPES:
        diff = sm[k] - bm[k]
        if diff > 0:
            changes.append(f"Increase {labels[k]} by {diff}%")
        elif diff < 0:
            changes.append(f"Reduce {labels[k]} by {abs(diff)}%")

    if changes:
        recommendation = " and ".join(changes) + "."
    else:
        recommendation = "Keep the current pitch mix (already optimal)."

    return "\n".join([
        "",
        "=" * 55,
        "  PITCH-MIX OPTIMISATION",
        f"  {result['pitcher']} vs {result['batter']}",
        "=" * 55,
        f"  Baseline mix:        fast={bm['fast']} break={bm['break']} off={bm['off']}",
        f"  Baseline pitcherWin: {result['baseline_pitcherWinProb']:.5f}",
        "",
        f"  Best mix:            fast={sm['fast']} break={sm['break']} off={sm['off']}",
        f"  Best pitcherWin:     {result['best_pitcherWinProb']:.5f}",
        f"  Improvement:         {result['improvement']:+.5f}",
        f"  Candidates tested:   {result['num_candidates_tested']}",
        "",
        f"  Recommendation:",
        f"  {recommendation}",
        "=" * 55,
    ])


# ── CLI ──────────────────────────────────────────────────────────────────────

def build_cli() -> argparse.ArgumentParser:
    """Build the argument parser with sensitivity and optimize sub-commands."""
    parser = argparse.ArgumentParser(
        description="Pitch-mix strategy analysis for baseball PAT model",
    )
    sub = parser.add_subparsers(dest="mode", required=True)

    sens = sub.add_parser("sensitivity", help="Test one pitch-mix perturbation")
    sens.add_argument("pitcher", help="Pitcher full name")
    sens.add_argument("batter", help="Batter full name")
    sens.add_argument(
        "--from", dest="from_pitch", required=True,
        choices=PITCH_TYPES, help="Pitch type to reduce",
    )
    sens.add_argument(
        "--to", dest="to_pitch", required=True,
        choices=PITCH_TYPES, help="Pitch type to increase",
    )
    sens.add_argument(
        "--step", type=int, default=5,
        help="Percentage points to shift (default: 5)",
    )
    sens.add_argument(
        "--use-cached", action="store_true",
        help="Load matchup from data/matchup.json instead of fetching live",
    )

    opt = sub.add_parser("optimize", help="Sweep all legal pitch mixes")
    opt.add_argument("pitcher", help="Pitcher full name")
    opt.add_argument("batter", help="Batter full name")
    opt.add_argument(
        "--step", type=int, default=5,
        help="Grid step size in percent (default: 5)",
    )
    opt.add_argument(
        "--min-pct", type=int, default=5,
        help="Minimum percentage per pitch type (default: 5)",
    )
    opt.add_argument(
        "--use-cached", action="store_true",
        help="Load matchup from data/matchup.json instead of fetching live",
    )

    return parser


def main() -> None:
    parser = build_cli()
    args = parser.parse_args()

    try:
        matchup = load_matchup_json() if args.use_cached else None

        if args.mode == "sensitivity":
            if args.from_pitch == args.to_pitch:
                parser.error("--from and --to must be different pitch types")
            result = run_sensitivity_analysis(
                args.pitcher, args.batter,
                args.from_pitch, args.to_pitch,
                args.step,
                matchup=matchup,
            )
            print(format_sensitivity_result(result))

        elif args.mode == "optimize":
            result = run_optimization(
                args.pitcher, args.batter,
                args.step, args.min_pct,
                matchup=matchup,
            )
            print(format_optimization_result(result))

    except RuntimeError as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"\nValidation error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
