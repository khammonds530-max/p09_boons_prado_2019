# Part 4 verification — 2026-11-18

The Part 4 branch was based on Kayla's `fae37c4` data-pipeline commit.
Her four data modules were reused unchanged. The original local `main`
and `feature/futures-data-pipeline` branch tips were not moved.

Verified locally:

- Real WRDS Datastream data downloaded for all 21 mapped commodities.
- `doit part4` completed; repeating it skipped up-to-date analysis outputs.
- 25 tests passed, including the existing five utility tests. The dedicated
  Part 4 suite contains 20 tests. Without cached WRDS data, the local-data
  identity test skips; all synthetic economic tests remain credential-free.
- A new temporary Git clone with **no data/output cache** independently
  downloaded WRDS records and completed `doit part4` successfully.
- Both rendered-table CSVs, both statistics CSVs and both monthly-return CSVs
  were identical between the fresh clone and the working repository.
- The analysis-tour notebook executed all four code cells successfully.
- The report fragment plus generated tables/macros compiled with XeLaTeX.
- New Python modules passed Ruff; Git diff whitespace checks passed.

This is a clean-code/data-cache check using the host's Python environment
plus temporary dependencies, not a fresh operating-system/container build.
The host lacked some project dependencies, so these were installed under a
temporary directory without modifying its global Python packages. The
repository's standard setup remains `pip install -r requirements.txt` inside
the project environment. Full ChartBook site rendering/publication was not
performed; its Part 4 registrations and TOML syntax were checked locally.

Selected generated results (1986-01 through 2014-02; 331 common Table 5 months):

| BM High4-Low4 | Annualized mean (%) | iid t |
|---|---:|---:|
| Futures | 17.49 | 4.32 |
| Spot component | -4.80 | -1.10 |
| Roll component | 22.55 | 11.95 |

These rounded figures are a dated verification snapshot, not report inputs.
The report reads generated `results_macros.tex`; unrounded values and future
rerun results remain in `_output/part4/`.

Table 4 conditional rows depend on an explicitly documented same-side overlap
convention. Unsigned-union sensitivity rows are also supplied. The screenshot
caption does not fully resolve this convention, so it should be reviewed with
the team before claiming an exact methodological match to the authors.

No exact numerical replication claim, current-data update, WRDS–Databento
reconciliation, remote push, PR merge, or website publication is implied by
these checks.
