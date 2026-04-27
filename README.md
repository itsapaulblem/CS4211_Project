
# Baseball At-Bat Parametric PCSP# Model — Project Status & Workflow

**Key Files:**
- `baseball_template.pcsp` — Parametric model template (do not edit directly)
- `auto_matchup.py` — Generates matchup model and runs PAT for a pitcher/batter pair
- `data_parser.py` — Fetches real Statcast/Bat Tracking data, computes model parameters
- `strategy_analysis.py` — Pitch-mix sensitivity analysis and optimisation (Part C)
- `llm_agent.py` — Natural language agent powered by Gemini (LLM integration)
- `matchup.pcsp` — Auto-generated model for a specific matchup (run this in PAT)
- **[USAGE.md](USAGE.md)** — CLI command reference and usage examples

---

## Project Status & Workflow (2026)

**Current State:**
- The project is fully automated: you can generate a formal PCSP# model for any MLB pitcher/batter matchup using real 2024 Statcast and Bat Tracking data.
- All model parameters are injected automatically; comments and documentation are consistent across template and generated files.
- The workflow is robust for most MLB players; missing data is handled gracefully with defaults and warnings.
- The codebase is ready for demonstration, extension, and team collaboration.

**For command-line usage and examples, see [USAGE.md](USAGE.md).**

---

## 1. Setup

### 1. Install dependencies
```sh
pip install -r requirements.txt
```

### 2. Configure your environment
Copy the example env file and fill in your paths:
```sh
cp .env.example .env
```

Then open `.env` and update the two paths:
```
PROJECT_DIR=C:\path\to\CS4211_Project        # Windows
PAT_EXE=C:\path\to\MONO-PAT-v3.6.0\PAT3.Console.exe
```

For macOS/Linux:
```
PROJECT_DIR=/Users/yourname/path/to/CS4211_Project
PAT_EXE=/Users/yourname/path/to/MONO-PAT-v3.6.0/PAT3.Console.exe
```

### 3. Install PAT (MONO-PAT v3.6.0)
- Download **MONO-PAT v3.6.0**
- Extract it and note the path to `PAT3.Console.exe` — this is your `PAT_EXE`
- **Windows (recommended, CLI-only): run PAT via Mono on Windows**
  - Install **Mono for Windows** (this is required for `PAT3.Console.exe` to run reliably)
    - Download: `https://www.mono-project.com/download/stable/`
  - Verify Mono is installed by checking that this exists:
    - `C:\Program Files\Mono\bin\mono.exe`
  - Your scripts will run PAT like:
    - `mono PAT3.Console.exe -pcsp matchup.pcsp matchup_output.txt`
- **Windows (alternative): run PAT via WSL + Mono**
  - Install WSL: `wsl --install`
  - In Ubuntu/WSL: `sudo apt update && sudo apt install -y mono-complete`
- **macOS/Linux:** Install Mono directly (`brew install mono` on macOS, `sudo apt install mono-complete` on Linux)

### 4. Verify setup
```sh
python auto_matchup.py "Gerrit Cole" "Aaron Judge"
```
You should see probabilities printed at the end.

For strategy analysis and LLM agent usage, see [USAGE.md](USAGE.md).

---

## Windows notes (PAT CLI setup)

If you're on Windows and using this repo's automation, the **simplest reliable setup** is:

- **Install Mono for Windows**
- Set `PAT_EXE` to your extracted `PAT3.Console.exe` (MONO-PAT v3.6.0)

`auto_matchup.py` will:
- **delete** `matchup_output.txt` before each run (to prevent stale results)
- run PAT via `mono.exe` (no WSL required)

If you previously saw inconsistent probabilities, it was usually because PAT didn't run and an old `matchup_output.txt` got reused. The current runner prevents that.

## 2. Overview

This project models a single baseball **at-bat** (pitcher vs batter) using PAT's probabilistic CSP (PCSP#) language, parameterized by real MLB data. The model is fully automated: you can generate a formal model for any matchup with a single command.

### Why baseball works as a 1v1 model

Every at-bat in baseball is a self-contained duel between exactly two players. The pitcher choosing what to throw, and the batter reacting. This is the direct analog of a tennis service game or tiebreaker. Although baseball is a team sport, the atomic competitive unit (the at-bat) is purely 1-vs-1 and has a binary outcome: the pitcher gets the batter out, or the batter reaches base.


### Data Sources & Automation

All model parameters are sourced automatically from two public MLB data sources:

1. **MLB Statcast via `pybaseball`**
   - Pitcher pitch mix → `P_FAST_PCT`, `P_BREAK_PCT`, `P_OFF_PCT`
   - Pitcher zone accuracy → `P_{TYPE}_ZONE` / `P_{TYPE}_MISS`
   - Batter swing rate → `B_{TYPE}_SWING` / `B_{TYPE}_TAKE`
   - Batter whiff/contact rate → `B_{TYPE}_WHIFF` / `B_{TYPE}_CONTACT`

2. **Baseball Savant Bat Tracking leaderboard**
   - Squared-Up % Contact → used to derive `B_{TYPE}_HIT`, `B_{TYPE}_OUT`, and `B_{TYPE}_FOUL`

The script `data_parser.py` fetches and computes all 30 model parameters. `auto_matchup.py`, `strategy_analysis.py`, and `llm_agent.py` then inject these parameters into `baseball_template.pcsp` to generate matchup-specific PCSP# models and run PAT.

#### Leaderboards NOT used (and why)

| Leaderboard | Why excluded |
|---|---|
| Bat Tracking — Swing Path / Attack Angle | No model parameter for attack angle or swing path tilt |
| Exit Velocity & Barrels | Hard Hit % and Barrels overlap with Squared-Up %; redundant |
| Pitch Movement | Model does not distinguish pitch break/movement |
| Pitch Tempo | Model does not account for timing/pace |
| Spin Direction | Model does not model spin |

These leaderboards contain rich data but adding them would require a more complex model with more parameters. For this project's scope (3 pitch types × swing/whiff/contact outcomes), the 2 sources above are sufficient.

> **Side (L/R):** The batting handedness column visible in leaderboards. Not modelled as a separate parameter — just note the matchup when pulling data.


### Project Mapping

- **Part B — Prediction / Reachability**
  - Question: “What is the probability Pitcher X gets Batter Y out?”
  - Method: generate one matchup-specific PCSP# model and verify:
    - `#assert AtBat reaches pitcherWins with prob;`
    - `#assert AtBat reaches batterWins with prob;`

- **Part C — Strategy / Sensitivity and Optimisation**
  - Sensitivity: compare a baseline model against a modified pitch mix or one-parameter change.
  - Optimisation: sweep valid `P_FAST_PCT` / `P_BREAK_PCT` / `P_OFF_PCT` combinations and select the mix that maximises `pitcherWins`.
---

## 3. Automated Model Generation Pipeline

**Step 1: Data Retrieval & Parameter Calculation**
- `data_parser.py` fetches all required data for a given pitcher and batter, computes the 30 model parameters, and can export them as a #define block or JSON.

**Step 2: Model File Generation**
- `auto_matchup.py` and `strategy_analysis.py` inject the computed parameters into `baseball_template.pcsp`.
- The output is `matchup.pcsp`, a generated model for the selected matchup.

**Step 3: Model Checking**
- The scripts invoke PAT automatically through the configured `PAT_EXE`.
- The generated `matchup.pcsp` can also be opened manually in PAT for inspection.

**Manual and Automated Workflows**
- You can still call `data_parser.py` directly for custom data extraction, debugging, or exporting JSON for teammates.
- The automated pipeline is robust for most MLB players; if data is missing, defaults and warnings are used.

---

## 4. Hierarchical Pitch Decision Tree

Each pitch follows a realistic multi-stage process that maps directly to bat tracking data:

```
Pitch type chosen (pitcher's strategy)
  │
  ├── Batter TAKES (does not swing)
  │     ├── In strike zone  → Called Strike  → HandleStrike
  │     └── Out of zone     → Ball           → HandleBall
  │
  └── Batter SWINGS
        ├── WHIFF (swing-and-miss) → Swinging Strike → HandleStrike
        └── CONTACT
              ├── Foul ball             → HandleFoul
              ├── Fielded out (weak)    → HandleInPlayOut  (pitcher wins)
              └── Base hit (squared-up) → HandleHit        (batter wins)
```

This tree is replicated for each pitch type (fastball / breaking / offspeed), each with its own probability weights from the batter's data.

---

## 5. Parameter Reference

### Strategy Parameters (3) — what Part C varies

| Parameter | Description | Constraint |
|-----------|-------------|------------|
| `P_FAST_PCT` | % fastballs in pitch mix | Sum of 3 = 100 |
| `P_BREAK_PCT` | % breaking balls in pitch mix | |
| `P_OFF_PCT` | % offspeed pitches in pitch mix | |

### Pitcher Skill (6) — from pitcher's Statcast Zone% by pitch type

| Parameter | Description | Constraint |
|-----------|-------------|------------|
| `P_FAST_ZONE` / `P_FAST_MISS` | Fastball in-zone rate | Pair sums to 100 |
| `P_BREAK_ZONE` / `P_BREAK_MISS` | Breaking in-zone rate | Pair sums to 100 |
| `P_OFF_ZONE` / `P_OFF_MISS` | Offspeed in-zone rate | Pair sums to 100 |

### Batter Skill — Swing Rate (6) — from batter's Swing% by pitch type

| Parameter | Description | Constraint |
|-----------|-------------|------------|
| `B_FAST_SWING` / `B_FAST_TAKE` | Swing rate vs fastball | Pair sums to 100 |
| `B_BREAK_SWING` / `B_BREAK_TAKE` | Swing rate vs breaking | Pair sums to 100 |
| `B_OFF_SWING` / `B_OFF_TAKE` | Swing rate vs offspeed | Pair sums to 100 |

### Batter Skill — Whiff Rate (6) — from whiff rate by pitch type

| Parameter | Description | Constraint |
|-----------|-------------|------------|
| `B_FAST_WHIFF` / `B_FAST_CONTACT` | Whiff rate vs fastball | Pair sums to 100 |
| `B_BREAK_WHIFF` / `B_BREAK_CONTACT` | Whiff rate vs breaking | Pair sums to 100 |
| `B_OFF_WHIFF` / `B_OFF_CONTACT` | Whiff rate vs offspeed | Pair sums to 100 |

### Batter Skill — Contact Quality (9) — from bat tracking by pitch type

| Parameter | Description | Constraint |
|-----------|-------------|------------|
| `B_FAST_FOUL` / `B_FAST_OUT` / `B_FAST_HIT` | Contact outcome vs fastball | Triple sums to 100 |
| `B_BREAK_FOUL` / `B_BREAK_OUT` / `B_BREAK_HIT` | Contact outcome vs breaking | Triple sums to 100 |
| `B_OFF_FOUL` / `B_OFF_OUT` / `B_OFF_HIT` | Contact outcome vs offspeed | Triple sums to 100 |

All values are integers 1–99 representing percentages.

---

## 6. Mapping Bat Tracking Data to Model Parameters

The Baseball Savant bat tracking leaderboard can be filtered by **pitch type** (fastball / breaking / offspeed). For a specific batter, set the pitch type filter and read the metrics. Here is how each model parameter is derived:

### 6.1 Swing Rate (`B_{TYPE}_SWING`)

**Source:** Statcast "Swing %" for the batter, filtered by pitch type. Available on the batter's Statcast player page or via Baseball Savant search API.

**Complement:** `B_{TYPE}_TAKE = 100 - B_{TYPE}_SWING`

### 6.2 Whiff Rate (`B_{TYPE}_WHIFF`)

**Source:** Batter's Statcast player page → Plate Discipline → Whiff % (= swinging strikes / total swings), filtered by pitch type.

**Complement:** `B_{TYPE}_CONTACT = 100 - B_{TYPE}_WHIFF`

### 6.3 Contact Quality (`B_{TYPE}_FOUL` / `OUT` / `HIT`)

These three must sum to 100 for each pitch type.

**Source:** Squared-Up % Contact from the [Bat Tracking leaderboard](https://baseballsavant.mlb.com/leaderboard/bat-tracking), filtered by pitch type. This is the only leaderboard metric the model needs.

**HIT rate:**

$$\text{HIT} \approx \text{Squared-Up \% Contact}$$

Squared-up contact (bat speed ≥ 80% of pitch speed, good barrel-to-ball angle) produces line drives and hard-hit balls — the batted balls most likely to become hits.

> Example: If Squared-Up % Contact vs breaking balls = 22%, set `B_BREAK_HIT = 22`.

**OUT rate:**

$$\text{OUT} \approx (100 - \text{Squared-Up \%}) \times 0.7$$

Non-squared-up contact produces weak grounders, popups, and routine fly balls. Roughly 70% of these become outs (the rest are fouls). The 0.7 factor is an estimate — adjust if needed.

> Example: (100 − 22) × 0.7 = 54.6 → round to `B_BREAK_OUT = 55`.

**FOUL rate (remainder):**

$$\text{FOUL} = 100 - \text{HIT} - \text{OUT}$$

> Example: 100 − 22 − 55 = 23 → `B_BREAK_FOUL = 23`.

### 6.4 Zone Rate (`P_{TYPE}_ZONE`)

**Source:** Pitcher's "Zone %" from Statcast, filtered by pitch type. This is a **pitcher** property — how often they locate in the zone.

**Complement:** `P_{TYPE}_MISS = 100 - P_{TYPE}_ZONE`

### Summary — Data Source → Model Parameter

| Source | Metric | Model Parameter(s) | Read or Derived? |
|---|---|---|---|
| Pitcher's Statcast page | Usage % | `P_FAST_PCT`, `P_BREAK_PCT`, `P_OFF_PCT` | Direct read |
| Pitcher's Statcast page | Zone % | `P_{TYPE}_ZONE` / `P_{TYPE}_MISS` | Direct read |
| Batter's Statcast page | Swing % | `B_{TYPE}_SWING` / `B_{TYPE}_TAKE` | Direct read |
| Batter's Statcast page | Whiff % | `B_{TYPE}_WHIFF` / `B_{TYPE}_CONTACT` | Direct read |
| Bat Tracking leaderboard | Squared-Up % Contact | `B_{TYPE}_HIT` / `B_{TYPE}_OUT` / `B_{TYPE}_FOUL` | Derived (Section 4.3) |

---

## 7. How Parameters Are Injected

The PCSP# template uses placeholders such as `{{P_FAST_PCT}}`, `{{B_FAST_SWING}}`, and `{{B_BREAK_HIT}}`. The Python scripts replace each placeholder with the corresponding integer percentage from the matchup dictionary.

```python
with open("baseball_template.pcsp", "r") as f:
    content = f.read()

for key, val in matchup.items():
    content = content.replace(f"{{{{{key}}}}}", str(val))

with open("matchup.pcsp", "w") as f:
    f.write(content)
```

---

## 8. Assertions

```
#assert AtBat reaches pitcherWins with prob;
```
→ Probability that the pitcher gets the batter out (strikeout + in-play out)

```
#assert AtBat reaches batterWins with prob;
```
→ Probability that the batter reaches base (walk + base hit)

These two sum to 1.0.

---

## 9. State Variables

| Variable | Description | Range |
|----------|-------------|-------|
| `balls` | Ball count in the at-bat | Starts 0, max 3 before walk |
| `strikes` | Strike count in the at-bat | Starts 0, max 2 before strikeout |
| `result` | Outcome flag | 0 = in progress, 1 = pitcher wins, 2 = batter wins |

---

## 10. Process Structure

```
AtBat → Pitch
  │→ pcase: FastPitch / BreakPitch / OffPitch
    │→ pcase: {TYPE}Swing / {TYPE}Take

    {TYPE}Take → pcase:
      P_{TYPE}_ZONE  → called_strike → HandleStrike
      P_{TYPE}_MISS  → ball          → HandleBall

    {TYPE}Swing → pcase:
      B_{TYPE}_WHIFF   → whiff → HandleStrike
      B_{TYPE}_CONTACT → {TYPE}Contact

    {TYPE}Contact → pcase:
      B_{TYPE}_FOUL → foul → HandleFoul
      B_{TYPE}_OUT  → out  → HandleInPlayOut  (pitcher wins)
      B_{TYPE}_HIT  → hit  → HandleHit        (batter wins)

HandleStrike:
  strikes < 2  → strikes + 1 → Pitch
  strikes >= 2 → strikeout   → Skip (pitcher wins)

HandleBall:
  balls < 3  → balls + 1 → Pitch
  balls >= 3 → walk       → Skip (batter wins)

HandleFoul:
  strikes < 2  → strikes + 1 → Pitch
  strikes >= 2 → no change   → Pitch  (foul cannot strikeout)
```

---

## 11. Example Use Cases

**"What is the probability that Gerrit Cole gets Aaron Judge out?"**
1. Fetch and compute the 30 matchup parameters.
2. Generate `matchup.pcsp`.
3. Run PAT on the reachability assertions.
4. Return `pitcherWinProb` and `batterWinProb`.

**"Should Cole shift 5% from fastballs to breaking balls against Judge?"**
1. Generate and verify the baseline model.
2. Modify the pitch mix by moving 5 percentage points from fastball to breaking ball.
3. Generate and verify the modified model.
4. Compare the two pitcher-win probabilities and report the delta.

**"What is the optimal pitch mix for Cole against Judge?"**
1. Fix all non-pitch-mix parameters from Statcast-derived data.
2. Generate all legal pitch-mix candidates under the configured grid.
3. Run PAT once per candidate.
4. Return the candidate with the highest `pitcherWinProb`.
---


## 12. Data Extraction Workflow (Automated)

**You do NOT need to collect data manually!**

The scripts handle all data retrieval, parameter calculation, and model file generation. For reference, here’s how the mapping works under the hood:

1. **Pitcher’s Statcast page** → Pitch Arsenal section
  - Usage % per pitch type → `P_FAST_PCT`, `P_BREAK_PCT`, `P_OFF_PCT`
  - Zone % per pitch type → `P_{TYPE}_ZONE` (complement = `P_{TYPE}_MISS`)
2. **Batter’s Statcast page** → Plate Discipline section
  - Swing % per pitch type → `B_{TYPE}_SWING` (complement = `B_{TYPE}_TAKE`)
  - Whiff % per pitch type → `B_{TYPE}_WHIFF` (complement = `B_{TYPE}_CONTACT`)
3. **Bat Tracking leaderboard**
  - Squared-Up % Contact → derive `B_{TYPE}_HIT`, `B_{TYPE}_OUT`, `B_{TYPE}_FOUL`

Pitch type classification for model parameters:

| Model Parameter | Pitch Types Included |
|---|---|
| `P_FAST_PCT` | Four-seam fastball (FF), sinker (SI), two-seam fastball (FT), generic fastball (FA), cutter (FC) |
| `P_BREAK_PCT` | Slider (SL), curveball (CU), knuckle-curve (KC), slow curve (CS), sweeper (ST), slurve (SV) |
| `P_OFF_PCT` | Changeup (CH), splitter (FS), forkball (FO), screwball (SC) |

---

## 13. Summary of Current Scope and Extension Points

### Summary of Current Scope

The current implementation supports:

- automatic retrieval of 2024 MLB Statcast and Bat Tracking data;
- generation of a matchup-specific `matchup.pcsp` file from `baseball_template.pcsp`;
- PAT reachability analysis for `pitcherWins` and `batterWins`;
- pitch-mix sensitivity analysis through explicit shifts and one-sided proportional adjustments between fastball, breaking ball, and offspeed usage;
- pitch-mix optimisation through grid search over valid pitch distributions;
- natural-language query handling through `llm_agent.py`.

### Known Scope Boundaries

The model currently represents a single at-bat only. It does not model full innings, runners on base, score state, pitcher fatigue, pitch sequencing, or count-dependent pitch selection. Pitch types are also grouped into three broad categories: fastball, breaking ball, and offspeed.

### Suggested Extension Points

Future extensions can build on the current pipeline by:

- adding count-dependent pitch mix, so pitch selection changes based on balls and strikes;
- adding handedness or platoon effects;
- expanding optimisation beyond pitch mix to parameters such as zone accuracy, whiff rate, or contact quality;
- chaining multiple at-bats to model inning-level outcomes;
- adapting the same data → PCSP# model → PAT → LLM architecture to another sport.

For command examples, see [USAGE.md](USAGE.md).
