# FinQA E3 N-control candidate

N is paired to the same 150 FinQA sources as O and K. It removes facts screened as outside the original FinQA gold program input support, while retaining the K-deleted necessary facts and every program leaf needed by the original answer path. For 148 sources, N removes the same number of distinct facts as paired K. Cases 20 and 103 have no other quantified facts available under those preservation rules, so N equals O for those two cases; no answer-bearing fact is deleted to force a matched dose.

Program checks replay exact edits, bind source IDs, preserve the question, verify disjoint K/N deleted fact IDs and retain the gold program input values. These checks and the two local screening passes are not independent human review or a complete proof of semantic irrelevance. Human review remains pending, and no N-condition model calls have been made.

The full audit JSON also includes the original gold program; treat gold/audit fields as evaluation-only and exclude them from model prompts. `n_control_pair_index.csv` provides the paired deletion counts and ratios.
