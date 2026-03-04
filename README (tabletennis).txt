================================================================================
  PART A — TABLE TENNIS SINGLES PARAMETRIC PCSP# MODEL  (Documentation)
================================================================================

FILE:  tabletennis_template.pcsp

================================================================================
1. PARAMETER REFERENCE (27 total)
================================================================================

STRATEGY PARAMETERS (10) — what Part C varies:
  P1_SERVE_FH_PCT / BH_PCT / MID_PCT   P1 serve placement split (sum=100)
  P2_SERVE_FH_PCT / BH_PCT / MID_PCT   P2 serve placement split (sum=100)
  P1_THIRD_ATTACK_PCT / PUSH_PCT        P1 third-ball choice (sum=100)
  P2_THIRD_ATTACK_PCT / PUSH_PCT        P2 third-ball choice (sum=100)

SKILL PARAMETERS (15) — from match data:
  P1_SERVE_IN_FH / BH / MID     P1 serve-in rate per placement
  P2_SERVE_IN_FH / BH / MID     P2 serve-in rate per placement
  P1_RCV_VS_FH / BH / MID       P1 receive success per placement
  P2_RCV_VS_FH / BH / MID       P2 receive success per placement
  P1_ATTACK_IN / P1_PUSH_IN     P1 third-ball success rates
  P2_ATTACK_IN / P2_PUSH_IN     P2 third-ball success rates
  P1_RALLY_WIN                   P1 rally win % (P2 = 100 - P1)

GAME SETTINGS (2):
  TARGET    default 11
  MAXSCORE  default 15

All values are integers 1–99 representing percentages.


================================================================================
2. HOW TO INJECT PARAMETERS
================================================================================

    import re
    template = open("tabletennis_template.pcsp").read()
    for param, value in stats.items():
        template = re.sub(
            rf"#define {param} \d+;",
            f"#define {param} {value};",
            template
        )
    open("matchup.pcsp", "w").write(template)

================================================================================
3. ASSERTIONS
================================================================================

#assert TableTennisGame reaches player1Win with prob;
  -> Exact probability Player 1 wins

#assert TableTennisGame reaches player2Win with prob;
  -> Exact probability Player 2 wins

These two sum to 1.0.
