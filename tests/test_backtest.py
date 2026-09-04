"""Testes do motor de backtest: resolução de trade (SL/TP1/TP2/timeout) e a
regra de "STOP tem prioridade se ambos forem tocados na mesma barra"."""

from __future__ import annotations

import pandas as pd
import pytest

from backtest import Trade, _resolve_trade, fetch_extended_klines, simulate
from gorilatrader import ASSETS, DEFAULT_WEIGHTS
from tests.conftest import build_df
from unittest.mock import MagicMock, patch


def _bars_df(bars):
    """bars: lista de (open_time_ms, high, low, close)."""
    rows = [{"open_time": t, "open": c, "high": h, "low": l, "close": c, "vol": 1000.0} for t, h, l, c in bars]
    return pd.DataFrame(rows)


def _buy_trade(entry_price=100.0, sl=95.0, tp1=105.0, tp2=110.0):
    return Trade(direction="COMPRA", signal="COMPRA", entry_idx=0, entry_time=0,
                 entry_price=entry_price, sl=sl, tp1=tp1, tp2=tp2)


def _sell_trade(entry_price=100.0, sl=105.0, tp1=95.0, tp2=90.0):
    return Trade(direction="VENDA", signal="VENDA", entry_idx=0, entry_time=0,
                 entry_price=entry_price, sl=sl, tp1=tp1, tp2=tp2)


def test_buy_trade_hits_stop_loss():
    trade = _buy_trade()
    df = _bars_df([
        (1, 101, 99, 100),
        (2, 100, 94, 96),   # low <= sl(95)
    ])
    _resolve_trade(df, trade, max_holding_bars=10)
    assert trade.outcome == "STOP"
    assert trade.exit_price == 95.0
    assert trade.r_multiple == pytest.approx(-1.0)


def test_buy_trade_reaches_tp2_directly():
    trade = _buy_trade()
    df = _bars_df([
        (0, 101, 99, 100),   # barra de entrada (índice 0, não é verificada)
        (1, 111, 99, 108),   # high >= tp2(110) já na 1a barra verificada
    ])
    _resolve_trade(df, trade, max_holding_bars=10)
    assert trade.outcome == "TP2"
    assert trade.exit_price == 110.0
    assert trade.r_multiple == pytest.approx(2.0)  # risco=5, ganho=10


def test_buy_trade_touches_tp1_then_tp2():
    trade = _buy_trade()
    df = _bars_df([
        (1, 106, 99, 105),  # toca TP1
        (2, 111, 104, 109),  # depois toca TP2
    ])
    _resolve_trade(df, trade, max_holding_bars=10)
    assert trade.outcome == "TP2"


def test_buy_trade_touches_tp1_then_stop_is_stop_after_tp1():
    trade = _buy_trade()
    df = _bars_df([
        (0, 101, 99, 100),
        (1, 106, 99, 105),   # toca TP1
        (2, 100, 94, 96),    # depois volta e toca o SL original (sem trailing stop)
    ])
    _resolve_trade(df, trade, max_holding_bars=10)
    assert trade.outcome == "STOP_AFTER_TP1"
    assert trade.exit_price == 95.0


def test_ambiguous_bar_assumes_stop_hit_first():
    """Regra conservadora: se STOP e TP1/TP2 são tocados na MESMA barra, o
    backtest assume que o STOP foi atingido primeiro (não temos dados de tick
    para saber a ordem real)."""
    trade = _buy_trade()
    df = _bars_df([
        (0, 101, 99, 100),
        (1, 111, 94, 100),  # high >= tp2 E low <= sl na mesma barra
    ])
    _resolve_trade(df, trade, max_holding_bars=10)
    assert trade.outcome == "STOP"


def test_buy_trade_times_out_without_touching_anything():
    trade = _buy_trade()
    df = _bars_df([(i, 101, 99, 100) for i in range(1, 6)])
    _resolve_trade(df, trade, max_holding_bars=5)
    assert trade.outcome == "TIMEOUT"
    assert trade.exit_price == 100.0


def test_buy_trade_times_out_after_touching_tp1():
    trade = _buy_trade()
    bars = [(1, 106, 99, 105)] + [(i, 106, 104, 105) for i in range(2, 6)]
    df = _bars_df(bars)
    _resolve_trade(df, trade, max_holding_bars=5)
    assert trade.outcome == "TP1_TIMEOUT"


def test_sell_trade_hits_stop_loss():
    trade = _sell_trade()
    df = _bars_df([(0, 101, 99, 100), (1, 106, 99, 103)])  # high >= sl(105)
    _resolve_trade(df, trade, max_holding_bars=10)
    assert trade.outcome == "STOP"
    assert trade.r_multiple == pytest.approx(-1.0)


def test_sell_trade_hits_tp2():
    trade = _sell_trade()
    df = _bars_df([(0, 101, 99, 100), (1, 101, 89, 92)])  # low <= tp2(90)
    _resolve_trade(df, trade, max_holding_bars=10)
    assert trade.outcome == "TP2"
    assert trade.r_multiple == pytest.approx(2.0)


def test_simulate_does_not_open_second_trade_while_one_is_pending():
    """Anti-spam: sinais consecutivos na mesma direção não abrem uma nova
    entrada enquanto a anterior ainda não foi resolvida no loop principal -
    a simulação resolve cada trade antes de seguir, então nunca há
    sobreposição (mesma regra do dashboard ao vivo)."""
    df = build_df(prefix_n=200, tail_steps=[0.006] * 40)
    trades = simulate("TEST", ASSETS["BTC"], df, weights=DEFAULT_WEIGHTS, warmup=100)
    for i in range(1, len(trades)):
        assert trades[i].entry_idx > trades[i - 1].exit_idx


def _binance_row(open_time_ms):
    return [open_time_ms, "100", "101", "99", "100.5", "1000",
            open_time_ms + 3600000, "100000", 10, "500", "50000", "0"]


def test_fetch_extended_klines_paginates_backward_and_dedupes():
    # 2 páginas: a mais recente (1000 candles) + uma mais antiga (200 candles),
    # buscadas na ordem inversa (mais recente primeiro, depois endTime para trás)
    recent_batch = [_binance_row(t) for t in range(1000 * 3600000, 2000 * 3600000, 3600000)]
    older_batch = [_binance_row(t) for t in range(800 * 3600000, 1000 * 3600000, 3600000)]

    resp_recent = MagicMock(status_code=200)
    resp_recent.raise_for_status.return_value = None
    resp_recent.json.return_value = recent_batch

    resp_older = MagicMock(status_code=200)
    resp_older.raise_for_status.return_value = None
    resp_older.json.return_value = older_batch

    resp_empty = MagicMock(status_code=200)
    resp_empty.raise_for_status.return_value = None
    resp_empty.json.return_value = []

    with patch("backtest.requests.get", side_effect=[resp_recent, resp_older]) as mock_get:
        df = fetch_extended_klines("BTCUSDT", "binance_spot", total_candles=1200)

    assert mock_get.call_count == 2
    # segunda chamada deve pedir dados anteriores ao primeiro candle da 1a leva
    second_url = mock_get.call_args_list[1][0][0]
    assert f"endTime={recent_batch[0][0] - 1}" in second_url
    # resultado ordenado cronologicamente e sem duplicatas
    assert df["open_time"].is_monotonic_increasing
    assert df["open_time"].duplicated().sum() == 0
    assert len(df) == 1200  # recortado para o total pedido


def test_fetch_extended_klines_raises_when_no_data():
    resp_empty = MagicMock(status_code=200)
    resp_empty.raise_for_status.return_value = None
    resp_empty.json.return_value = []
    with patch("backtest.requests.get", return_value=resp_empty):
        with pytest.raises(RuntimeError):
            fetch_extended_klines("BTCUSDT", "binance_spot", total_candles=500)
