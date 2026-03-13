
# Baseball At-Bat Parametric PCSP# Model — Project Status & Workflow

**Key Files:**
- `baseball_template.pcsp` — Parametric model template (do not edit directly)
- `auto_update_pcsp.py` — Automates model generation for any pitcher/batter matchup
- `data_parser.py` — Fetches real Statcast/Bat Tracking data, computes model parameters
- `matchup.pcsp` — Auto-generated model for a specific matchup (run this in PAT)
- `data/matchup.json` — Stores parameter sets for matchups

---

## Project Status & Workflow (2026)

**Current State:**
- The project is fully automated: you can generate a formal PCSP# model for any MLB pitcher/batter matchup using real 2024 Statcast and Bat Tracking data.
- All model parameters are injected automatically; comments and documentation are consistent across template and generated files.
- The workflow is robust for most MLB players; missing data is handled gracefully with defaults and warnings.
- The codebase is ready for demonstration, extension, and team collaboration.

**How to Use:**
1. **Generate a matchup model:**
  ```sh
  python auto_update_pcsp.py "Pitcher Name" "Batter Name"
  ```
  Example:
  ```sh
  python auto_update_pcsp.py "Gerrit Cole" "Aaron Judge"
  ```
  This creates `matchup.pcsp` with all real probabilities and up-to-date comments.

2. **Run the model in PAT:**
  - Open `matchup.pcsp` in PAT (or your PCSP# toolchain) and run reachability/sensitivity queries as described below.

3. **(Optional) Export parameters for teammates:**
  - Use `data_parser.py` to export a JSON file for use in other tools:
    ```sh
    python -c "import data_parser; data_parser.export_matchup_json('Gerrit Cole', 'Aaron Judge')"
    ```

---

## 1. Overview

This project models a single baseball **at-bat** (pitcher vs batter) using PAT's probabilistic CSP (PCSP#) language, parameterized by real MLB data. The model is fully automated: you can generate a formal model for any matchup with a single command.

### Why baseball works as a 1v1 model

Every at-bat in baseball is a self-contained duel between exactly two players. The pitcher choosing what to throw, and the batter reacting. This is the direct analog of a tennis service game or tiebreaker. Although baseball is a team sport, the atomic competitive unit (the at-bat) is purely 1-vs-1 and has a binary outcome: the pitcher gets the batter out, or the batter reaches base.


### Data Sources & Automation

All model parameters are sourced automatically from three public MLB data sources:

1. **Pitcher's Statcast player page** (Pitch Arsenal section)
  - **Usage %** by pitch type → `P_FAST_PCT`, `P_BREAK_PCT`, `P_OFF_PCT`
  - **Zone %** by pitch type → `P_{TYPE}_ZONE` (complement → `P_{TYPE}_MISS`)
2. **Batter's Statcast player page** (Plate Discipline section)
  - **Swing %** by pitch type → `B_{TYPE}_SWING` (complement → `B_{TYPE}_TAKE`)
  - **Whiff %** by pitch type → `B_{TYPE}_WHIFF` (complement → `B_{TYPE}_CONTACT`)
3. **[Bat Tracking leaderboard — Bat Speed & Contact](https://baseballsavant.mlb.com/leaderboard/bat-tracking)**
  - **Squared-Up % Contact** by pitch type → used to derive `B_{TYPE}_HIT` / `B_{TYPE}_OUT` / `B_{TYPE}_FOUL`

The script `data_parser.py` fetches and computes all 30 model parameters. `auto_update_pcsp.py` injects them into the template, producing a ready-to-run model file with up-to-date comments.

#### Leaderboards NOT used (and why)

| Leaderboard | Why excluded |
|---|---|
| Bat Tracking — Swing Path / Attack Angle | No model parameter for attack angle or swing path tilt |
| Exit Velocity & Barrels | Hard Hit % and Barrels overlap with Squared-Up %; redundant |
| Pitch Movement | Model does not distinguish pitch break/movement |
| Pitch Tempo | Model does not account for timing/pace |
| Spin Direction | Model does not model spin |

These leaderboards contain rich data but adding them would require a more complex model with more parameters. For this project's scope (3 pitch types × swing/whiff/contact outcomes), the 3 sources above are sufficient.

> **Side (L/R):** The batting handedness column visible in leaderboards. Not modelled as a separate parameter — just note the matchup when pulling data.


### Project Mapping

- **Part B (Prediction / Reachability):**
  - "What is the probability Pitcher X gets Batter Y out?"
  - → `#assert AtBat reaches pitcherWins with prob;`
- **Part C (Strategy / Sensitivity):**
  - "What pitch mix should Pitcher X use against Batter Y?"
  - → Vary `P_FAST_PCT` / `P_BREAK_PCT` / `P_OFF_PCT` across combinations, re-run PAT for each, find the mix that maximises `pitcherWins`.

---

## 2. Automated Model Generation Pipeline

**Step 1: Data Retrieval & Parameter Calculation**
- `data_parser.py` fetches all required data for a given pitcher and batter, computes the 30 model parameters, and can export them as a #define block or JSON.

**Step 2: Model File Generation**
- `auto_update_pcsp.py` takes pitcher and batter names as input, calls `data_parser.py`, and injects the parameters into `baseball_template.pcsp`.
- The output is `matchup.pcsp`, a fully documented, ready-to-run model for the selected matchup.

**Step 3: Model Checking**
- Open `matchup.pcsp` in PAT or your PCSP# toolchain.
- Run reachability or sensitivity queries as described below.

**Manual and Automated Workflows**
- You can still call `data_parser.py` directly for custom data extraction, debugging, or exporting JSON for teammates.
- The automated pipeline is robust for most MLB players; if data is missing, defaults and warnings are used.

---

## 2. Hierarchical Pitch Decision Tree

Each pitch follows a realistic multi-stage process that maps directly to bat tracking data:

```
Pitch type chosen (pitcher's strategy)
  │
  ├── Batter TAKES (does not swing)
  │     ├── In strike zone  → Called Strike  → HandleStrike
  │     └── Out of zone     → Ball           → HandleBall
  │
  └── Batter SWINGS
        ├── WHIFF (misses completely: Sword / swing-and-miss) → Swinging Strike → HandleStrike
        └── CONTACT
              ├── Foul ball             → HandleFoul
              ├── Fielded out (weak)    → HandleInPlayOut  (pitcher wins)
              └── Base hit (squared-up) → HandleHit        (batter wins)
```

This tree is replicated for each pitch type (fastball / breaking / offspeed), each with its own probability weights from the batter's data.

---

## 3. Parameter Reference

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

### Batter Skill — Whiff Rate (6) — from Sword% / whiff rate by pitch type

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

## 4. Mapping Bat Tracking Data to Model Parameters

The Baseball Savant bat tracking leaderboard can be filtered by **pitch type** (fastball / breaking / offspeed). For a specific batter, set the pitch type filter and read the metrics. Here is how each model parameter is derived:

### 4.1 Swing Rate (`B_{TYPE}_SWING`)

**Source:** Statcast "Swing %" for the batter, filtered by pitch type. Available on the batter's Statcast player page or via Baseball Savant search API.

**Complement:** `B_{TYPE}_TAKE = 100 - B_{TYPE}_SWING`

### 4.2 Whiff Rate (`B_{TYPE}_WHIFF`)

**Source:** Batter's Statcast player page → Plate Discipline → Whiff % (= swinging strikes / total swings), filtered by pitch type.

**Complement:** `B_{TYPE}_CONTACT = 100 - B_{TYPE}_WHIFF`

### 4.3 Contact Quality (`B_{TYPE}_FOUL` / `OUT` / `HIT`)

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

### 4.4 Zone Rate (`P_{TYPE}_ZONE`)

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

## 5. How to Inject Parameters

```python
import re

template = open("baseball_template.pcsp").read()
for param, value in stats.items():
    template = re.sub(
        rf"#define {param} \d+;",
        f"#define {param} {value};",
        template
    )
open("matchup.pcsp", "w").write(template)
```

---

## 6. Assertions

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

## 7. State Variables

| Variable | Description | Range |
|----------|-------------|-------|
| `balls` | Ball count in the at-bat | Starts 0, max 3 before walk |
| `strikes` | Strike count in the at-bat | Starts 0, max 2 before strikeout |
| `result` | Outcome flag | 0 = in progress, 1 = pitcher wins, 2 = batter wins |

---

## 8. Process Structure

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

## 9. Example Use Cases

**"What is the probability that Gerrit Cole gets Aaron Judge out?"**
1. Fetch Judge's bat tracking data filtered by fastball/breaking/offspeed
2. Fetch Cole's zone% by pitch type
3. Compute `B_*` parameters from bat tracking metrics (Section 4)
4. Set `P_*` from Cole's typical pitch mix
5. PAT outputs: `pitcherWins = 0.68`, `batterWins = 0.32`

**"What pitch mix should Cole use against Judge?"**
1. Fix all skill parameters (from data)
2. Sweep `P_FAST_PCT` from 20–70 in steps of 5
3. For each fastball%, sweep `P_BREAK_PCT`, derive `P_OFF_PCT = 100 - rest`
4. Run PAT for each combination
5. Find the mix that maximises `pitcherWins`
6. Output: "Throw 35% fastballs, 40% breaking, 25% offspeed for a 71.2% out rate (up from 68.0% with your current mix)"

**"Judge has a 38° swing path tilt — how do I exploit that?"**
1. A steep tilt means more whiffs on certain pitch types
2. The data shows higher Sword% vs breaking balls for Judge
3. Model confirms: increasing breaking ball percentage from 30% to 45% raises `pitcherWins` from 0.68 to 0.72

---


## 10. Data Extraction Workflow (Automated)

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

| Model Parameter   | Pitch Types Included                                                                 |
|-------------------|-------------------------------------------------------------------------------------|
| `P_FAST_PCT`      | Four-Seam Fastball (FF), Sinker (SI), Cutter (FC), Two-Seam Fastball (FT, if listed) |
| `P_BREAK_PCT`     | Slider (SL), Curveball (CU), Sweeper (ST), Knuckle Curve (KC)                        |
| `P_OFF_PCT`       | Changeup (CH), Splitter (FS or SP), Forkball (FO), Eephus (EP, if listed), others    |

---

## 11. Project Progress & Next Steps

- **Template and automation complete:** The PCSP# template is finalized and well-commented. All scripts are robust and ready for use.
- **Comment/documentation consistency:** All generated files (`matchup.pcsp`) now match the template in comments and structure.
- **Error handling:** The pipeline handles missing data gracefully and warns the user if defaults are used.
- **Ready for extension:** The project is ready for further work (e.g., LLM integration, sensitivity analysis, or new sports).

---

**For any questions or to extend the project, see the code comments in `data_parser.py` and `auto_update_pcsp.py`.**
