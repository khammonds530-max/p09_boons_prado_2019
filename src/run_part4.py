"""Build Doris's real-data replication tables from cached WRDS observations."""

import hashlib
import json
import os

import numpy as np
import pandas as pd

from build_futures_panel import build_futures_panel
from build_futures_returns import build_monthly_returns
from build_futures_signals import calculate_basis
from part4_analysis import (
    decomposition,
    maturity_signals,
    summarize,
    table4_series,
    table5_series,
)
from part4_config import (
    DATA_DIR,
    OUTPUT_DIR,
    OVERLAP_MODE,
    SAMPLE_END,
    SAMPLE_START,
    TSTAT_METHOD,
    UNIVERSE_FILE,
)

BLOCKS = ["bm12", "bm23", "bm23|bm12", "bm34", "bm34|bm12"]
METRICS4 = ["R2", "R2-R3", "R3", "R3-R4"]
COLS5 = [
    ("bm12", "High4"),
    ("bm12", "Mid"),
    ("bm12", "Low4"),
    ("bm12", "High4-Low4"),
    ("basis", "High4-Low4"),
    ("momentum", "High4-Low4"),
]


def save_parquet(frame, path):
    """Store periods as explicit YYYY-MM strings for interoperable handoff."""
    frame = frame.copy()
    for name in frame:
        if isinstance(frame[name].dtype, pd.PeriodDtype):
            frame[name] = frame[name].astype(str)
    frame.to_parquet(path, index=False)


def prepare():
    """Use Kayla's functions, then add signals and auditable roll components."""
    panels, returns, components, diagnostics = [], [], [], []
    for row in pd.read_csv(UNIVERSE_FILE).itertuples(index=False):
        path = DATA_DIR / "raw" / f"{row.ticker}_futures.parquet"
        if not path.exists():
            raise FileNotFoundError(
                f"Missing {path}. Run python src/pull_part4_wrds.py first."
            )
        raw = pd.read_parquet(path)
        if raw.duplicated(["futcode", "date_"]).any():
            raise ValueError(f"Duplicate contract-date: {row.commodity}")
        panel = build_futures_panel(raw)
        panel["commodity"], panel["ticker"] = row.commodity, row.ticker
        ret = build_monthly_returns(raw, panel)
        # Nonpositive prices cannot be used in the multiplicative decomposition.
        ret.loc[ret.settlement.le(0) | ret.next_settlement.le(0), "monthly_return"] = (
            np.nan
        )
        comp = decomposition(raw, panel, ret)
        panels.append(panel)
        returns.append(
            ret[["commodity", "month", "nearby_rank", "futcode", "monthly_return"]]
        )
        components.append(comp)
        diagnostics.append(
            {
                "commodity": row.commodity,
                "ticker": row.ticker,
                "raw_rows": len(raw),
                "first_raw_date": str(raw.date_.min()),
                "last_raw_date": str(raw.date_.max()),
                "panel_months": panel.month.nunique(),
                "valid_returns": ret.monthly_return.notna().sum(),
                "missing_returns": ret.monthly_return.isna().sum(),
                "nonpositive_initial_prices": ret.settlement.le(0).sum(),
                "expected_rolls": comp.is_roll.sum(),
                "missing_roll": comp.roll_return.isna().sum(),
                "unexpected_contract_changes": comp.roll_status.eq(
                    "unexpected_contract_change"
                ).sum(),
            }
        )
    panel = pd.concat(panels, ignore_index=True)
    ret = pd.concat(returns, ignore_index=True)
    comp = pd.concat(components, ignore_index=True)
    for frame in [panel, ret, comp]:
        frame["month"] = pd.PeriodIndex(frame.month, freq="M")
    if ret.duplicated(["commodity", "month", "nearby_rank"]).any():
        raise ValueError("Non-unique commodity-month-rank")
    signals = maturity_signals(ret).merge(
        calculate_basis(panel), on=["commodity", "month"], validate="one_to_one"
    )
    for name, frame in [
        ("panel", panel),
        ("returns", ret),
        ("signals", signals),
        ("components", comp),
    ]:
        save_parquet(frame, DATA_DIR / f"{name}.parquet")
    pd.DataFrame(diagnostics).to_csv(
        OUTPUT_DIR / "coverage_diagnostics.csv", index=False
    )
    comp.loc[comp.roll_status.ne("ok")].to_csv(
        OUTPUT_DIR / "roll_event_diagnostics.csv", index=False
    )
    return ret, signals, comp


def within_sample(frame):
    """Filter on realized holding month, retaining pre-1986 signal warmup."""
    month = pd.PeriodIndex(frame.holding_month, freq="M")
    return frame.loc[
        (month >= pd.Period(SAMPLE_START)) & (month <= pd.Period(SAMPLE_END))
    ].copy()


def display_tables(stats4, stats5):
    """Match the supplied table blocks; blanks mean unreported, not zero."""
    rows4 = []
    for block in BLOCKS:
        subset = stats4.loc[stats4.block.eq(block)].set_index("metric")
        for statistic, label in [
            ("avg_ret", "Avg. ret. (%)"),
            ("t_stat", "(t)"),
            ("sharpe", "Sharpe"),
        ]:
            values = {
                metric: (
                    f"{subset.loc[metric, statistic]:.2f}"
                    if metric in subset.index
                    else ""
                )
                for metric in METRICS4
            }
            if statistic == "t_stat":
                values = {k: f"({v})" if v else "" for k, v in values.items()}
            n = int(subset.n_months.max()) if len(subset) else 0
            rows4.append(
                dict(
                    Sort=f"{block} (N<={n})" if statistic == "avg_ret" else "",
                    Statistic=label,
                    **values,
                )
            )
    rows5 = []
    labels = [f"{signal}: {portfolio}" for signal, portfolio in COLS5]
    for metric in ["futures", "spot", "roll"]:
        for statistic, label in [("avg_ret", "Avg. ret. (%)"), ("t_stat", "(t)")]:
            row = {
                "Component": metric if statistic == "avg_ret" else "",
                "Statistic": label,
            }
            for (signal, portfolio), column in zip(COLS5, labels):
                selected = stats5.loc[
                    stats5.signal.eq(signal)
                    & stats5.portfolio.eq(portfolio)
                    & stats5.metric.eq(metric)
                ]
                v = f"{selected.iloc[0][statistic]:.2f}" if len(selected) else ""
                row[column] = f"({v})" if statistic == "t_stat" and v else v
            rows5.append(row)
    return pd.DataFrame(rows4), pd.DataFrame(rows5)


def paper_targets():
    """Transcribe only supplied screenshot targets; never use them to tune data."""
    rows = []
    values4 = {
        "bm12": [
            [14.55, 5.88, 0.80],
            [2.31, 4.57, 0.63],
            [12.42, 5.35, 0.73],
            [0.98, 2.06, 0.32],
        ],
        "bm23": [[16.46, 6.75, 0.92], [2.52, 5, 0.68]],
        "bm23|bm12": [[7.43, 1.85, 0.42], [1.58, 1.94, 0.44]],
        "bm34": [[11.96, 4.85, 0.71], [0.91, 1.89, 0.28]],
        "bm34|bm12": [[11.52, 3.69, 0.67], [0.57, 0.97, 0.18]],
    }
    for block, values in values4.items():
        columns = (
            METRICS4
            if block == "bm12"
            else (METRICS4[:2] if "bm23" in block else METRICS4[2:])
        )
        for column, numbers in zip(columns, values):
            for statistic, value in zip(["avg_ret", "t_stat", "sharpe"], numbers):
                rows.append(
                    {
                        "table": 4,
                        "block": block,
                        "metric": column,
                        "statistic": statistic,
                        "paper_value": value,
                    }
                )
    values5 = {
        "futures": [
            [15.60, 6.35],
            [5.02, 2.49],
            [-2.78, -1.19],
            [18.38, 6.73],
            [-10.61, -3.88],
            [15.02, 4.61],
        ],
        "spot": [
            [4.99, 1.98],
            [9.45, 4.69],
            [7.82, 3.17],
            [-2.83, -0.98],
            [37.92, 12.88],
            [-7.54, -2.25],
        ],
        "roll": [
            [11.95, 11.54],
            [-4.08, -9.64],
            [-9.57, -13.33],
            [21.53, 17.37],
            [-48.90, -35.03],
            [23.05, 20.15],
        ],
    }
    for metric, values in values5.items():
        for (signal, portfolio), numbers in zip(COLS5, values):
            for statistic, value in zip(["avg_ret", "t_stat"], numbers):
                rows.append(
                    {
                        "table": 5,
                        "block": f"{signal}:{portfolio}",
                        "metric": metric,
                        "statistic": statistic,
                        "paper_value": value,
                    }
                )
    return pd.DataFrame(rows)


def compare_targets(stats4, stats5):
    """Export differences as diagnostics, not full-history equality assertions."""
    target = paper_targets()
    actual = []
    for row in target.itertuples(index=False):
        if row.table == 4:
            selected = stats4.loc[
                stats4.block.eq(row.block) & stats4.metric.eq(row.metric)
            ]
        else:
            signal, portfolio = row.block.split(":")
            selected = stats5.loc[
                stats5.signal.eq(signal)
                & stats5.portfolio.eq(portfolio)
                & stats5.metric.eq(row.metric)
            ]
        actual.append(selected.iloc[0][row.statistic] if len(selected) else np.nan)
    target["reproduced_value"] = actual
    target["difference"] = target.reproduced_value - target.paper_value
    target["comparison_status"] = (
        "different source/sample; diagnostic, not exact-match pass/fail"
    )
    target.to_csv(OUTPUT_DIR / "paper_comparison.csv", index=False)


def render_tables(table4, table5, subtitle):
    """Generate report-ready LaTeX plus HTML and PNG previews from actual values."""
    os.environ.setdefault("MPLCONFIGDIR", str(OUTPUT_DIR / ".matplotlib"))
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    for number, frame in [(4, table4), (5, table5)]:
        path = OUTPUT_DIR / f"table{number}"
        frame.to_csv(path.with_suffix(".csv"), index=False)
        path.with_suffix(".tex").write_text(frame.to_latex(index=False, escape=True))
        path.with_suffix(".html").write_text(
            '<meta charset="utf-8"><style>body{font:16px Georgia;margin:40px}table{border-collapse:collapse}td,th{padding:10px;border-bottom:1px solid #ddd}th{background:#eef2f5}</style>'
            + f"<h2>Table {number}: WRDS replication</h2><p>{subtitle}</p>"
            + frame.to_html(index=False, border=0)
        )
        fig, ax = plt.subplots(figsize=(16, 8 if number == 4 else 5))
        ax.axis("off")
        table = ax.table(
            cellText=frame.values,
            colLabels=frame.columns,
            loc="center",
            cellLoc="center",
        )
        table.auto_set_font_size(False)
        table.set_fontsize(10 if number == 4 else 9)
        table.scale(1, 1.65)
        table.auto_set_column_width(list(range(len(frame.columns))))
        for (r, c), cell in table.get_celld().items():
            cell.set_edgecolor("#dddddd")
            if r == 0:
                cell.set_facecolor("#e8eff6")
                cell.set_text_props(weight="bold")
        ax.set_title(
            f"Table {number}: WRDS historical replication\n{subtitle}",
            fontsize=13,
            pad=20,
        )
        fig.savefig(path.with_suffix(".png"), dpi=170, bbox_inches="tight")
        plt.close(fig)


def main():
    """Build local data, monthly audit trails, result tables and provenance."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ret, signals, comp = prepare()
    ts4, members4 = table4_series(signals, ret)
    ts5, members5 = table5_series(signals, comp)
    if ts4.empty or ts5.empty:
        raise RuntimeError(
            "Insufficient signal histories/universe to form Part 4 portfolios."
        )
    ts4, ts5 = within_sample(ts4), within_sample(ts5)
    for members in [members4, members5]:
        members["holding_month"] = (pd.PeriodIndex(members.month, freq="M") + 1).astype(
            str
        )
    members4, members5 = within_sample(members4), within_sample(members5)
    stats4 = summarize(ts4, ["block", "metric"])
    stats5 = summarize(ts5, ["signal", "portfolio", "metric"])
    for name, frame in [
        ("table4_monthly", ts4),
        ("table5_monthly", ts5),
        ("table4_memberships", members4),
        ("table5_memberships", members5),
        ("table4_statistics", stats4),
        ("table5_statistics", stats5),
    ]:
        frame.to_csv(OUTPUT_DIR / f"{name}.csv", index=False)
    stats4.loc[~stats4.block.str.contains("sensitivity")].to_csv(
        OUTPUT_DIR / "table4_main_statistics.csv", index=False
    )
    table4, table5 = display_tables(stats4, stats5)
    compare_targets(stats4, stats5)
    # Audit identity AFTER aggregation, with predeclared floating-point tolerance.
    audit = ts5.pivot(
        index=["month", "signal", "portfolio"], columns="metric", values="value"
    ).dropna()
    residual = audit.futures - audit.spot - audit.roll - audit.cross_term
    if not np.allclose(residual, 0, atol=1e-12, rtol=0):
        raise AssertionError("Portfolio decomposition identity failed")
    audit["identity_residual"] = residual
    audit.to_csv(OUTPUT_DIR / "decomposition_identity_audit.csv")
    valid4 = ts4.loc[ts4.value.notna()]
    valid5 = ts5.loc[ts5.value.notna()]
    subtitle = f"Holding months {SAMPLE_START} to {SAMPLE_END}; WRDS substituted sample; iid t statistics"
    render_tables(table4, table5, subtitle)
    manifest = {
        "sample_start": SAMPLE_START,
        "sample_end": SAMPLE_END,
        "t_stat_method": TSTAT_METHOD,
        "overlap_mode": OVERLAP_MODE,
        "table4_first": str(valid4.holding_month.min()),
        "table4_last": str(valid4.holding_month.max()),
        "table5_first": str(valid5.holding_month.min()),
        "table5_last": str(valid5.holding_month.max()),
        "max_portfolio_identity_error": float(residual.abs().max()),
        "input_manifest_sha256": hashlib.sha256(
            (DATA_DIR / "source_manifest.json").read_bytes()
        ).hexdigest(),
        "pandas_version": pd.__version__,
        "numpy_version": np.__version__,
        "code_hashes": {
            name: hashlib.sha256(
                (UNIVERSE_FILE.parents[1] / name).read_bytes()
            ).hexdigest()
            for name in [
                "src/part4_analysis.py",
                "src/run_part4.py",
                "src/part4_config.py",
                "src/build_futures_panel.py",
                "src/build_futures_returns.py",
                "src/build_futures_signals.py",
                "src/pull_part4_wrds.py",
                "data_manual/part4_commodities.csv",
            ]
        },
    }
    (OUTPUT_DIR / "run_manifest.json").write_text(json.dumps(manifest, indent=2))
    hl = stats5.loc[
        stats5.signal.eq("bm12") & stats5.portfolio.eq("High4-Low4")
    ].set_index("metric")
    findings = (
        f"# Part 4: WRDS replication results\n\n"
        f"Evaluation window: {SAMPLE_START} through {SAMPLE_END}; actual holding months "
        f"{manifest['table5_first']} through {manifest['table5_last']}. "
        f"BM High4-Low4 has {int(hl.loc['futures', 'n_months'])} valid months.\n\n"
        f"Annualized BM High4-Low4 futures return is {hl.loc['futures', 'avg_ret']:.2f}% "
        f"(iid t={hl.loc['futures', 't_stat']:.2f}); roll is {hl.loc['roll', 'avg_ret']:.2f}% "
        f"(t={hl.loc['roll', 't_stat']:.2f}); spot is {hl.loc['spot', 'avg_ret']:.2f}% "
        f"(t={hl.loc['spot', 't_stat']:.2f}). The substituted historical sample supports the "
        "roll-driven interpretation; this is not an out-of-sample trading-performance claim.\n\n"
        f"Maximum portfolio decomposition residual: {manifest['max_portfolio_identity_error']:.2e}.\n\n"
        "The paper uses 1960-08 through 2014-02 and CRB/FII; this run uses WRDS and a shorter, "
        "unbalanced universe. HU gasoline ends in 2006; copper starts in 1988; rough rice starts "
        "in 1986. See coverage_diagnostics.csv and roll_event_diagnostics.csv. Anomalous "
        "contract changes are not assumed to be scheduled rolls. No exact-match claim is made. "
        "Signed overlap is the main convention; unsigned overlap and HAC(1) are sensitivities.\n"
    )
    (OUTPUT_DIR / "results.md").write_text(findings)
    macros = "\n".join(
        f"\\newcommand{{\\{name}}}{{{hl.loc[metric, stat]:.2f}}}"
        for name, metric, stat in [
            ("PartFourFutures", "futures", "avg_ret"),
            ("PartFourRoll", "roll", "avg_ret"),
            ("PartFourSpot", "spot", "avg_ret"),
            ("PartFourFuturesT", "futures", "t_stat"),
        ]
    )
    (OUTPUT_DIR / "results_macros.tex").write_text(macros + "\n")
    print(table4.to_string(index=False))
    print(table5.to_string(index=False))
    print(f"Outputs: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
