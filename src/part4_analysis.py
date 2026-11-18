"""Pure, auditable calculations for Tables 4 / IA.XI and 5 / IA.XV.

All rows are labelled by formation month: monthly_return at t is the
same-contract return t -> t+1, following Kayla's interface. Sorts use information
at t only. A missing selected asset's outcome invalidates the portfolio-month;
we never replace it with the next best asset after observing outcomes.
"""

import numpy as np
import pandas as pd

from part4_config import IDENTITY_ATOL, N_EXTREME, OVERLAP_MODE


def maturity_signals(returns):
    """Compound 12 realized calendar months, then difference nearby momentums."""
    frames = []
    for commodity, group in returns.groupby("commodity"):
        wide = group.assign(month=pd.PeriodIndex(group.month, freq="M")).pivot(
            index="month", columns="nearby_rank", values="monthly_return"
        )
        wide = wide.reindex(
            index=pd.period_range(wide.index.min(), wide.index.max(), freq="M"),
            columns=[1, 2, 3, 4],
        )
        # At formation t, the return stored at t-1 has just become observable.
        momentum = (1 + wide.shift(1)).rolling(12, min_periods=12).apply(
            np.prod, raw=True
        ) - 1
        out = pd.DataFrame(index=wide.index)
        out["commodity"] = commodity
        out["momentum"] = momentum[1]
        for a, b in [(1, 2), (2, 3), (3, 4)]:
            out[f"bm{a}{b}"] = momentum[a] - momentum[b]
        out.index.name = "month"
        frames.append(out.reset_index())
    return pd.concat(frames, ignore_index=True)


def decomposition(raw, panel, returns):
    """Trace the previously held first contract to the current roll-date price.

    Kayla's panel is post-roll (>t+2). The OLD contract is last month's selected
    first contract, not today's post-roll second contract. Verify that it expires
    in t+2, then price old/new on the exact common formation date. No roll = 0;
    unobservable previous holdings or unmatched prices = missing, never zero.
    """
    panel = panel.copy()
    panel["month"] = pd.PeriodIndex(panel.month, freq="M")
    first = panel.loc[panel.nearby_rank.eq(1)].sort_values("month").copy()
    previous = first[["month", "futcode", "contract_month"]].copy()
    previous["month"] += 1
    previous = previous.rename(
        columns={"futcode": "old_futcode", "contract_month": "old_contract_month"}
    )
    first = first.merge(previous, on="month", how="left", validate="one_to_one")
    raw = raw.copy()
    raw["date_"] = pd.to_datetime(raw.date_)
    prices = raw[["futcode", "date_", "settlement"]].rename(
        columns={"futcode": "old_futcode", "settlement": "old_settlement"}
    )
    if prices.duplicated(["old_futcode", "date_"]).any():
        raise ValueError("Duplicate raw contract-date prices")
    first = first.merge(
        prices, on=["old_futcode", "date_"], how="left", validate="many_to_one"
    )
    known = first.old_futcode.notna()
    first["is_roll"] = known & first.futcode.ne(first.old_futcode)
    expected = first.old_contract_month.eq(first.month + 2)
    first["roll_status"] = np.select(
        [
            ~known,
            first.is_roll & ~expected,
            first.is_roll & first.old_settlement.isna(),
        ],
        ["no_previous_month", "unexpected_contract_change", "missing_old_price"],
        default="ok",
    )
    first["roll_return"] = np.nan
    first.loc[known & ~first.is_roll, "roll_return"] = 0.0
    valid_roll = (
        first.is_roll & expected & first.old_settlement.gt(0) & first.settlement.gt(0)
    )
    first.loc[valid_roll, "roll_return"] = (
        first.loc[valid_roll, "old_settlement"] / first.loc[valid_roll, "settlement"]
        - 1
    )
    ret = returns.loc[returns.nearby_rank.eq(1), ["month", "monthly_return"]].copy()
    ret["month"] = pd.PeriodIndex(ret.month, freq="M")
    first = first.merge(ret, on="month", validate="one_to_one")
    first["spot_return"] = (1 + first.monthly_return) / (1 + first.roll_return) - 1
    first["cross_term"] = first.spot_return * first.roll_return
    valid = first[["monthly_return", "roll_return", "spot_return"]].notna().all(axis=1)
    np.testing.assert_allclose(
        first.loc[valid, "monthly_return"],
        first.loc[valid, "spot_return"]
        + first.loc[valid, "roll_return"]
        + first.loc[valid, "cross_term"],
        atol=IDENTITY_ATOL,
        rtol=0,
    )
    return first[
        [
            "commodity",
            "month",
            "date_",
            "futcode",
            "old_futcode",
            "settlement",
            "old_settlement",
            "is_roll",
            "roll_status",
            "monthly_return",
            "roll_return",
            "spot_return",
            "cross_term",
        ]
    ]


def sort_members(frame, signal, n=N_EXTREME):
    """Select fixed extremes using signal only; commodity names break ties."""
    eligible = frame.loc[np.isfinite(frame[signal])].sort_values([signal, "commodity"])
    if len(eligible) < 2 * n:
        return None
    return {
        "Low4": eligible.head(n).commodity.tolist(),
        "Mid": eligible.iloc[n:-n].commodity.tolist(),
        "High4": eligible.tail(n).commodity.tolist(),
    }


def overlap_count(reference, alternative, mode="same_side"):
    """Count same-side agreement or unsigned overlap among the eight extremes."""
    if mode == "same_side":
        return sum(
            len(set(reference[side]) & set(alternative[side]))
            for side in ["High4", "Low4"]
        )
    if mode == "union":
        return len(
            set(reference["High4"] + reference["Low4"])
            & set(alternative["High4"] + alternative["Low4"])
        )
    raise ValueError(f"Unknown overlap convention: {mode}")


def portfolio_mean(values, members):
    """Return missing if ANY preselected member has a missing outcome."""
    if not members:
        return np.nan
    selected = values.reindex(members)
    return selected.mean() if np.isfinite(selected).all() else np.nan


def table4_series(signals, returns):
    """Build the exact five row blocks and four columns in the supplied table."""
    wide = (
        returns.assign(month=pd.PeriodIndex(returns.month, freq="M"))
        .pivot(
            index=["commodity", "month"], columns="nearby_rank", values="monthly_return"
        )
        .reindex(columns=[1, 2, 3, 4])
    )
    outcomes = pd.DataFrame(
        {
            "R2": wide[2],
            "R2-R3": wide[2] - wide[3],
            "R3": wide[3],
            "R3-R4": wide[3] - wide[4],
        }
    ).reset_index()
    merged = signals.merge(
        outcomes, on=["commodity", "month"], how="left", validate="one_to_one"
    )
    records, memberships = [], []
    for month, group in merged.groupby("month"):
        # Common, formation-time signal universe for comparable maturity sorts.
        group = group.dropna(subset=["bm12", "bm23", "bm34"])
        sorts = {s: sort_members(group, s) for s in ["bm12", "bm23", "bm34"]}
        if sorts["bm12"] is None:
            continue
        for signal, columns in [
            ("bm12", ["R2", "R2-R3", "R3", "R3-R4"]),
            ("bm23", ["R2", "R2-R3"]),
            ("bm34", ["R3", "R3-R4"]),
        ]:
            members = sorts[signal]
            same = overlap_count(sorts["bm12"], members, "same_side")
            union = overlap_count(sorts["bm12"], members, "union")
            for side in ["High4", "Low4"]:
                memberships.extend(
                    {
                        "month": str(month),
                        "signal": signal,
                        "side": side,
                        "commodity": c,
                    }
                    for c in members[side]
                )
            for column in columns:
                values = group.set_index("commodity")[column]
                value = portfolio_mean(values, members["High4"]) - portfolio_mean(
                    values, members["Low4"]
                )
                base = {
                    "month": str(month),
                    "holding_month": str(month + 1),
                    "metric": column,
                    "value": value,
                    "eligible_commodities": len(group),
                    "overlap_same_side": same,
                    "overlap_union": union,
                }
                records.append(dict(**base, block=signal))
                if (
                    signal != "bm12"
                    and (same if OVERLAP_MODE == "same_side" else union) <= 3
                ):
                    records.append(dict(**base, block=f"{signal}|bm12"))
                if signal != "bm12" and union <= 3:
                    records.append(
                        dict(**base, block=f"{signal}|bm12_union_sensitivity")
                    )
    return pd.DataFrame(records), pd.DataFrame(memberships)


def table5_series(signals, components):
    """Sort at t then average each commodity's futures, spot, roll and product."""
    cols = [
        "commodity",
        "month",
        "monthly_return",
        "spot_return",
        "roll_return",
        "cross_term",
    ]
    merged = signals.merge(
        components[cols], on=["commodity", "month"], how="left", validate="one_to_one"
    )
    records, memberships = [], []
    for month, group in merged.groupby("month"):
        # Basis and momentum benchmarks use the same known-signal universe.
        group = group.dropna(subset=["bm12", "basis", "momentum"])
        for signal in ["bm12", "basis", "momentum"]:
            members = sort_members(group, signal)
            if members is None or not members["Mid"]:
                continue
            for side, names in members.items():
                memberships.extend(
                    {
                        "month": str(month),
                        "signal": signal,
                        "side": side,
                        "commodity": c,
                    }
                    for c in names
                )
            values = group.set_index("commodity")
            # Keep all return components on exactly the same portfolio-months.
            complete = (
                values[["monthly_return", "spot_return", "roll_return", "cross_term"]]
                .apply(np.isfinite)
                .all(axis=1)
            )
            for metric, column in [
                ("futures", "monthly_return"),
                ("spot", "spot_return"),
                ("roll", "roll_return"),
                ("cross_term", "cross_term"),
            ]:
                means = {}
                for side, names in members.items():
                    means[side] = (
                        portfolio_mean(values[column], names)
                        if complete.all()
                        else np.nan
                    )
                means["High4-Low4"] = means["High4"] - means["Low4"]
                for side, value in means.items():
                    if signal != "bm12" and side != "High4-Low4":
                        continue
                    records.append(
                        {
                            "month": str(month),
                            "holding_month": str(month + 1),
                            "signal": signal,
                            "portfolio": side,
                            "metric": metric,
                            "value": value,
                            "eligible_commodities": len(group),
                        }
                    )
    return pd.DataFrame(records), pd.DataFrame(memberships)


def summary_stats(series):
    """Annual arithmetic mean (%), iid t, annual Sharpe and HAC(1) sensitivity."""
    x = np.asarray(series.dropna(), dtype=float)
    n = len(x)
    if n < 2:
        return {
            "n_months": n,
            "avg_ret": np.nan,
            "t_stat": np.nan,
            "sharpe": np.nan,
            "t_hac1": np.nan,
        }
    mean, std = x.mean(), x.std(ddof=1)
    iid_se = std / np.sqrt(n)
    return {
        "n_months": n,
        "avg_ret": 1200 * mean,
        "t_stat": mean / iid_se if iid_se else np.nan,
        "sharpe": np.sqrt(12) * mean / std if std else np.nan,
    }


def summarize(frame, keys):
    """Preserve calendar spacing for HAC(1), including conditional sample gaps."""
    rows = []
    for key, group in frame.groupby(keys, sort=False):
        key = key if isinstance(key, tuple) else (key,)
        stats = summary_stats(group.value)
        valid = group.dropna(subset=["value"]).copy()
        x = valid.value.to_numpy()
        if len(x) >= 2:
            errors = x - x.mean()
            month = pd.PeriodIndex(valid.month, freq="M").asi8
            order = np.argsort(month)
            month, errors = month[order], errors[order]
            lag_products = (errors[1:] * errors[:-1])[np.diff(month) == 1].sum()
            variance = (
                (np.dot(errors, errors) + lag_products)
                / len(x) ** 2
                * len(x)
                / (len(x) - 1)
            )
            stats["t_hac1"] = x.mean() / np.sqrt(variance) if variance > 0 else np.nan
        else:
            stats["t_hac1"] = np.nan
        stats.update(
            first_holding_month=valid.holding_month.min() if len(valid) else None,
            last_holding_month=valid.holding_month.max() if len(valid) else None,
        )
        rows.append(dict(zip(keys, key), **stats))
    return pd.DataFrame(rows)
