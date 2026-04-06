# Presentation Notes — Baseball At-Bat Formal Verification

**Total time for these 3 presenters: ~6-7 minutes**
(Follows ~3-4 minutes from other presenters covering project context, PAT model, and data layer)

---

## Presenter 1: Prediction (~2 min)

**Core message:** "Given real MLB data, we can compute exact win probabilities using formal verification."

### Slide: What the model computes

- Brief recap: 30 parameters from real Statcast data, pitcher vs batter duel
- Two assertions checked by PAT:
  - `#assert AtBat reaches pitcherWins with prob;`
  - `#assert AtBat reaches batterWins with prob;`
- Probabilities always sum to 1.0

### Demo: single matchup

```sh
python auto_matchup.py "Gerrit Cole" "Aaron Judge" --use-cached
```

Expected output:
```
Final Result: {'pitcherWinProb': 0.72732, 'batterWinProb': 0.27268}
```

"Cole gets Judge out 72.7% of the time — this is exact, not estimated."

### Talking points

- These are not simulations or ML predictions — PAT exhaustively computes the probability from the state machine
- Parameters come from real 2024 Statcast data (previous presenters explained the data pipeline)
- This answers **Part B: Reachability analysis**

### Transition to Presenter 2

> "But knowing the probability isn't enough — a pitcher wants to know how to IMPROVE it. That's where strategy analysis comes in."

---

## Presenter 2: Strategy Analysis (~2 min)

**Core message:** "We can systematically find the optimal pitch mix by varying strategy parameters and re-running formal verification."

### Slide: Two levels of strategy analysis

- **Sensitivity** — test one specific change
  - "What if I shift 5% from fastballs to breaking balls?"
  - Answers: "Does this specific change help?"
- **Optimization** — sweep all legal pitch mixes
  - Tries every valid (fast, break, off) combination
  - Answers: "What is the globally best mix?"

Key point: only the pitch mix (P_FAST_PCT, P_BREAK_PCT, P_OFF_PCT) is varied. All 27 other parameters stay fixed at their real Statcast values.

### Demo: sensitivity

```sh
python strategy_analysis.py sensitivity "Gerrit Cole" "Aaron Judge" --from fast --to break --step 5 --use-cached
```

Walk through output:
- Baseline mix and baseline pitcherWinProb
- Shifted mix (5% from fastballs to breaking balls)
- New pitcherWinProb and the delta
- Whether the shift improves or hurts

### Demo: optimization (pre-computed screenshot recommended — takes minutes to run live)

Show the result:
- Best mix found (e.g. fast=X, break=Y, off=Z)
- Improvement over baseline
- Number of candidates tested (e.g. 171 at step=5, min=5)

### Talking points

- Sensitivity = one perturbation, quick to run
- Optimize = exhaustive sweep, guaranteed to find the best mix within the grid
- Both use the same PAT engine — formal verification, not heuristics
- This answers **Part C: Strategy analysis**

### Transition to Presenter 3

> "These are powerful tools, but they require knowing exact CLI flags and parameter names. What if a baseball coach could just ask questions in plain English?"

---

## Presenter 3: LLM Integration (~2.5 min)

**Core message:** "A natural language interface lets you ask any of the above questions in plain English — and supports richer query types."

### Slide: Architecture

How the LLM agent works:

```
User question (plain English)
        |
        v
  Gemini LLM (classify into JSON)
        |
        v
  Route to pipeline:
    - prediction       --> 1 PAT run
    - proportional     --> 2 PAT runs (adjust rest proportionally)
    - explicit shift   --> 2 PAT runs (shift between two types)
    - optimize         --> N PAT runs (full grid sweep)
        |
        v
  Gemini LLM (synthesize results into coaching advice)
        |
        v
  Plain-English answer
```

Key point: the LLM never guesses probabilities. It classifies the question, runs the formal verification engine, then explains the results.

### Slide: The 4 query types (demo each)

**1. Prediction** (same as Presenter 1, but in English):

```sh
python llm_agent.py "What is the probability Cole gets Judge out?"
```

"This runs the same single PAT verification, but you don't need to know any flags."

**2. Proportional what-if** (new capability not available in the CLI):

```sh
python llm_agent.py "What if Cole increases fastball usage by 5% against Judge?"
```

"I only said increase fastballs — the system proportionally decreased both breaking balls and offspeed to keep the mix summing to 100. If I don't specify a percentage, it defaults to 5%."

**3. Explicit shift** (same as Presenter 2's sensitivity, but in English):

```sh
python llm_agent.py "What if Cole shifts 5% from fastballs to breaking balls against Judge?"
```

"Here I specified both sides — fastballs decrease by 5%, breaking balls increase by 5%, offspeed stays the same. This is exactly what the CLI sensitivity command does."

**4. Optimize** (same as Presenter 2's optimize, but in English):

```sh
python llm_agent.py "What is the optimal pitch mix for Cole against Judge?"
```

"This triggers the full grid sweep — same exhaustive search, but triggered by a natural question."

### Talking points

- Two Gemini calls per query: one to classify, one to synthesize
- The proportional what-if is a new capability beyond the CLI — handles vague questions like "What if Cole throws more fastballs?" by defaulting to 5% and adjusting the rest proportionally
- The explicit shift delegates directly to the strategy analysis module — same code, same results
- All results are reproducible via cached matchup data

### Closing

> "Formal verification gives us exact answers. Strategy analysis finds the best pitch mix. And the LLM layer makes it all accessible — a coach just asks a question and gets precise, data-backed advice."

---

## Quick reference — flow summary

| Presenter | Question answered | What they demo | Time |
|---|---|---|---|
| 1 | Can we predict who wins? | `auto_matchup.py` — one PAT run, exact probabilities | ~2 min |
| 2 | Can we find the best strategy? | `strategy_analysis.py` — sensitivity + optimize | ~2 min |
| 3 | Can a coach just ask? | `llm_agent.py` — all 4 query types via natural language | ~2.5 min |

Each presenter builds on the previous. Presenter 3 wraps everything into a unified interface.

---

## Pre-demo checklist

- [ ] `.env` is configured with `PROJECT_DIR`, `PAT_EXE`, `GEMINI_API_KEY`
- [ ] `data/matchup.json` exists (run export if not)
- [ ] Mono is installed and working
- [ ] Test all demo commands once before presenting
- [ ] Have optimization results screenshot ready (in case live demo is too slow)
