"""
llm_agent.py — LLM Agent Layer
===================================================================
Sits on top of the existing pipeline:
  - data_parser.py     → get_matchup(), generate_pcsp_defines()
  - auto_update_pcsp.py → generates matchup.pcsp from template
  - auto_matchup.py     → runs PAT and returns probabilities

Classification format:
  { "intent": "prediction | strategy",
    "analysis_type": "reachability | sensitivity" }

Three execution paths:
  prediction + reachability  → 1 PAT run (base model)
  prediction + sensitivity   → 2 PAT runs (base vs modified)
  strategy   + sensitivity   → N PAT runs (grid search, find best)

Usage:
  python llm_agent.py "What is the probability Cole gets Judge out?"
  python llm_agent.py "Should Cole throw more breaking balls against Judge?"
  python llm_agent.py "What if Cole improves his fastball command by 10%?"

Requirements:
  - All existing project dependencies (see requirements.txt)
  - .env configured with PROJECT_DIR and PAT_EXE
  - pip install openai (or google-generativeai) for real LLM calls
"""

from google.genai import types
from data_parser import get_matchup
import json
import os
import re
import subprocess
import sys
from dotenv import load_dotenv

# Load project paths from .env
load_dotenv()
PROJECT_DIR = os.getenv("PROJECT_DIR", "")
PAT_EXE = os.getenv("PAT_EXE", "")

# Import existing project modules
sys.path.insert(0, PROJECT_DIR)


# ============================================================================
# SYSTEM PROMPT
# ============================================================================

SYSTEM_PROMPT = """You are an expert AI Baseball Analyst. You have access to a
Formal Verification engine (PAT model checker) that computes EXACT at-bat
outcome probabilities. You must NEVER guess or estimate probabilities.

THE MODEL:
An at-bat is a probabilistic state machine with 30 parameters:

Pitcher (9): P_FAST_PCT / P_BREAK_PCT / P_OFF_PCT (pitch mix, sum=100),
  P_FAST_ZONE/MISS, P_BREAK_ZONE/MISS, P_OFF_ZONE/MISS (zone accuracy,
  pairs sum=100)

Batter (18+): B_FAST_SWING/TAKE, B_BREAK_SWING/TAKE, B_OFF_SWING/TAKE,
  B_FAST_WHIFF/CONTACT, B_BREAK_WHIFF/CONTACT, B_OFF_WHIFF/CONTACT,
  B_FAST_FOUL/OUT/HIT, B_BREAK_FOUL/OUT/HIT, B_OFF_FOUL/OUT/HIT

Terminal: pitcherWins (result==1) vs batterWins (result==2)

OUTPUT FORMAT — always a JSON with these fields:
  "intent":        "prediction" or "strategy"
  "analysis_type": "reachability" or "sensitivity"
  "pitcher":       full pitcher name (e.g. "Gerrit Cole")
  "batter":        full batter name (e.g. "Aaron Judge")

Additional fields depending on combination:
  prediction + sensitivity: "parameter" (PCSP# param name), "delta" (int)
  strategy + sensitivity:   "parameter_to_vary"
    ("pitch_mix"|"zone_accuracy"|"swing_rate"|"all")

THE 3 COMBINATIONS:

1. prediction + reachability
   → "What is the probability Cole gets Judge out?"
   Fields: pitcher, batter

2. strategy + sensitivity
   → "Should Cole throw more breaking balls against Judge?"
   Fields: pitcher, batter, parameter_to_vary

3. prediction + sensitivity
   → "What if Cole's fastball command improves by 10%?"
   Fields: pitcher, batter, parameter, delta

RULES:
- NEVER guess probabilities. Always use a tool.
- Output ONLY a valid JSON object. No markdown, no explanation.
- Use FULL NAMES (e.g. "Gerrit Cole", not "Cole").

EXAMPLES:

User: "What is the probability Gerrit Cole gets Aaron Judge out?"
{"intent": "prediction", "analysis_type": "reachability",
    "pitcher": "Gerrit Cole", "batter": "Aaron Judge"}

User: "Should Cole throw more breaking balls against Judge?"
{"intent": "strategy", "analysis_type": "sensitivity",
    "pitcher": "Gerrit Cole", "batter": "Aaron Judge",
    "parameter_to_vary": "pitch_mix"}

User: "What if Cole's fastball command improves by 10%?"
{"intent": "prediction", "analysis_type": "sensitivity",
    "pitcher": "Gerrit Cole", "batter": "Aaron Judge",
    "parameter": "P_FAST_ZONE", "delta": 10}

User: "What is the optimal pitch mix for Cole against Judge?"
{"intent": "strategy", "analysis_type": "sensitivity",
    "pitcher": "Gerrit Cole", "batter": "Aaron Judge",
    "parameter_to_vary": "pitch_mix"}

User: "How much does a 5% decrease in Judge's chase rate help Cole?"
{"intent": "prediction", "analysis_type": "sensitivity",
    "pitcher": "Gerrit Cole", "batter": "Aaron Judge",
    "parameter": "B_BREAK_SWING", "delta": -5}
"""


# ============================================================================
# LLM CALL
# ============================================================================

def call_llm(user_query: str) -> dict:
    """
    Send query to LLM, get structured JSON.
    Uncomment your preferred API below.
    """

    # ----- OPTION A: OpenAI -----
    # from openai import OpenAI
    # client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    # resp = client.chat.completions.create(
    #     model="gpt-4o",
    #     messages=[
    #         {"role": "system", "content": SYSTEM_PROMPT},
    #         {"role": "user", "content": user_query},
    #     ],
    #     temperature=0,
    # )
    # raw = resp.choices[0].message.content

    # ----- OPTION B: Google Gemini -----
    from google import genai

    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    response = client.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=user_query,
        config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT),
    )
    raw = response.text

    # ----- MOCK (testing without API key) -----
    # raw = _mock_llm(user_query)

    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    tool_call = json.loads(raw)
    _validate(tool_call)
    return tool_call


def _mock_llm(query: str) -> str:
    """Regex-based mock for testing without an API key."""
    q = query.lower()
    pitcher = "Gerrit Cole"
    batter = "Aaron Judge"

    # strategy + sensitivity
    if any(re.search(kw, q) for kw in [
        r"should.*throw", r"how should", r"best.*mix",
        r"optimal", r"more breaking", r"more fastball",
    ]):
        return json.dumps({
            "intent": "strategy",
            "analysis_type": "sensitivity",
            "pitcher": pitcher,
            "batter": batter,
            "parameter_to_vary": "pitch_mix",
        })

    # prediction + sensitivity
    if any(re.search(kw, q) for kw in [
        r"what happens if", r"what if.*improve", r"what if.*change",
        r"what if.*increase", r"what if.*decrease", r"how much does",
    ]):
        return json.dumps({
            "intent": "prediction",
            "analysis_type": "sensitivity",
            "pitcher": pitcher,
            "batter": batter,
            "parameter": "P_FAST_ZONE",
            "delta": 10,
        })

    # prediction + reachability (default)
    return json.dumps({
        "intent": "prediction",
        "analysis_type": "reachability",
        "pitcher": pitcher,
        "batter": batter,
    })


def _validate(tc: dict):
    assert tc.get("intent") in ("prediction", "strategy"), \
        f"intent must be prediction|strategy, got {tc.get('intent')}"
    assert tc.get("analysis_type") in ("reachability", "sensitivity"), \
        f"analysis_type must be reachability|sensitivity, " \
        f"got {tc.get('analysis_type')}"
    assert "pitcher" in tc and "batter" in tc, \
        "Must include pitcher and batter"

    if tc["intent"] == "prediction" and tc["analysis_type"] == "sensitivity":
        assert "parameter" in tc and "delta" in tc, \
            "prediction + sensitivity requires parameter and delta"
    if tc["intent"] == "strategy" and tc["analysis_type"] == "sensitivity":
        assert "parameter_to_vary" in tc, \
            "strategy + sensitivity requires parameter_to_vary"


# ============================================================================
# INTEGRATION WITH EXISTING PIPELINE
# ============================================================================

def fetch_stats(pitcher: str, batter: str) -> dict:
    """
    Uses data_parser.get_matchup() to fetch real MLB Statcast data.
    Returns the parameter dict with all 30 PCSP# parameters.
    """
    print(f"[Data] Fetching stats: {pitcher} vs {batter}")
    return get_matchup(pitcher, batter)


# def build_model(stats: dict, pitcher: str, batter: str,
#                 output_path: str = "matchup.pcsp") -> str:
#     """
#     Reads baseball_template.pcsp, injects stats via generate_pcsp_defines(),
#     writes the output .pcsp file.
#     """
#     define_block = generate_pcsp_defines(stats)
#     template_path = os.path.join(PROJECT_DIR, "baseball_template.pcsp")

#     with open(template_path, "r") as f:
#         content = f.read()

#     # Replace the define block
#     pattern = r"\A(?:\s*//.*\n|\s*#define[^\n]*\n|\s*\n)*?(?=\s*var\s+)"
#     new_content = re.sub(pattern, define_block + "\n", content,
#                          count=1, flags=re.MULTILINE)

#     # Remove comments
#     new_content = re.sub(r"//.*", "", new_content).lstrip()

#     full_output = os.path.join(PROJECT_DIR, output_path)
#     with open(full_output, "w") as f:
#         f.write(new_content)

#     print(f"[Model] Generated: {full_output}")
#     return full_output

def build_model(stats: dict, pitcher: str, batter: str,
                output_path: str = "matchup.pcsp") -> str:
    template_path = os.path.join(PROJECT_DIR, "baseball_template.pcsp")

    with open(template_path, "r") as f:
        content = f.read()

    for key, val in stats.items():
        content = content.replace(f"{{{{{key}}}}}", str(val))

    full_output = os.path.join(PROJECT_DIR, output_path)
    with open(full_output, "w") as f:
        f.write(content)

    print(f"[Model] Generated: {full_output}")
    return full_output


def build_perturbed_model(stats: dict, pitcher: str, batter: str,
                          parameter: str, delta: int,
                          output_path: str = None) -> str:
    """
    Copy stats, perturb one parameter, fix complements, build model.
    """
    modified = dict(stats)
    old_val = modified[parameter]
    new_val = max(1, min(99, old_val + delta))
    modified[parameter] = new_val

    # Fix complement groups so sums stay at 100
    _fix_complements(parameter, modified, old_val, new_val)

    if output_path is None:
        sign = '+' if delta > 0 else ''
        output_path = f"matchup_{parameter}_{sign}{delta}.pcsp"

    return build_model(modified, pitcher, batter, output_path)


def run_pat(pcsp_file: str) -> dict:
    """
    Runs PAT on a .pcsp file and parses the probability output.
    Matches the exact approach used in auto_matchup.py:
      - Windows: WSL + mono, writes output to a file
      - macOS/Linux: mono directly, writes output to a file
    Returns: {"pitcherWins_prob": float, "batterWins_prob": float}
    """
    print(f"[PAT] Running: {pcsp_file}")

    if not PAT_EXE:
        print("[PAT] WARNING: PAT_EXE not set in .env — returning stub values")
        return {"pitcherWins_prob": 0.634, "batterWins_prob": 0.366}

    pcsp_abs = os.path.abspath(pcsp_file)
    # output_file = os.path.splitext(pcsp_abs)[0] + "_output.txt"
    # output_abs = os.path.abspath(output_file)
    output_filename = os.path.splitext(os.path.basename(pcsp_abs))[
        0] + "_output.txt"

    output_file = os.path.join(PROJECT_DIR, output_filename)
    output_abs = os.path.abspath(output_file)

    import platform
    system = platform.system()

    if system == "Windows":
        # WSL path conversion
        def to_wsl_path(win_path):
            return (
                "/mnt/" +
                win_path.replace("\\", "/")
                .replace(":", "")
                .lower()
            )

        cmd = [
            "wsl", "mono",
            to_wsl_path(PAT_EXE),
            "-pcsp",
            to_wsl_path(pcsp_abs),
            to_wsl_path(output_abs),
        ]
    elif system == "Darwin":  # macOS
        cmd = ["mono", PAT_EXE, "-pcsp", pcsp_abs, output_abs]
    else:  # Linux
        cmd = ["mono", PAT_EXE, "-pcsp", pcsp_abs, output_abs]

    # try:
    #     subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    # except subprocess.TimeoutExpired:
    #     print("[PAT] ERROR: Timed out after 120s")
    #     return {"pitcherWins_prob": 0.0, "batterWins_prob": 0.0}
    # except FileNotFoundError:
    #     print("[PAT] ERROR: WSL/mono/PAT not found—"
    #           "check .env and WSL install")
    #     return {"pitcherWins_prob": 0.0, "batterWins_prob": 0.0}
    # except Exception as e:
    #     print(f"[PAT] ERROR: {e}")
    #     return {"pitcherWins_prob": 0.0, "batterWins_prob": 0.0}

    # # Read output from file
    # try:
    #     with open(output_file, "r") as f:
    #         output = f.read()
    # except FileNotFoundError:
    #     print(f"[PAT] ERROR: Output file not created: {output_file}")
    #     return {"pitcherWins_prob": 0.0, "batterWins_prob": 0.0}

    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        with open(output_file, "r") as f:
            output = f.read()
    except subprocess.TimeoutExpired:
        print("[PAT] ERROR: Timed out after 120s")
        return {"pitcherWins_prob": 0.0, "batterWins_prob": 0.0}
    except FileNotFoundError:
        print("[PAT] ERROR: WSL/mono/PAT not found — "
              "check .env and WSL install")
        return {"pitcherWins_prob": 0.0, "batterWins_prob": 0.0}
    except Exception as e:
        print(f"[PAT] ERROR: {e}")
        return {"pitcherWins_prob": 0.0, "batterWins_prob": 0.0}

    # Parse probabilities
    probs_list = re.findall(r"Probability \[([0-9.]+),", output)

    if len(probs_list) >= 2:
        return {
            "pitcherWins_prob": float(probs_list[0]),
            "batterWins_prob": float(probs_list[1]),
        }
    elif len(probs_list) == 1:
        p = float(probs_list[0])
        return {
            "pitcherWins_prob": p,
            "batterWins_prob": round(1.0 - p, 4),
        }
    else:
        print(f"[PAT] WARNING: Could not parse output:\n{output[:500]}")
        return {"pitcherWins_prob": 0.0, "batterWins_prob": 0.0}


# ============================================================================
# COMPLEMENT GROUPS (must sum to 100)
# ============================================================================

COMPLEMENT_GROUPS = {
    "pitch_mix":     ["P_FAST_PCT", "P_BREAK_PCT", "P_OFF_PCT"],
    "fast_zone":     ["P_FAST_ZONE", "P_FAST_MISS"],
    "break_zone":    ["P_BREAK_ZONE", "P_BREAK_MISS"],
    "off_zone":      ["P_OFF_ZONE", "P_OFF_MISS"],
    "fast_swing":    ["B_FAST_SWING", "B_FAST_TAKE"],
    "break_swing":   ["B_BREAK_SWING", "B_BREAK_TAKE"],
    "off_swing":     ["B_OFF_SWING", "B_OFF_TAKE"],
    "fast_whiff":    ["B_FAST_WHIFF", "B_FAST_CONTACT"],
    "break_whiff":   ["B_BREAK_WHIFF", "B_BREAK_CONTACT"],
    "off_whiff":     ["B_OFF_WHIFF", "B_OFF_CONTACT"],
    "fast_contact":  ["B_FAST_FOUL", "B_FAST_OUT", "B_FAST_HIT"],
    "break_contact": ["B_BREAK_FOUL", "B_BREAK_OUT", "B_BREAK_HIT"],
    "off_contact":   ["B_OFF_FOUL", "B_OFF_OUT", "B_OFF_HIT"],
}

PARAM_GROUPS_FOR_STRATEGY = {
    "pitch_mix":     ["P_FAST_PCT", "P_BREAK_PCT", "P_OFF_PCT"],
    "zone_accuracy": ["P_FAST_ZONE", "P_BREAK_ZONE", "P_OFF_ZONE"],
    "swing_rate":    ["B_FAST_SWING", "B_BREAK_SWING", "B_OFF_SWING"],
}

DELTAS = [-10, -5, 5, 10]


def _fix_complements(param_name: str, stats: dict, old_val: int, new_val: int):
    """After changing one parameter, adjust its group to keep sum = 100."""
    for group_name, members in COMPLEMENT_GROUPS.items():
        if param_name in members:
            others = [m for m in members if m != param_name]
            diff = new_val - old_val

            if len(others) == 1:
                stats[others[0]] = stats[others[0]] - diff
            else:
                other_total = sum(stats.get(m, 0) for m in others)
                if other_total == 0:
                    return
                for m in others:
                    share = stats[m] / other_total
                    stats[m] = max(1, round(stats[m] - diff * share))
                # Fix rounding
                current_sum = sum(stats[m] for m in members)
                if current_sum != 100:
                    stats[others[0]] += (100 - current_sum)
            return


# ============================================================================
# EXECUTION PATHS
# ============================================================================

def execute_tool(tc: dict) -> dict:
    intent = tc["intent"]
    analysis = tc["analysis_type"]
    pitcher = tc["pitcher"]
    batter = tc["batter"]

    if intent == "prediction" and analysis == "reachability":
        return _prediction_reachability(pitcher, batter)
    elif intent == "prediction" and analysis == "sensitivity":
        return _prediction_sensitivity(
            pitcher, batter, tc["parameter"], tc["delta"])
    elif intent == "strategy" and analysis == "sensitivity":
        param_to_vary = tc.get("parameter_to_vary", "all")
        return _strategy_sensitivity(pitcher, batter, param_to_vary)
    elif intent == "strategy" and analysis == "reachability":
        return _prediction_reachability(pitcher, batter)


def _prediction_reachability(pitcher: str, batter: str) -> dict:
    """1 model → 1 PAT run → return probabilities."""
    stats = fetch_stats(pitcher, batter)
    pcsp_file = build_model(stats, pitcher, batter)
    result = run_pat(pcsp_file)
    return {
        "intent": "prediction", "analysis_type": "reachability",
        "pitcher": pitcher, "batter": batter, **result,
    }


def _prediction_sensitivity(pitcher: str, batter: str,
                            parameter: str, delta: int) -> dict:
    """2 models → compare base vs modified."""
    stats = fetch_stats(pitcher, batter)

    base_file = build_model(stats, pitcher, batter, "matchup_base.pcsp")
    base = run_pat(base_file)

    mod_file = build_perturbed_model(stats, pitcher, batter, parameter, delta)
    modified = run_pat(mod_file)

    return {
        "intent": "prediction", "analysis_type": "sensitivity",
        "pitcher": pitcher, "batter": batter,
        "parameter": parameter, "delta": delta,
        "base_pitcherWins": base.get("pitcherWins_prob", 0),
        "base_batterWins": base.get("batterWins_prob", 0),
        "modified_pitcherWins": modified.get("pitcherWins_prob", 0),
        "modified_batterWins": modified.get("batterWins_prob", 0),
        "change": round(modified.get("pitcherWins_prob", 0) -
                        base.get("pitcherWins_prob", 0), 4),
    }


def _strategy_sensitivity(pitcher: str, batter: str,
                          param_to_vary: str) -> dict:
    """N models → grid search → find optimal adjustment."""
    stats = fetch_stats(pitcher, batter)

    base_file = build_model(stats, pitcher, batter, "matchup_base.pcsp")
    base_prob = run_pat(base_file).get("pitcherWins_prob", 0)

    if param_to_vary == "all":
        params = [p for g in PARAM_GROUPS_FOR_STRATEGY.values() for p in g]
    elif param_to_vary in PARAM_GROUPS_FOR_STRATEGY:
        params = PARAM_GROUPS_FOR_STRATEGY[param_to_vary]
    else:
        params = [param_to_vary]

    results = []
    for param in params:
        for delta in DELTAS:
            pcsp_file = build_perturbed_model(
                dict(stats), pitcher, batter, param, delta
            )
            prob = run_pat(pcsp_file).get("pitcherWins_prob", 0)
            results.append({
                "parameter": param, "delta": delta,
                "pitcherWins_prob": prob,
                "improvement": round(prob - base_prob, 4),
            })

    results.sort(key=lambda r: r["pitcherWins_prob"], reverse=True)

    return {
        "intent": "strategy", "analysis_type": "sensitivity",
        "pitcher": pitcher, "batter": batter,
        "base_pitcherWins": base_prob,
        "best_adjustment": results[0] if results else {},
        "all_results": results, "total_runs": len(results),
    }


# ============================================================================
# RESULT SYNTHESIS
# ============================================================================

SYNTHESIS_PROMPT = (
    "You are a baseball coach. Given the formal model-checking "
    "results below, provide a clear 3-5 sentence summary. Include exact "
    "probabilities. Explain in plain baseball language. Do NOT change "
    "numbers.\n\n"
    "User question: {query}\n"
    "Result: {result_json}\n"
)


def synthesize(user_query: str, tc: dict, result: dict) -> str:
    """Turn raw results into coaching advice."""
    # TODO: In production, call LLM with SYNTHESIS_PROMPT
    intent = tc["intent"]
    analysis = tc["analysis_type"]

    if intent == "prediction" and analysis == "reachability":
        pw = result.get("pitcherWins_prob", 0)
        bw = result.get("batterWins_prob", 0)
        return (
            f"Based on formal model checking with real Statcast data: "
            f"{result['pitcher']} gets {result['batter']} out "
            f"{pw:.1%} of the time (strikeout + fielded out), "
            f"while {result['batter']} reaches base {bw:.1%} (walk + hit)."
        )

    elif intent == "prediction" and analysis == "sensitivity":
        readable = result["parameter"].replace(
            "P_", "").replace("B_", "").replace("_", " ").lower()
        change = result["change"]
        return (
            f"If {readable} changes by {result['delta']:+d} points: "
            f"pitcher-win probability moves from "
            f"{result['base_pitcherWins']:.1%} to "
            f"{result['modified_pitcherWins']:.1%} "
            f"({'+' if change > 0 else ''}{change:.2%})."
        )

    elif intent == "strategy" and analysis == "sensitivity":
        if not result.get("best_adjustment"):
            return "No improvements found."
        best = result["best_adjustment"]
        readable = best["parameter"].replace("P_", "").replace(
            "B_", "").replace("_", " ").lower()
        direction = "increase" if best["delta"] > 0 else "decrease"
        return (
            f"Recommendation: {direction} {readable} by "
            f"{abs(best['delta'])} percentage points. This moves "
            f"pitcher-win probability from {result['base_pitcherWins']:.1%} "
            f"to {best['pitcherWins_prob']:.1%} "
            f"({'+' if best['improvement'] > 0 else ''}"
            f"{best['improvement']:.2%}). "
            f"Tested {result['total_runs']} variations."
        )

    return json.dumps(result, indent=2)


# ============================================================================
# MAIN
# ============================================================================

def run_agent(user_query: str) -> str:
    """Full pipeline: query → LLM classify → execute → synthesize → answer."""
    print(f"\n{'='*60}")
    print(f"User: {user_query}")
    print(f"{'='*60}")

    print("\n[1] LLM classifying...")
    tc = call_llm(user_query)
    print(f"    intent:        {tc['intent']}")
    print(f"    analysis_type: {tc['analysis_type']}")
    print(f"    pitcher:       {tc['pitcher']}")
    print(f"    batter:        {tc['batter']}")

    print(f"\n[2] Executing: {tc['intent']} + {tc['analysis_type']}...")
    result = execute_tool(tc)

    print("\n[3] Synthesizing...")
    answer = synthesize(user_query, tc, result)

    print(f"\n{'='*60}")
    print(f"COACH: {answer}")
    print(f"{'='*60}")
    return answer


if __name__ == "__main__":
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        run_agent(query)
    else:
        print("CS4211 Baseball AI Coach — LLM Agent Layer")
        print("=" * 45)
        print('\nUsage:')
        print('  python llm_agent.py '
              '"What is the probability Cole gets Judge out?"')
        print('  python llm_agent.py '
              '"Should Cole throw more breaking balls?"')
        print('  python llm_agent.py '
              '"What if Cole improves fastball command by 10%?"')
        print("\nRunning demo queries...\n")

        queries = [
            "What is the probability Gerrit Cole gets Aaron Judge out?",
            "Should Cole throw more breaking balls against Judge?",
            "What if Cole's fastball command improves by 10%?",
        ]
        for q in queries:
            run_agent(q)
            print()
