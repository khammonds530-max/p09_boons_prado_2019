# ---
# jupyter:
#   jupytext:
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#   kernelspec:
#     display_name: Python 3
#     language: python
#     name: python3
# ---

# %% [markdown]
# # Curve maturity and spot/roll decomposition — Doris, Part 4
#
# Run `doit part4` first. Tables 4 and 5 correspond to the supplied
# IA.XI and IA.XV screenshots. This notebook presents WRDS results, not
# simulated prices or the authors' original CRB/FII observations.

# %%
from pathlib import Path

import pandas as pd
from IPython.display import Markdown, display

ROOT = next(
    p
    for p in [Path.cwd(), *Path.cwd().parents]
    if (p / "data_manual/part4_commodities.csv").exists()
)
OUT = ROOT / "_output/part4"

# %% [markdown]
# ## Table 4: maturity-specific relative strength
#
# At formation month t, compound the 12 returns realized by t separately for
# nearby ranks 1–4. Form BM12, BM23, BM34; select four highest/four lowest
# commodities, then evaluate next month's outright or spreading returns.
# Same-side portfolio agreement <=3 defines the main conditional rows;
# unsigned-union overlap is exported as a sensitivity, since the caption's
# overlap wording does not fully specify how opposite-side matches count.

# %%
display(pd.read_csv(OUT / "table4.csv").fillna(""))
display(pd.read_csv(OUT / "table4_main_statistics.csv"))

# %% [markdown]
# ## Table 5: futures = spot + roll + spot × roll
#
# On a roll date, price the previously held contract and newly selected first
# contract at the exact same observation date. Roll = old/new - 1, and spot =
# (1+futures)/(1+roll)-1. Without a roll, roll is zero. The spot component is a
# residual; it is not an independently observed physical spot-price return.
# Decompose commodities first, then form equal-weight portfolios. Reject a
# whole formation month if any eligible component is unavailable; do not
# replace a missing selected commodity using its realized future outcome.

# %%
display(pd.read_csv(OUT / "table5.csv"))
audit = pd.read_csv(OUT / "decomposition_identity_audit.csv")
display(
    Markdown(
        f"Maximum absolute portfolio identity residual: **{audit.identity_residual.abs().max():.2e}**."
    )
)

# %% [markdown]
# ## Coverage and comparison limits
#
# The evaluation window is 1986-01 through 2014-02, with available pre-1986
# warmup observations. Histories differ across commodities. The HU gasoline
# series is not silently spliced to a different specification. Exceptional
# contract changes are quarantined in the decomposition. Mean returns are
# annual arithmetic percentages; the main t statistic uses monthly iid SEs,
# with calendar-aware HAC(1) sensitivity in the statistics files.

# %%
display(pd.read_csv(OUT / "coverage_diagnostics.csv"))
display(pd.read_csv(OUT / "paper_comparison.csv"))
