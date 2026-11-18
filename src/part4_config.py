"""Committed, non-secret settings for Doris's historical Part 4 replication."""

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "_data" / "part4"
OUTPUT_DIR = BASE_DIR / "_output" / "part4"
UNIVERSE_FILE = BASE_DIR / "data_manual" / "part4_commodities.csv"
PULL_START = "1984-12-01"  # Prices needed for Jan-Dec 1985 realized signal warmup.
PULL_END = "2014-02-28"
SAMPLE_START = "1986-01"
SAMPLE_END = "2014-02"
N_EXTREME = 4
# The supplied table's mean t statistics are consistent with monthly iid SEs.
# Also export HAC(1) sensitivity statistics; do not silently replace the main SE.
TSTAT_METHOD = "iid"
# Signed portfolio agreement: same commodity on the same side of both sorts.
# Export union overlap too, because the caption alone does not resolve this convention.
OVERLAP_MODE = "same_side"
IDENTITY_ATOL = 1e-12
