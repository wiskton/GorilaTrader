"""Testes do modo papel (paper_trading.py): abertura na transição de sinal,
uma posição por ativo, resolução contra STOP/TP2/timeout e persistência."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from paper_trading import PaperTrade, PaperTradingEngine


@dataclass
class FakeMarketData:
    """Só os campos que PaperTradingEngine realmente lê de MarketData -
    evita depender da fixture pesada de CryptoAnalyzer.analyze_dataframe."""
    asset_key: str
    signal: str
    price: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float


def make_buy_item(price=100.0, sl=95.0, tp1=105.0, tp2=110.0, signal="COMPRA", key="BTC"):
    return FakeMarketData(asset_key=key, signal=signal, price=price, stop_loss=sl, take_profit_1=tp1, take_profit_2=tp2)


def make_sell_item(price=100.0, sl=105.0, tp1=95.0, tp2=90.0, signal="VENDA", key="BTC"):
    return FakeMarketData(asset_key=key, signal=signal, price=price, stop_loss=sl, take_profit_1=tp1, take_profit_2=tp2)


def test_maybe_open_ignores_non_fresh_signal(tmp_path):
    engine = PaperTradingEngine(str(tmp_path / "paper_trades.json"))
    trade = engine.maybe_open(make_buy_item(), is_fresh_buy=False, is_fresh_sell=False)
    assert trade is None
    assert engine.open_trades == {}


def test_maybe_open_opens_buy_on_fresh_signal(tmp_path):
    engine = PaperTradingEngine(str(tmp_path / "paper_trades.json"))
    trade = engine.maybe_open(make_buy_item(price=100.0, sl=95.0, tp1=105.0, tp2=110.0), is_fresh_buy=True, is_fresh_sell=False)

    assert trade is not None
    assert trade.direction == "COMPRA"
    assert trade.entry_price == 100.0
    assert engine.open_trades["BTC"] is trade


def test_maybe_open_does_not_stack_second_position_same_asset(tmp_path):
    engine = PaperTradingEngine(str(tmp_path / "paper_trades.json"))
    engine.maybe_open(make_buy_item(), is_fresh_buy=True, is_fresh_sell=False)
    second = engine.maybe_open(make_buy_item(price=200.0), is_fresh_buy=True, is_fresh_sell=False)

    assert second is None
    assert len(engine.open_trades) == 1
    assert engine.open_trades["BTC"].entry_price == 100.0


def test_update_closes_at_take_profit_2(tmp_path):
    engine = PaperTradingEngine(str(tmp_path / "paper_trades.json"))
    engine.maybe_open(make_buy_item(price=100.0, sl=95.0, tp1=105.0, tp2=110.0), is_fresh_buy=True, is_fresh_sell=False)

    closed = engine.update(make_buy_item(price=111.0))

    assert closed is not None
    assert closed.outcome == "TP2"
    assert closed.exit_price == 110.0
    assert closed.r_multiple == 2.0  # risco de 5, alvo a 10 de distância -> 2R
    assert "BTC" not in engine.open_trades
    assert engine.closed_trades == [closed]


def test_update_closes_at_stop_loss(tmp_path):
    engine = PaperTradingEngine(str(tmp_path / "paper_trades.json"))
    engine.maybe_open(make_buy_item(price=100.0, sl=95.0, tp1=105.0, tp2=110.0), is_fresh_buy=True, is_fresh_sell=False)

    closed = engine.update(make_buy_item(price=94.0))

    assert closed.outcome == "STOP"
    assert closed.exit_price == 95.0
    assert closed.r_multiple == -1.0


def test_update_marks_stop_after_tp1_when_tp1_reached_first(tmp_path):
    engine = PaperTradingEngine(str(tmp_path / "paper_trades.json"))
    engine.maybe_open(make_buy_item(price=100.0, sl=95.0, tp1=105.0, tp2=110.0), is_fresh_buy=True, is_fresh_sell=False)

    mid = engine.update(make_buy_item(price=106.0))
    assert mid is None  # só marca TP1, não fecha
    assert engine.open_trades["BTC"].reached_tp1 is True

    closed = engine.update(make_buy_item(price=94.0))
    assert closed.outcome == "STOP_AFTER_TP1"


def test_update_resolves_sell_direction_correctly(tmp_path):
    engine = PaperTradingEngine(str(tmp_path / "paper_trades.json"))
    engine.maybe_open(make_sell_item(price=100.0, sl=105.0, tp1=95.0, tp2=90.0), is_fresh_sell=True, is_fresh_buy=False)

    closed = engine.update(make_sell_item(price=89.0))

    assert closed.outcome == "TP2"
    assert closed.exit_price == 90.0
    assert closed.r_multiple == 2.0


def test_update_times_out_after_max_holding_hours(tmp_path):
    engine = PaperTradingEngine(str(tmp_path / "paper_trades.json"), max_holding_hours=1)
    engine.maybe_open(make_buy_item(price=100.0, sl=95.0, tp1=105.0, tp2=110.0), is_fresh_buy=True, is_fresh_sell=False)
    engine.open_trades["BTC"].entry_time = (datetime.now() - timedelta(hours=2)).isoformat(timespec="seconds")

    closed = engine.update(make_buy_item(price=101.0))

    assert closed.outcome == "TIMEOUT"
    assert closed.exit_price == 101.0


def test_update_returns_none_when_no_open_trade(tmp_path):
    engine = PaperTradingEngine(str(tmp_path / "paper_trades.json"))
    assert engine.update(make_buy_item()) is None


def test_persistence_round_trip_across_instances(tmp_path):
    path = str(tmp_path / "paper_trades.json")
    engine = PaperTradingEngine(path)
    engine.maybe_open(make_buy_item(key="BTC", price=100.0, sl=95.0, tp1=105.0, tp2=110.0), is_fresh_buy=True, is_fresh_sell=False)
    engine.maybe_open(make_sell_item(key="ETH", price=50.0, sl=52.0, tp1=48.0, tp2=45.0), is_fresh_sell=True, is_fresh_buy=False)
    engine.update(make_buy_item(key="BTC", price=111.0))  # fecha BTC em TP2

    reloaded = PaperTradingEngine(path)
    assert set(reloaded.open_trades.keys()) == {"ETH"}
    assert len(reloaded.closed_trades) == 1
    assert reloaded.closed_trades[0].asset_key == "BTC"
    assert reloaded.closed_trades[0].outcome == "TP2"


def test_summary_computes_win_rate_and_totals(tmp_path):
    engine = PaperTradingEngine(str(tmp_path / "paper_trades.json"))
    win = PaperTrade(
        asset_key="BTC", direction="COMPRA", signal="COMPRA",
        entry_time=datetime.now().isoformat(timespec="seconds"), entry_price=100.0,
        sl=95.0, tp1=105.0, tp2=110.0,
    )
    win.close(110.0, "TP2")
    loss = PaperTrade(
        asset_key="ETH", direction="VENDA", signal="VENDA",
        entry_time=datetime.now().isoformat(timespec="seconds"), entry_price=50.0,
        sl=52.0, tp1=48.0, tp2=45.0,
    )
    loss.close(52.0, "STOP")
    engine.closed_trades = [win, loss]

    summary = engine.summary()

    assert summary["TODOS"]["trades"] == 2
    assert summary["TODOS"]["wins"] == 1
    assert summary["TODOS"]["losses"] == 1
    assert summary["TODOS"]["win_rate"] == 50.0
    assert summary["COMPRA"]["trades"] == 1
    assert summary["VENDA"]["trades"] == 1


def test_summary_reports_zero_trades_when_empty(tmp_path):
    engine = PaperTradingEngine(str(tmp_path / "paper_trades.json"))
    summary = engine.summary()
    assert summary["TODOS"] == {"trades": 0}
