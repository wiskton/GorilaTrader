"""Testes do padrão de gatilhos de aviso: o Telegram só recebe sinais de
entrada de "mais certeza" (FORTE COMPRA/FORTE VENDA) - sinais fracos
(COMPRA/VENDA) continuam tocando o apito e entrando no histórico do
dashboard normalmente, só não vão pro Telegram (ficam reservados pros
alertas de rompimento/RSI/Bollinger). E um novo aviso de conclusão da
operação (STOP/TP) do modo papel, só pra trades abertos por sinal FORTE."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import gorilatrader as g
from gorilatrader import ASSETS, DEFAULT_WEIGHTS, CryptoAnalyzer
from paper_trading import PaperTrade
from tests.conftest import build_df


def _build_terminal():
    terminal = g.GorilaTraderTerminal(
        sound_enabled=False,
        telegram_token="TOKEN",
        telegram_chat_id="@canal",
        paper_trading_enabled=False,
    )
    terminal.telegram.send = MagicMock()
    terminal.sound.play_buy_alert = MagicMock()
    terminal.sound.play_sell_alert = MagicMock()
    return terminal


def _buy_item(signal="COMPRA"):
    df = build_df(prefix_n=200, tail_steps=[0.006] * 40)
    item = CryptoAnalyzer.analyze_dataframe("BTC", ASSETS["BTC"], df, DEFAULT_WEIGHTS)
    item.signal = signal
    return item


def _sell_item(signal="VENDA"):
    df = build_df(prefix_n=200, tail_steps=[-0.006] * 40)
    item = CryptoAnalyzer.analyze_dataframe("BTC", ASSETS["BTC"], df, DEFAULT_WEIGHTS)
    item.signal = signal
    return item


def test_weak_buy_signal_sounds_and_records_history_but_skips_telegram():
    terminal = _build_terminal()
    before = len(terminal.history_alerts)
    with patch("gorilatrader.save_alert_history"):
        terminal.check_and_alert(_buy_item("COMPRA"))

    terminal.sound.play_buy_alert.assert_called_once()
    assert len(terminal.history_alerts) == before + 1
    assert terminal.history_alerts[-1]["signal"] == "COMPRA"
    terminal.telegram.send.assert_not_called()


def test_strong_buy_signal_sends_telegram():
    terminal = _build_terminal()
    with patch("gorilatrader.save_alert_history"):
        terminal.check_and_alert(_buy_item("FORTE COMPRA"))

    terminal.sound.play_buy_alert.assert_called_once()
    terminal.telegram.send.assert_called_once()


def test_weak_sell_signal_skips_telegram():
    terminal = _build_terminal()
    with patch("gorilatrader.save_alert_history"):
        terminal.check_and_alert(_sell_item("VENDA"))
    terminal.telegram.send.assert_not_called()


def test_strong_sell_signal_sends_telegram():
    terminal = _build_terminal()
    with patch("gorilatrader.save_alert_history"):
        terminal.check_and_alert(_sell_item("FORTE VENDA"))
    terminal.telegram.send.assert_called_once()


def test_extreme_alerts_still_always_send_telegram_regardless_of_confidence():
    """Alertas de rompimento (RSI/Bollinger) não são sinais de entrada - devem
    continuar indo pro Telegram sempre, independente do filtro de "mais certeza"."""
    terminal = _build_terminal()
    item = _buy_item("AGUARDAR")
    item.rsi = 85.0
    with patch("gorilatrader.save_alert_history"):
        terminal.check_extreme_alerts(item)
    terminal.telegram.send.assert_called_once()


def _make_trade(signal: str, outcome: str, r_multiple: float = 1.0, pct_return: float = 1.0) -> PaperTrade:
    trade = PaperTrade(
        asset_key="BTC", direction="COMPRA" if "COMPRA" in signal else "VENDA", signal=signal,
        entry_time="2026-01-01T00:00:00", entry_price=100.0, sl=95.0, tp1=105.0, tp2=110.0,
    )
    trade.exit_price = 110.0
    trade.outcome = outcome
    trade.r_multiple = r_multiple
    trade.pct_return = pct_return
    return trade


def test_trade_conclusion_stop_sends_loss_styled_telegram():
    terminal = _build_terminal()
    before = len(terminal.history_alerts)
    trade = _make_trade("FORTE COMPRA", "STOP", r_multiple=-1.0, pct_return=-1.0)
    with patch("gorilatrader.save_alert_history"):
        terminal._record_trade_conclusion(trade)

    terminal.telegram.send.assert_called_once()
    text = terminal.telegram.send.call_args[0][0]
    assert "STOP" in text
    assert text.startswith("🔴")
    assert len(terminal.history_alerts) == before + 1
    assert "STOP" in terminal.history_alerts[-1]["signal"]


def test_trade_conclusion_tp2_sends_win_styled_telegram():
    terminal = _build_terminal()
    trade = _make_trade("FORTE VENDA", "TP2", r_multiple=2.0, pct_return=2.0)
    with patch("gorilatrader.save_alert_history"):
        terminal._record_trade_conclusion(trade)

    text = terminal.telegram.send.call_args[0][0]
    assert "TAKE PROFIT" in text
    assert text.startswith("🟢")


def test_refresh_sends_conclusion_alert_only_for_high_confidence_trades():
    terminal = _build_terminal()
    item = _buy_item("COMPRA")  # sinal atual do ativo não importa aqui, só o trade fechado

    strong_trade = _make_trade("FORTE COMPRA", "TP2", r_multiple=2.0, pct_return=2.0)
    weak_trade = _make_trade("COMPRA", "TP2", r_multiple=2.0, pct_return=2.0)

    fake_paper = MagicMock()
    terminal.paper = fake_paper

    with patch("gorilatrader.save_alert_history"), \
         patch.object(terminal, "fetch_all", return_value={"BTC": item}), \
         patch.object(terminal, "check_and_alert"), \
         patch.object(terminal, "check_extreme_alerts"):

        fake_paper.update.return_value = weak_trade
        terminal.refresh({})
        terminal.telegram.send.assert_not_called()

        fake_paper.update.return_value = strong_trade
        terminal.refresh({})
        terminal.telegram.send.assert_called_once()
