# Part 4 — Curve maturity and spot/roll decomposition

Owner: Doris Ding. Course Table 4 corresponds to the supplied Table IA.XI;
course Table 5 corresponds to Table IA.XV. The supplied screenshots are the
numerical target; table numbers differ across paper versions. The same targets
also appear as Tables 4 and 5 in the
[earlier author manuscript](https://conference.nber.org/confer/2016/CEMf16/Boons_Prado.pdf).

## Run from a clean clone

From the repository root, install `requirements.txt` in your project environment.
WRDS access to `tr_ds_fut` is required. Configure your own libpq `.pgpass` file
(on Unix it should have mode 0600). Supply `WRDS_USERNAME` if there is no
WRDS-specific username entry. Do not commit passwords or any `.env` file.

```bash
python -m pip install -r requirements.txt
doit part4
python -m pytest -q src/test_part4.py
```

Equivalent individual steps:

```bash
python src/pull_part4_wrds.py
python src/run_part4.py
jupytext --to notebook --output _output/04_part4_analysis.ipynb src/04_part4_analysis.ipynb.py
jupyter nbconvert --execute --to notebook --inplace _output/04_part4_analysis.ipynb
```

The current historical replication does **not** update the tables through 2026.
Its committed evaluation dates are in `src/part4_config.py`. Changing the
historical versus update sample is a research decision, not a secret `.env`
setting. Inputs begin in December 1984 to provide twelve realized 1985 monthly
returns for the first possible January 1986 evaluation. Some commodities start
later, so the panel is unbalanced.

## What is reused from Kayla

`pull_part4_wrds.py` uses Kayla's Datastream table join and exact
contract-name/ticker/USD filters. `data_manual/part4_commodities.csv` makes the
21-commodity mapping explicit; WRDS metadata was checked before pulling it.
There is no dependence on the missing `wrds_commodity_coverage.csv`.

The query downloads only the last settlement observation of each **individual
contract-month**. This is lossless for Kayla's month-end panel and same-contract
monthly return functions, but cannot support daily roll-timing extensions.
These compact WRDS records are under `_data/part4/raw/`; do not mistake them
for daily data or overwrite Kayla's `_data` products with them.

The runner directly calls her `build_futures_panel`, `build_monthly_returns`
and `calculate_basis` functions, without changing their source files. Her
panel is post-roll: contract month must be strictly after formation month t+2.
The same selected contract is repriced at t+1. The return stored at t is the
forward holding-period return, not the return already known at t.

## Table 4

For each commodity and nearby rank, calculate a trailing 12-month compounded
return using only returns realized by formation month t. Reindex to a full
monthly calendar before shifting and compounding, so gaps cannot be bridged.
BM12, BM23 and BM34 are differences of these compounded rank returns.

Use the common formation-time universe with all three signals available.
At least eight commodities are required. Four highest and four lowest signals
are selected; commodity name is the deterministic tie-breaker. Equal-weight
High4 minus equal-weight Low4 is evaluated in R2, R2-R3, R3 and R3-R4 exactly
where the screenshot reports those columns. Selected outcomes must all exist;
a missing selected contract invalidates that metric's portfolio-month.
There is no reranking using next-month return availability.

The main conditional row uses same-side agreement:

```
|High4(BM12) intersect High4(BM23)|
+ |Low4(BM12) intersect Low4(BM23)| <= 3
```

BM34 is handled analogously. **Convention to review with the team:** the caption
does not explicitly resolve whether opposite-side matches should count.
Unsigned overlap of the two eight-name unions is therefore exported in rows
ending `_union_sensitivity`. This choice is not presented as author-confirmed.
Counts in the rendered main table show the maximum valid N in a row block;
exact N and date ranges per metric are in `table4_main_statistics.csv`.

## Table 5

At formation t, identify last month's selected first contract using an exact
calendar-month join. If it differs from the newly selected first contract,
verify that the old contract expires in t+2, and retrieve the old price on the
**same exact date** as the new contract's price. Then:

```
roll = old_price_at_t / new_price_at_t - 1
spot = (1 + futures_return_t_to_t1) / (1 + roll) - 1
```

No contract change means roll=0. Missing old quotes, missing previous holdings,
or an unexpected contract change mean an unavailable decomposition, not zero.
The old contract is not today's post-roll rank 2. The spot component is a
residual defined by this decomposition, not an independent physical-price
observation. The roll component is not an immediate cash profit on switching.

Sort on BM12, basis or momentum using a common available-signal universe;
at least nine commodities are required so Mid is nonempty. Decompose each
commodity **before** averaging into High4, Mid and Low4. The same names and
weights are used for futures, spot, roll and the product term. If any eligible
commodity lacks a component, all Table 5 portfolios for that month are marked
missing, preserving the same evaluation months across groups and signals.

The exact identity, tested before and after aggregation, is:

```
futures = spot + roll + spot * roll
```

Portfolio spot is not `(1+portfolio_futures)/(1+portfolio_roll)-1`.
The benchmark basis direction is High minus Low exactly as the supplied table,
not the reversed low-basis carry direction.

## Statistics and source differences

Annual average returns are `1200 * mean(monthly_decimal_return)`, in percent.
Sharpe is `sqrt(12) * mean / sample_std`. Main t statistics use the monthly
sample standard deviation divided by sqrt(N); this is consistent with the
reported Sharpe/N/t relationships in the supplied table. The table caption
does not separately document a robust covariance estimator. Calendar-aware
HAC(1) sensitivity is exported as `t_hac1`, including actual gaps in conditional
samples, without treating two nonadjacent months as neighbors.

The authors' sample starts in 1960-08 and uses CRB/FII; ours is 1986-01 to
2014-02 using WRDS. Exact equality to their targets is not expected. Every
reported target, reproduced value and difference is in `paper_comparison.csv`;
no matching filters or numeric tolerances are tuned to force agreement.
The predeclared floating-point identity tolerance is 1e-12 in decimal returns.

Known coverage limits: HU gasoline ends in December 2006; no automatic splice
to reformulated gasoline is made. Copper starts in July 1988 and rough rice
in August 1986, before additional signal warmup. WRDS contains a small number
of irregular first-contract changes in rough rice and silver. These are
quarantined and listed in `roll_event_diagnostics.csv`; their months may be
missing from Table 5. Full-sample versus common-sample effects should be
reviewed before merging into the team's main results.

## Outputs and report handoff

All generated files are under `_output/part4/` and ignored by Git:

- `table4` / `table5`: CSV, LaTeX, HTML and PNG previews.
- `table*_monthly.csv`: monthly returns, formation and holding months.
- `table*_memberships.csv`: exact commodity selection by month and signal.
- `table*_statistics.csv`: unrounded statistics, N, dates and sensitivities.
- `coverage_diagnostics.csv` and `roll_event_diagnostics.csv`: exclusions.
- `decomposition_identity_audit.csv`: portfolio identity residuals.
- `paper_comparison.csv`: targets versus WRDS results; diagnostic, not pass/fail.
- `results.md` and `results_macros.tex`: generated findings and report numbers.
- `run_manifest.json`: sample settings, input manifest hash and code hashes.

WRDS data, hashes and download dates are documented locally in
`_data/part4/source_manifest.json`. Restricted raw records are not registered
for public download. `reports/part4_section.tex` can be included in the team's
main report after `doit part4`. ChartBook registration covers only generated
aggregate statistics and the analysis-tour notebook; no site is published here.

## Verification scope

`src/test_part4.py` tests calendar alignment, same-contract returns, roll-event
pricing, multiplicative identities, sorting, missing outcomes and units.
Synthetic fixtures are labelled and used only for tests, never as empirical
tables. One local-data identity check skips without a WRDS cache. GitHub
Actions runs the credential-free Part 4 tests on pushes and pull requests;
this does not claim to validate the other members' future analyses.
