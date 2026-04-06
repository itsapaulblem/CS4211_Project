# Usage Guide

All commands assume you are in the project root directory with dependencies installed and `.env` configured (see [README.md](README.md) for setup).

---

## Quick Start

**1. Generate and verify a matchup:**

```sh
python auto_matchup.py "Gerrit Cole" "Aaron Judge"
```

**2. Run a strategy analysis:**

```sh
python strategy_analysis.py sensitivity "Gerrit Cole" "Aaron Judge" --from fast --to break --step 5
```

**3. Ask a question in plain English (LLM agent):**

```sh
python llm_agent.py "What is the probability Cole gets Judge out?"
```

---

## Caching Matchup Data

By default, every run fetches live data from the Statcast API. Since API data can change between runs (even for past seasons), results may not be reproducible.

To lock in a set of parameters for consistent results:

**Step 1: Export the matchup once:**

```sh
python -c "from data_parser import export_matchup_json; export_matchup_json('Gerrit Cole', 'Aaron Judge')"
```

This saves parameters to `data/matchup.json`.

**Step 2: Use cached data in subsequent runs:**

```sh
# auto_matchup
python auto_matchup.py "Gerrit Cole" "Aaron Judge" --use-cached

# strategy analysis
python strategy_analysis.py sensitivity "Gerrit Cole" "Aaron Judge" --from fast --to break --use-cached
python strategy_analysis.py optimize "Gerrit Cole" "Aaron Judge" --use-cached

# LLM agent (automatically uses data/matchup.json if it exists)
python llm_agent.py "What is the probability Cole gets Judge out?"
```

To refresh the data (re-fetch from Statcast), either delete `data/matchup.json` or run the export command again.

---

## `auto_matchup.py` — Single Matchup

Generates `matchup.pcsp` from real Statcast data and runs PAT once. The simplest way to get win probabilities.

```sh
python auto_matchup.py "Pitcher Name" "Batter Name"
```

```sh
python auto_matchup.py "Gerrit Cole" "Aaron Judge"
python auto_matchup.py "Spencer Strider" "Mookie Betts"
```

---

## `strategy_analysis.py` — Pitch-Mix Analysis

Two sub-commands: `sensitivity` and `optimize`. Only the pitch-mix parameters (`P_FAST_PCT`, `P_BREAK_PCT`, `P_OFF_PCT`) are varied; all other matchup parameters stay at their real Statcast values.

### `sensitivity` — Test one pitch-mix shift

Moves `--step` percentage points from one pitch type to another, compares against the baseline.

```sh
python strategy_analysis.py sensitivity "Pitcher" "Batter" --from <type> --to <type> [--step N]
```

| Flag | Required | Default | Description |
|------|----------|---------|-------------|
| `--from` | Yes | — | Pitch type to reduce (`fast`, `break`, or `off`) |
| `--to` | Yes | — | Pitch type to increase (`fast`, `break`, or `off`) |
| `--step` | No | 5 | Percentage points to shift |

```sh
# Move 5% from fastballs to breaking balls
python strategy_analysis.py sensitivity "Gerrit Cole" "Aaron Judge" --from fast --to break --step 5

# Move 10% from offspeed to fastballs
python strategy_analysis.py sensitivity "Gerrit Cole" "Aaron Judge" --from off --to fast --step 10

# Move 3% from breaking to offspeed
python strategy_analysis.py sensitivity "Gerrit Cole" "Aaron Judge" --from break --to off --step 3
```

**All 6 possible shift directions** (with default step=5):

```sh
python strategy_analysis.py sensitivity "Gerrit Cole" "Aaron Judge" --from fast --to break
python strategy_analysis.py sensitivity "Gerrit Cole" "Aaron Judge" --from fast --to off
python strategy_analysis.py sensitivity "Gerrit Cole" "Aaron Judge" --from break --to fast
python strategy_analysis.py sensitivity "Gerrit Cole" "Aaron Judge" --from break --to off
python strategy_analysis.py sensitivity "Gerrit Cole" "Aaron Judge" --from off --to fast
python strategy_analysis.py sensitivity "Gerrit Cole" "Aaron Judge" --from off --to break
```

### `optimize` — Sweep all legal pitch mixes

Tests every valid `(fast, break, off)` combination on a grid and reports the mix that maximises pitcher win probability.

```sh
python strategy_analysis.py optimize "Pitcher" "Batter" [--step N] [--min-pct N]
```

| Flag | Required | Default | Description |
|------|----------|---------|-------------|
| `--step` | No | 5 | Grid step size in percentage points |
| `--min-pct` | No | 5 | Minimum percentage each pitch type must have |

```sh
# Standard sweep (step=5, min=5) — tests ~171 combinations
python strategy_analysis.py optimize "Gerrit Cole" "Aaron Judge"

# Fast demo (step=10, min=10) — tests ~36 combinations
python strategy_analysis.py optimize "Gerrit Cole" "Aaron Judge" --step 10 --min-pct 10

# Fine-grained (step=1, min=5) — very thorough but slow
python strategy_analysis.py optimize "Gerrit Cole" "Aaron Judge" --step 1 --min-pct 5

# Allow extreme mixes (min=1) — includes near-100% single-pitch mixes
python strategy_analysis.py optimize "Gerrit Cole" "Aaron Judge" --step 5 --min-pct 1

# Conservative mix bounds (min=20) — all pitch types stay above 20%
python strategy_analysis.py optimize "Gerrit Cole" "Aaron Judge" --step 5 --min-pct 20
```

**Approximate candidate counts by settings:**

| `--step` | `--min-pct` | Candidates | Speed |
|----------|-------------|------------|-------|
| 10 | 10 | ~36 | Fast (~2 min) |
| 5 | 10 | ~66 | Moderate (~4 min) |
| 5 | 5 | ~171 | Moderate (~10 min) |
| 1 | 5 | ~4186 | Slow (~3+ hours) |

---

## `llm_agent.py` — Natural Language Agent

Ask questions in plain English. Gemini classifies the query, runs the appropriate analysis pipeline, and synthesizes the results into coaching advice.

**Prerequisites:** Set `GEMINI_API_KEY` in your `.env` file (see `.env.example`).

```sh
python llm_agent.py "<question>"
```

Four types of queries are supported:

| Query type | Example | What happens |
|---|---|---|
| **Prediction** | "What is the probability Cole gets Judge out?" | 1 PAT run |
| **What-if** | "What if Cole's fastball command improves by 10%?" | 2 PAT runs |
| **Pitch-mix shift** | "Should Cole throw more breaking balls?" | 2 PAT runs |
| **Optimal mix** | "What is the optimal pitch mix for Cole vs Judge?" | N PAT runs |

### Prediction queries (1 PAT run)

Ask about base win probabilities for any matchup.

```sh
python llm_agent.py "What is the probability Gerrit Cole gets Aaron Judge out?"
python llm_agent.py "Who wins the Cole vs Judge at-bat?"
python llm_agent.py "What are the win odds for Spencer Strider against Mookie Betts?"
```

### What-if queries (2 PAT runs)

Test the effect of changing a pitch-mix parameter. The agent automatically adjusts complement parameters to keep sums valid.

```sh
python llm_agent.py "What if Cole throws 10% more fastballs against Judge?"
python llm_agent.py "What if Cole reduces his offspeed usage by 5%?"
python llm_agent.py "What happens if Cole increases breaking balls by 10% against Judge?"
```

### Pitch-mix shift queries (2 PAT runs)

Test shifting percentage points between pitch types. Delegates to `strategy_analysis.py` sensitivity mode.

```sh
python llm_agent.py "Should Cole throw more breaking balls against Judge?"
python llm_agent.py "Should Cole throw fewer fastballs and more offspeed?"
python llm_agent.py "What happens if Cole shifts 10% from fastballs to breaking balls against Judge?"
python llm_agent.py "Would Cole benefit from throwing more offspeed to Judge?"
```

### Optimal pitch-mix queries (N PAT runs)

Finds the best pitch distribution. Delegates to `strategy_analysis.py` optimize mode. This is the slowest query type.

```sh
python llm_agent.py "What is the optimal pitch mix for Cole against Judge?"
python llm_agent.py "Find the best pitch distribution for Strider vs Betts"
python llm_agent.py "Optimize Cole's pitch selection against Judge"
```

### Demo mode (no arguments)

Runs all 4 query types with example data:

```sh
python llm_agent.py
```

---

## `data_parser.py` — Data Retrieval

Fetch Statcast data and compute model parameters. Typically called indirectly by the other scripts.

```sh
# Print matchup parameters for Cole vs Judge (default)
python data_parser.py

# Export to JSON (from Python)
python -c "from data_parser import export_matchup_json; export_matchup_json('Gerrit Cole', 'Aaron Judge')"
```
