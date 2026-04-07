"""
llm_agent.py — LLM Agent Layer
===================================================================
Sits on top of the existing pipeline:
  - data_parser.py       → get_matchup()
  - strategy_analysis.py → run_pat_on_matchup(), run_sensitivity_analysis(),
                           run_optimization()

Classification format (from LLM):
  { "intent": "prediction | strategy",
    "analysis_type": "reachability | sensitivity | optimize" }

Four execution paths:
  prediction + reachability  → 1 PAT run (base model)
  prediction + sensitivity   → 2 PAT runs (base vs modified parameter)
  strategy   + sensitivity   → 2 PAT runs (base vs shifted pitch mix)
  strategy   + optimize      → N PAT runs (grid sweep, find best mix)

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
import sys

from dotenv import load_dotenv
from data_parser import get_matchup, load_matchup_json
from strategy_analysis import (
    run_pat_on_matchup,
    run_sensitivity_analysis,
    run_optimization,
    format_sensitivity_result,
    format_optimization_result,
)

CACHE_PATH = "data/matchup.json"

load_dotenv()


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

Batter (21): B_FAST_SWING/TAKE, B_BREAK_SWING/TAKE, B_OFF_SWING/TAKE,
  B_FAST_WHIFF/CONTACT, B_BREAK_WHIFF/CONTACT, B_OFF_WHIFF/CONTACT,
  B_FAST_FOUL/OUT/HIT, B_BREAK_FOUL/OUT/HIT, B_OFF_FOUL/OUT/HIT

Terminal: pitcherWins (result==1) vs batterWins (result==2)

OUTPUT FORMAT — always a JSON object with these fields:
  "intent":        "prediction" or "strategy"
  "analysis_type": "reachability", "sensitivity", or "optimize"
  "pitcher":       full pitcher name (e.g. "Gerrit Cole")
  "batter":        full batter name (e.g. "Aaron Judge")

Additional fields depending on combination:

  prediction + sensitivity:
    "parameter": PCSP# param name (e.g. "P_FAST_PCT")
    "delta":     signed int (e.g. 10 or -5; default to 5 if user doesn't specify)

  strategy + sensitivity:
    "from_pitch": pitch type to REDUCE  ("fast", "break", or "off")
    "to_pitch":   pitch type to INCREASE ("fast", "break", or "off")
    "step":       percentage points to shift (int, default 5)

  strategy + optimize:
    "step":    grid step size in percent (int, default 5)
    "min_pct": minimum percentage per pitch type (int, default 5)

THE 4 COMBINATIONS:

1. prediction + reachability
   → "What is the probability Cole gets Judge out?"
   Fields: pitcher, batter

2. prediction + sensitivity  (ONE-SIDED pitch-mix OR any single parameter)
   → User mentions only ONE pitch type to increase/decrease, OR a single
     non-pitch-mix parameter (zone accuracy, swing rate, etc.).
   → The system automatically adjusts complementary parameters
     proportionally so group totals stay at 100.
   Fields: pitcher, batter, parameter, delta

3. strategy + sensitivity  (TWO-SIDED pitch-mix shift)
   → User explicitly names BOTH a pitch type to reduce AND a pitch type
     to increase (e.g. "decrease fastballs and increase breaking balls").
   → Only use this when the user specifies BOTH directions.
   Fields: pitcher, batter, from_pitch, to_pitch, step

4. strategy + optimize
   → "What is the optimal pitch mix for Cole against Judge?"
   Fields: pitcher, batter, step, min_pct

CHOOSING BETWEEN #2 AND #3:
- If the user mentions ONLY one pitch type direction (e.g. "throw MORE
  breaking balls", "increase offspeed"), use prediction + sensitivity
  with parameter = the corresponding P_*_PCT parameter.
- If the user explicitly mentions BOTH directions (e.g. "decrease
  fastballs AND increase breaking balls"), use strategy + sensitivity
  with from_pitch and to_pitch.

RULES:
- NEVER guess probabilities. Always use a tool.
- Output ONLY a valid JSON object. No markdown fences, no explanation.
- Use FULL NAMES (e.g. "Gerrit Cole", not "Cole").
- Default delta/step to 5 if the user does not specify a percentage.

EXAMPLES:

User: "What is the probability Gerrit Cole gets Aaron Judge out?"
{"intent": "prediction", "analysis_type": "reachability",
 "pitcher": "Gerrit Cole", "batter": "Aaron Judge"}

User: "Should Cole throw more breaking balls against Judge?"
{"intent": "prediction", "analysis_type": "sensitivity",
 "pitcher": "Gerrit Cole", "batter": "Aaron Judge",
 "parameter": "P_BREAK_PCT", "delta": 5}

User: "Should Cole increase breaking ball usage by 10% against Judge?"
{"intent": "prediction", "analysis_type": "sensitivity",
 "pitcher": "Gerrit Cole", "batter": "Aaron Judge",
 "parameter": "P_BREAK_PCT", "delta": 10}

User: "Should Cole throw fewer fastballs and more offspeed?"
{"intent": "strategy", "analysis_type": "sensitivity",
 "pitcher": "Gerrit Cole", "batter": "Aaron Judge",
 "from_pitch": "fast", "to_pitch": "off", "step": 5}

User: "Should Cole decrease fastballs and increase breaking balls by 5%?"
{"intent": "strategy", "analysis_type": "sensitivity",
 "pitcher": "Gerrit Cole", "batter": "Aaron Judge",
 "from_pitch": "fast", "to_pitch": "break", "step": 5}

User: "What if Cole's fastball command improves by 10%?"
{"intent": "prediction", "analysis_type": "sensitivity",
 "pitcher": "Gerrit Cole", "batter": "Aaron Judge",
 "parameter": "P_FAST_ZONE", "delta": 10}

User: "What is the optimal pitch mix for Cole against Judge?"
{"intent": "strategy", "analysis_type": "optimize",
 "pitcher": "Gerrit Cole", "batter": "Aaron Judge",
 "step": 5, "min_pct": 5}

User: "How much does a 5% decrease in Judge's chase rate help Cole?"
{"intent": "prediction", "analysis_type": "sensitivity",
 "pitcher": "Gerrit Cole", "batter": "Aaron Judge",
 "parameter": "B_BREAK_SWING", "delta": -5}

User: "What if Cole increases his fastball usage against Judge?"
{"intent": "prediction", "analysis_type": "sensitivity",
 "pitcher": "Gerrit Cole", "batter": "Aaron Judge",
 "parameter": "P_FAST_PCT", "delta": 5}
"""


# ============================================================================
# LLM CALL
# ============================================================================

def call_llm(user_query: str) -> dict:
    """
    Send query to LLM, get structured JSON.
    Uncomment your preferred API below.
    """
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


def _validate(tc: dict):
    """Validate the LLM's JSON response has all required fields."""
    intent = tc.get("intent")
    analysis = tc.get("analysis_type")

    assert intent in ("prediction", "strategy"), \
        f"intent must be prediction|strategy, got {intent}"
    assert analysis in ("reachability", "sensitivity", "optimize"), \
        f"analysis_type must be reachability|sensitivity|optimize, got {analysis}"
    assert "pitcher" in tc and "batter" in tc, \
        "Must include pitcher and batter"

    if intent == "prediction" and analysis == "sensitivity":
        assert "parameter" in tc, \
            "prediction + sensitivity requires parameter"
        tc.setdefault("delta", 5)
    if intent == "strategy" and analysis == "sensitivity":
        assert "from_pitch" in tc and "to_pitch" in tc, \
            "strategy + sensitivity requires from_pitch and to_pitch"


# ============================================================================
# COMPLEMENT GROUPS (for prediction + sensitivity perturbations)
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


def _fix_complements(param_name: str, stats: dict, old_val: int, new_val: int):
    """After changing one parameter, adjust its complement group to keep sum = 100."""
    for _group_name, members in COMPLEMENT_GROUPS.items():
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
                current_sum = sum(stats[m] for m in members)
                if current_sum != 100:
                    stats[others[0]] += (100 - current_sum)
            return


# ============================================================================
# EXECUTION PATHS
# ============================================================================

def execute_tool(tc: dict) -> dict:
    """Route the classified intent to the appropriate execution path."""
    intent = tc["intent"]
    analysis = tc["analysis_type"]
    pitcher = tc["pitcher"]
    batter = tc["batter"]

    if intent == "prediction" and analysis == "reachability":
        return _prediction_reachability(pitcher, batter)

    if intent == "prediction" and analysis == "sensitivity":
        return _prediction_sensitivity(
            pitcher, batter, tc["parameter"], int(tc["delta"]))

    if intent == "strategy" and analysis == "sensitivity":
        return _strategy_sensitivity(
            pitcher, batter,
            tc["from_pitch"], tc["to_pitch"],
            int(tc.get("step", 5)))

    if intent == "strategy" and analysis == "optimize":
        return _strategy_optimize(
            pitcher, batter,
            int(tc.get("step", 5)),
            int(tc.get("min_pct", 5)))

    return _prediction_reachability(pitcher, batter)


def _load_stats(pitcher: str, batter: str) -> dict:
    """Load matchup stats from cache if available, otherwise fetch live."""
    if os.path.exists(CACHE_PATH):
        return load_matchup_json(CACHE_PATH)
    print(f"[Data] Fetching stats: {pitcher} vs {batter}")
    return get_matchup(pitcher, batter)


def _prediction_reachability(pitcher: str, batter: str) -> dict:
    """Single PAT run → return win probabilities."""
    stats = _load_stats(pitcher, batter)
    result = run_pat_on_matchup(stats)
    return {
        "type": "reachability",
        "pitcher": pitcher,
        "batter": batter,
        "pitcherWinProb": result["pitcherWinProb"],
        "batterWinProb": result["batterWinProb"],
    }


def _prediction_sensitivity(pitcher: str, batter: str,
                            parameter: str, delta: int) -> dict:
    """Two PAT runs: base vs one modified parameter."""
    stats = _load_stats(pitcher, batter)

    print("[PAT] Running baseline...")
    base_prob = run_pat_on_matchup(stats)["pitcherWinProb"]

    modified = dict(stats)
    old_val = modified[parameter]
    new_val = max(1, min(99, old_val + delta))
    modified[parameter] = new_val

    snapshot_before = {k: modified[k] for k in modified}
    _fix_complements(parameter, modified, old_val, new_val)

    complement_members = []
    for _gname, members in COMPLEMENT_GROUPS.items():
        if parameter in members:
            complement_members = [m for m in members if m != parameter]
            break

    adjustments = {}
    for k in complement_members:
        adjustments[k] = (snapshot_before[k], modified[k])

    if complement_members:
        print(f"\n    [Auto-adjust] {parameter}: {old_val} → {new_val} "
              f"({delta:+d})")
        print(f"    Complementary parameters proportionally adjusted:")
        for k, (before, after) in adjustments.items():
            diff = after - before
            if diff == 0:
                print(f"      {k}: {before} → {after} "
                      f"(unchanged — share too small to shift)")
            else:
                print(f"      {k}: {before} → {after} ({diff:+d})")
    else:
        print(f"\n    [Adjust] {parameter}: {old_val} → {new_val} "
              f"({delta:+d})")

    print(f"\n[PAT] Running with {parameter} {old_val} → {new_val}...")
    mod_prob = run_pat_on_matchup(modified)["pitcherWinProb"]

    return {
        "type": "prediction_sensitivity",
        "pitcher": pitcher,
        "batter": batter,
        "parameter": parameter,
        "delta": delta,
        "old_value": old_val,
        "new_value": new_val,
        "adjustments": {k: {"from": v[0], "to": v[1]}
                        for k, v in adjustments.items()
                        if v[0] != v[1]},
        "base_pitcherWinProb": round(base_prob, 5),
        "modified_pitcherWinProb": round(mod_prob, 5),
        "change": round(mod_prob - base_prob, 5),
    }


def _strategy_sensitivity(pitcher: str, batter: str,
                          from_pitch: str, to_pitch: str,
                          step: int = 5) -> dict:
    """Pitch-mix shift analysis via strategy_analysis module."""
    matchup = _load_stats(pitcher, batter)
    return run_sensitivity_analysis(
        pitcher, batter, from_pitch, to_pitch, step, matchup=matchup)


def _strategy_optimize(pitcher: str, batter: str,
                       step: int = 5, min_pct: int = 5) -> dict:
    """Full pitch-mix optimisation sweep via strategy_analysis module."""
    matchup = _load_stats(pitcher, batter)
    return run_optimization(
        pitcher, batter, step, min_pct, matchup=matchup)


# ============================================================================
# RESULT SYNTHESIS
# ============================================================================

SYNTHESIS_PROMPT = (
    "You are a baseball coach explaining formal model-checking results to a "
    "player or manager. Provide a clear 3-5 sentence summary using plain "
    "baseball language. Include the exact probabilities from the data — do NOT "
    "round or change any numbers. Give actionable advice where applicable.\n\n"
    "User question: {query}\n"
    "Analysis result:\n{result_json}\n"
)


def synthesize(user_query: str, tc: dict, result: dict) -> str:
    """Turn raw results into coaching advice, using LLM with template fallback."""
    try:
        import google.generativeai as genai
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        model = genai.GenerativeModel("gemini-2.5-flash-lite")
        prompt = SYNTHESIS_PROMPT.format(
            query=user_query,
            result_json=json.dumps(result, indent=2),
        )
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"[Synthesis] LLM failed ({e}), using template fallback")
        return _template_synthesis(tc, result)


def _template_synthesis(tc: dict, result: dict) -> str:
    """Fallback template-based synthesis when LLM synthesis is unavailable."""
    rtype = result.get("type", "")
    mode = result.get("mode", "")

    if rtype == "reachability":
        pw = result.get("pitcherWinProb", 0)
        bw = result.get("batterWinProb", 0)
        return (
            f"Based on formal model checking with real Statcast data: "
            f"{result['pitcher']} gets {result['batter']} out "
            f"{pw:.1%} of the time (strikeout + fielded out), "
            f"while {result['batter']} reaches base {bw:.1%} (walk + hit)."
        )

    if rtype == "prediction_sensitivity":
        readable = (result["parameter"]
                    .replace("P_", "").replace("B_", "")
                    .replace("_", " ").lower())
        change = result["change"]
        adj = result.get("adjustments", {})
        adj_text = ""
        if adj:
            parts = []
            for k, v in adj.items():
                name = (k.replace("P_", "").replace("B_", "")
                        .replace("_", " ").lower())
                parts.append(f"{name} {v['from']} → {v['to']}")
            adj_text = (f" Complementary parameters adjusted "
                        f"proportionally: {', '.join(parts)}.")
        return (
            f"If {readable} changes by {result['delta']:+d} points "
            f"({result['old_value']} → {result['new_value']}): "
            f"pitcher-win probability moves from "
            f"{result['base_pitcherWinProb']:.1%} to "
            f"{result['modified_pitcherWinProb']:.1%} "
            f"({'+' if change > 0 else ''}{change:.2%})."
            f"{adj_text}"
        )

    if mode == "sensitivity":
        return format_sensitivity_result(result)

    if mode == "optimize":
        return format_optimization_result(result)

    return json.dumps(result, indent=2)


# ============================================================================
# MAIN
# ============================================================================

def run_agent(user_query: str) -> str:
    """Full pipeline: query → LLM classify → execute → synthesize → answer."""
    print(f"\n{'='*60}")
    print(f"User: {user_query}")
    print(f"{'='*60}")

    print("\n[1] Classifying query...")
    tc = call_llm(user_query)
    print(f"    intent:        {tc['intent']}")
    print(f"    analysis_type: {tc['analysis_type']}")
    print(f"    pitcher:       {tc['pitcher']}")
    print(f"    batter:        {tc['batter']}")

    query_lower = user_query.lower()
    has_user_pct = bool(re.search(r'\d+\s*%', query_lower))

    if "parameter" in tc:
        print(f"    parameter:     {tc['parameter']}")
        delta_val = tc['delta']
        if not has_user_pct:
            print(f"    delta:         {delta_val}  "
                  f"(default — no % specified in query)")
        else:
            print(f"    delta:         {delta_val}")
    if "from_pitch" in tc:
        print(f"    from_pitch:    {tc['from_pitch']}")
        print(f"    to_pitch:      {tc['to_pitch']}")
        step_val = tc.get('step', 5)
        if not has_user_pct:
            print(f"    step:          {step_val}  "
                  f"(default — no % specified in query)")
        else:
            print(f"    step:          {step_val}")
    if tc.get("analysis_type") == "optimize":
        print(f"    step:          {tc.get('step', 5)}")
        print(f"    min_pct:       {tc.get('min_pct', 5)}")

    print(f"\n[2] Executing: {tc['intent']} + {tc['analysis_type']}...")
    result = execute_tool(tc)

    print("\n[3] Synthesizing response...")
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
        print("\nUsage:")
        print('  python llm_agent.py '
              '"What is the probability Cole gets Judge out?"')
        print('  python llm_agent.py '
              '"Should Cole throw more breaking balls?"')
        print('  python llm_agent.py '
              '"What if Cole improves fastball command by 10%?"')
        print('  python llm_agent.py '
              '"What is the optimal pitch mix for Cole vs Judge?"')
        print("\nRunning demo queries...\n")

        queries = [
            "What is the probability Gerrit Cole gets Aaron Judge out?",
            "Should Cole throw more breaking balls against Judge?",
            "What if Cole's fastball command improves by 10%?",
            "What is the optimal pitch mix for Cole against Judge?",
        ]
        for q in queries:
            run_agent(q)
            print()
