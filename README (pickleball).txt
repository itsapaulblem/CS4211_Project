================================================================================
  PART A — PICKLEBALL DOUBLES PARAMETRIC PCSP# MODEL  (Documentation)
================================================================================

FILE:  pickleball_template.pcsp

================================================================================
1. OVERVIEW
================================================================================

This model captures a pickleball DOUBLES game (2 vs 2) using PAT's
probabilistic CSP (PCSP#) language.

Key pickleball doubles rules modelled:
  - SIDE-OUT SCORING: only the serving team can score a point
  - TWO SERVERS PER TEAM: Server 1 serves first.  If the serving
    team loses a rally, Server 2 takes over.  If Server 2's team
    also loses, it is a side out to the other team.
  - OPENING EXCEPTION: the game starts with the first serving team
    at Server 2 (only one serve before the first side out)
  - Single serve attempt per server (fault = next server or side out)

Point flow per rally:
    SERVE  ->  RETURN  ->  THIRD SHOT  ->  RALLY

Pickleball-specific concepts modelled:
  - Underhand serve with DEEP / WIDE / MID placement
  - Third shot: DROP (soft dink into kitchen) vs DRIVE (hard topspin)
  - Rally phase (net play / dinking battle / speed-ups)

Skills are modelled per-TEAM (not per-individual).  Each team's
parameters represent the combined ability of that pair.  To model
individual server differences, split T1 serve params into T1S1_ /
T1S2_ variants.


================================================================================
2. PARAMETER REFERENCE (29 independent, 46 #define lines total)
================================================================================

STRATEGY PARAMETERS (10) — what Part C varies:
  T1_SERVE_DEEP_PCT / WIDE_PCT / MID_PCT   T1 serve placement split (sum=100)
  T2_SERVE_DEEP_PCT / WIDE_PCT / MID_PCT   T2 serve placement split (sum=100)
  T1_THIRD_DROP_PCT / DRIVE_PCT             T1 third-shot choice  (sum=100)
  T2_THIRD_DROP_PCT / DRIVE_PCT             T2 third-shot choice  (sum=100)

SKILL PARAMETERS (17) — derived from match data:
  T1_SERVE_IN_DEEP / WIDE / MID   T1 serve-in rate per placement
  T2_SERVE_IN_DEEP / WIDE / MID   T2 serve-in rate per placement
  T1_RET_VS_DEEP / WIDE / MID     T1 return success per placement
  T2_RET_VS_DEEP / WIDE / MID     T2 return success per placement
  T1_DROP_IN / T1_DRIVE_IN        T1 third-shot success rates
  T2_DROP_IN / T2_DRIVE_IN        T2 third-shot success rates
  T1_RALLY_WIN                    T1 rally win % (T2 = 100 - T1)

  Each skill parameter also has an explicit complement constant
  (e.g., T1_SERVE_FAULT_DEEP = 100 - T1_SERVE_IN_DEEP) so that
  PAT's integer-weight pcase works correctly.

GAME SETTINGS (2):
  TARGET    default 11
  MAXSCORE  default 15

All values are integers 1–99 representing percentages.


================================================================================
3. DOUBLES SIDE-OUT SCORING
================================================================================

  Pickleball doubles uses SIDE-OUT SCORING with TWO SERVERS per team:

  Serving team wins rally:
    -> serving team scores +1, same server continues

  Serving team loses rally (or serve fault):
    -> if Server 1 was serving:  pass to Server 2 on same team (no point)
    -> if Server 2 was serving:  SIDE OUT to other team at Server 1

  Opening exception:
    -> game starts with Team 1 at serverNum = 2
    -> this means Team 1 only gets ONE serve attempt before the
       first side out, preventing an unfair first-serve advantage

  Score call in real pickleball:  "server score – receiver score – server#"
  (e.g., "4-2-1" means serving team has 4, receiving team has 2, Server 1)


================================================================================
4. HOW TO INJECT PARAMETERS
================================================================================

    import re
    template = open("pickleball_template.pcsp").read()
    for param, value in stats.items():
        template = re.sub(
            rf"#define {param} \d+;",
            f"#define {param} {value};",
            template
        )
    open("matchup.pcsp", "w").write(template)


================================================================================
5. ASSERTIONS
================================================================================

#assert PickleballGame reaches team1Win with prob;
  -> Exact probability Team 1 wins

#assert PickleballGame reaches team2Win with prob;
  -> Exact probability Team 2 wins

These two sum to 1.0.


================================================================================
6. STATE VARIABLES
================================================================================

  t1Score       Team 1's current score     (starts 0)
  t2Score       Team 2's current score     (starts 0)
  servingTeam   Which team is serving: 1 or 2   (starts 1)
  serverNum     Which server on that team: 1 or 2
                (starts 2 — opening exception)
  winner        0 until game ends, then 1 or 2


================================================================================
7. PROCESS STRUCTURE
================================================================================

  PickleballGame -> CheckScore
    |-> T1Serves / T2Serves             (serve placement pcase)
      |-> T1Serve{Deep,Wide,Mid}        (serve-in / fault pcase)
        |-> T2Returns{Deep,Wide,Mid}    (return success pcase)
          |-> T1ThirdShot               (drop / drive choice pcase)
            |-> T1Third{Drop,Drive}     (shot success pcase)
              |-> RallyT1Served         (rally outcome pcase)
                |-> T1ScoresPoint       (serving team won)
                |-> T1LosesRally        (see below)
    (symmetric for T2 serving)

  Server switch / side-out:
    T1LosesRally:
      serverNum == 1  ->  t1_second_server, serverNum = 2  -> CheckScore
      serverNum == 2  ->  side_out, servingTeam = 2, serverNum = 1  -> CheckScore
    T2LosesRally:
      serverNum == 1  ->  t2_second_server, serverNum = 2  -> CheckScore
      serverNum == 2  ->  side_out, servingTeam = 1, serverNum = 1  -> CheckScore

  Scoring:
    T1ScoresPoint  -> t1Score + 1, server stays    -> CheckScore
    T2ScoresPoint  -> t2Score + 1, server stays    -> CheckScore
