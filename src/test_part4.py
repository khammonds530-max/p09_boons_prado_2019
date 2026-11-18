"""Economic correctness checks using hand-constructed, credential-free examples."""

import numpy as np
import pandas as pd
import pytest

from build_futures_panel import build_futures_panel
from build_futures_returns import build_monthly_returns
from part4_analysis import (
    decomposition,
    maturity_signals,
    overlap_count,
    portfolio_mean,
    sort_members,
    summary_stats,
    table4_series,
    table5_series,
)
from run_part4 import within_sample


def history():
    """A complete calendar with known constant returns at each nearby rank."""
    return pd.DataFrame(
        [
            {
                "commodity": "A",
                "month": str(month),
                "nearby_rank": rank,
                "monthly_return": 0.01 / rank,
            }
            for month in pd.period_range("2020-01", "2021-03", freq="M")
            for rank in range(1, 5)
        ]
    )


def test_twelve_realized_months_and_no_future_information():
    data = history()
    result = maturity_signals(data).set_index("month")
    assert (
        result.loc[pd.Period("2020-12"), "bm12"]
        != result.loc[pd.Period("2020-12"), "bm12"]
    )
    assert result.loc[pd.Period("2021-01"), "bm12"] == pytest.approx(
        1.01**12 - 1.005**12
    )
    data.loc[data.month.ge("2021-01"), "monthly_return"] = 999
    changed = maturity_signals(data).set_index("month")
    assert (
        changed.loc[pd.Period("2021-01"), "bm12"]
        == result.loc[pd.Period("2021-01"), "bm12"]
    )


def test_missing_calendar_month_cannot_be_bridged():
    result = maturity_signals(history().query("month != '2020-06'"))
    assert result.bm12.isna().all()


def test_missing_realized_return_invalidates_signal_window():
    data = history()
    data.loc[(data.month == "2020-06") & (data.nearby_rank == 2), "monthly_return"] = (
        np.nan
    )
    assert maturity_signals(data).bm12.isna().all()


def test_farther_signals_use_correct_ranks():
    result = maturity_signals(history()).dropna().iloc[0]
    assert result.bm23 == pytest.approx(1.005**12 - (1 + 0.01 / 3) ** 12)
    assert result.bm34 == pytest.approx((1 + 0.01 / 3) ** 12 - 1.0025**12)


def roll_fixture(same=False):
    jan, feb = pd.Period("2020-01"), pd.Period("2020-02")
    panel = pd.DataFrame(
        {
            "commodity": ["A", "A"],
            "month": [jan, feb],
            "nearby_rank": [1, 1],
            "futcode": ["OLD", "OLD" if same else "NEW"],
            "contract_month": [
                pd.Period("2020-05" if same else "2020-04"),
                pd.Period("2020-05"),
            ],
            "date_": pd.to_datetime(["2020-01-31", "2020-02-28"]),
            "settlement": [100.0, 100.0],
        }
    )
    raw = pd.DataFrame(
        {
            "futcode": ["OLD", "OLD", "NEW"],
            "date_": pd.to_datetime(["2020-01-31", "2020-02-28", "2020-02-28"]),
            "settlement": [100.0, 102.0, 100.0],
        }
    )
    returns = panel[["month", "nearby_rank"]].assign(monthly_return=[0.02, 0.03])
    return raw, panel, returns


def test_roll_prices_old_and_new_on_same_day():
    result = decomposition(*roll_fixture()).iloc[-1]
    assert result.roll_return == pytest.approx(0.02)
    assert result.spot_return == pytest.approx(1.03 / 1.02 - 1)
    assert result.monthly_return == pytest.approx(
        result.spot_return + result.roll_return + result.cross_term
    )


def test_nonroll_month_is_zero():
    result = decomposition(*roll_fixture(same=True)).iloc[-1]
    assert result.roll_return == 0
    assert result.spot_return == pytest.approx(0.03)


def test_missing_old_quote_is_not_zero_roll():
    raw, panel, ret = roll_fixture()
    result = decomposition(raw.iloc[[0, 2]], panel, ret).iloc[-1]
    assert pd.isna(result.roll_return)
    assert result.roll_status == "missing_old_price"


def test_unexpected_change_is_flagged_not_treated_as_paper_roll():
    raw, panel, ret = roll_fixture()
    panel.loc[0, "contract_month"] = pd.Period("2020-06")
    result = decomposition(raw, panel, ret).iloc[-1]
    assert result.roll_status == "unexpected_contract_change"
    assert pd.isna(result.roll_return)


def test_return_follows_contract_not_next_month_rank():
    raw = pd.DataFrame(
        {
            "futcode": ["MAY", "MAY", "JUNE"],
            "date_": pd.to_datetime(["2020-01-31", "2020-02-28", "2020-02-28"]),
            "settlement": [100.0, 110.0, 90.0],
        }
    )
    panel = pd.DataFrame(
        {
            "futcode": ["MAY", "JUNE"],
            "month": ["2020-01", "2020-02"],
            "settlement": [100.0, 90.0],
        }
    )
    result = build_monthly_returns(raw, panel)
    assert result.iloc[0].monthly_return == pytest.approx(0.10)


def test_kayla_t_plus_two_selection():
    raw = pd.DataFrame(
        {
            "futcode": ["MAR", "APR", "MAY", "JUN", "JUL"],
            "date_": pd.to_datetime(["2020-01-31"] * 5),
            "contrdate": ["0320", "0420", "0520", "0620", "0720"],
            "lasttrddate": pd.to_datetime(
                ["2020-03-20", "2020-04-20", "2020-05-20", "2020-06-20", "2020-07-20"]
            ),
        }
    )
    result = build_futures_panel(raw)
    assert result.futcode.tolist() == ["APR", "MAY", "JUN", "JUL"]


def cross_section(n=12):
    month = pd.Period("2020-01")
    signals = pd.DataFrame(
        [
            {
                "commodity": f"C{i:02}",
                "month": month,
                "bm12": i,
                "bm23": i,
                "bm34": -i,
                "basis": i,
                "momentum": i,
            }
            for i in range(n)
        ]
    )
    returns = pd.DataFrame(
        [
            {
                "commodity": f"C{i:02}",
                "month": month,
                "nearby_rank": rank,
                "monthly_return": i * 0.01 / rank,
            }
            for i in range(n)
            for rank in range(1, 5)
        ]
    )
    return signals, returns


def test_sort_is_across_commodities_and_has_four_each():
    signals, _ = cross_section()
    result = sort_members(signals, "bm12")
    assert result["High4"] == ["C08", "C09", "C10", "C11"]
    assert result["Low4"] == ["C00", "C01", "C02", "C03"]
    assert not set(result["High4"]) & set(result["Low4"])


def test_table4_two_layers_of_long_short():
    signals, ret = cross_section()
    series, _ = table4_series(signals, ret)
    selected = series.query("block=='bm12' and metric=='R2-R3'").iloc[0]
    assert selected.value == pytest.approx((9.5 - 1.5) * (0.01 / 2 - 0.01 / 3))


def test_no_reranking_when_selected_future_return_is_missing():
    signals, ret = cross_section()
    ret.loc[(ret.commodity == "C11") & (ret.nearby_rank == 2), "monthly_return"] = (
        np.nan
    )
    series, members = table4_series(signals, ret)
    assert pd.isna(series.query("block=='bm12' and metric=='R2'").iloc[0].value)
    assert "C11" in members.query("signal=='bm12' and side=='High4'").commodity.tolist()


def test_overlap_distinguishes_side_and_unsigned_membership():
    a = {"High4": [1, 2, 3, 4], "Low4": [5, 6, 7, 8]}
    b = {"High4": [5, 6, 7, 8], "Low4": [1, 2, 3, 4]}
    assert overlap_count(a, b, "same_side") == 0
    assert overlap_count(a, b, "union") == 8


def test_table5_decomposes_before_averaging_and_preserves_product():
    signals, _ = cross_section()
    components = signals[["commodity", "month"]].copy()
    components["monthly_return"] = np.linspace(-0.02, 0.05, len(signals))
    components["roll_return"] = np.linspace(-0.01, 0.03, len(signals))
    components["spot_return"] = (1 + components.monthly_return) / (
        1 + components.roll_return
    ) - 1
    components["cross_term"] = components.spot_return * components.roll_return
    series, _ = table5_series(signals, components)
    hl = (
        series.query("signal=='bm12' and portfolio=='High4-Low4'")
        .set_index("metric")
        .value
    )
    assert hl.futures == pytest.approx(hl.spot + hl.roll + hl.cross_term, abs=1e-12)
    expected_spot = (
        components.spot_return.iloc[-4:].mean() - components.spot_return.iloc[:4].mean()
    )
    assert hl.spot == pytest.approx(expected_spot)
    assert hl.spot != pytest.approx((1 + hl.futures) / (1 + hl.roll) - 1, abs=1e-7)
    # Missing outcomes invalidate the whole signal-month; they do not change sorting.
    components.loc[0, "spot_return"] = np.nan
    incomplete, _ = table5_series(signals, components)
    assert incomplete.value.isna().all()


def test_sample_filter_uses_realized_not_formation_month():
    data = pd.DataFrame(
        {
            "month": ["1985-12", "2014-02"],
            "holding_month": ["1986-01", "2014-03"],
            "value": [1, 2],
        }
    )
    assert within_sample(data).value.tolist() == [1]


def test_summary_units_and_iid_t():
    x = pd.Series([0.01, 0.02, 0.03])
    result = summary_stats(x)
    assert result["avg_ret"] == pytest.approx(24.0)
    assert result["t_stat"] == pytest.approx(0.02 / (0.01 / np.sqrt(3)))
    assert result["sharpe"] == pytest.approx(np.sqrt(12) * 2)


def test_missing_selected_member_does_not_reweight_remaining_assets():
    assert pd.isna(portfolio_mean(pd.Series({"A": 0.01, "B": np.nan}), ["A", "B"]))


def test_local_real_data_identities_when_cache_exists():
    """Real-data validation skips clean CI; synthetic economic tests always run."""
    from part4_config import DATA_DIR

    path = DATA_DIR / "components.parquet"
    if not path.exists():
        pytest.skip("WRDS local cache unavailable")
    comp = pd.read_parquet(path).dropna(
        subset=["monthly_return", "spot_return", "roll_return"]
    )
    assert len(comp) > 0
    np.testing.assert_allclose(
        comp.monthly_return,
        comp.spot_return + comp.roll_return + comp.cross_term,
        atol=1e-12,
        rtol=0,
    )
    assert comp.loc[~comp.is_roll, "roll_return"].eq(0).all()
