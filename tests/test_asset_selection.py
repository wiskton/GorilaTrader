"""Testes de resolve_assets_from_tickers/--assets: a pessoa digita quais
criptos quer acompanhar (na flag ou no prompt interativo do terminal), e o
programa monta a config do ativo sozinho quando não é um dos já conhecidos."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd

from gorilatrader import DEFAULT_ASSETS, _detect_display_decimals, resolve_assets_from_tickers

BINANCE_ROW_TEMPLATE = [1700000000000, "0.0", "0.0", "0.0", None,
                        "1000.0", 1700003600000, "0.0", 10, "0.0", "0.0", "0"]


def _binance_response(price: float):
    row = list(BINANCE_ROW_TEMPLATE)
    row[4] = str(price)
    ok_response = MagicMock(status_code=200)
    ok_response.raise_for_status.return_value = None
    ok_response.json.return_value = [row, row]
    return ok_response


def test_detect_display_decimals_buckets():
    assert _detect_display_decimals(79000.0) == 2
    assert _detect_display_decimals(1.0) == 2
    assert _detect_display_decimals(0.5) == 4
    assert _detect_display_decimals(0.01) == 4
    assert _detect_display_decimals(0.005) == 6
    assert _detect_display_decimals(0.0001) == 6
    assert _detect_display_decimals(0.00001) == 8


def test_resolve_reuses_currently_configured_asset():
    resolved = resolve_assets_from_tickers("btc")
    assert resolved == {"BTC": DEFAULT_ASSETS["BTC"]}


def test_resolve_is_case_insensitive_and_trims_whitespace():
    resolved = resolve_assets_from_tickers("  btc , Eth  ")
    assert set(resolved.keys()) == {"BTC", "ETH"}


def test_resolve_accepts_semicolon_separator():
    resolved = resolve_assets_from_tickers("btc; eth")
    assert set(resolved.keys()) == {"BTC", "ETH"}


def test_resolve_ignores_empty_entries():
    resolved = resolve_assets_from_tickers("btc,, ,eth")
    assert set(resolved.keys()) == {"BTC", "ETH"}


def test_resolve_builds_new_asset_with_detected_decimals():
    with patch("gorilatrader.requests.get", return_value=_binance_response(0.08)):
        resolved = resolve_assets_from_tickers("DOGE")

    assert resolved["DOGE"] == {
        "name": "DOGE",
        "symbol": "DOGEUSDT",
        "exchange": "binance_spot",
        "icon": "🪙",
        "decimals": 4,
    }


def test_resolve_falls_back_to_2_decimals_when_symbol_not_found():
    empty_response = MagicMock(status_code=200)
    empty_response.raise_for_status.return_value = None
    empty_response.json.return_value = []

    with patch("gorilatrader.requests.get", return_value=empty_response):
        resolved = resolve_assets_from_tickers("NAOEXISTETICKER")

    assert resolved["NAOEXISTETICKER"]["decimals"] == 2
    assert resolved["NAOEXISTETICKER"]["symbol"] == "NAOEXISTETICKERUSDT"


def test_resolve_warns_console_when_symbol_not_found():
    empty_response = MagicMock(status_code=200)
    empty_response.raise_for_status.return_value = None
    empty_response.json.return_value = []
    console = MagicMock()

    with patch("gorilatrader.requests.get", return_value=empty_response):
        resolve_assets_from_tickers("NAOEXISTETICKER", console=console)

    console.print.assert_called_once()
    assert "NAOEXISTETICKER" in console.print.call_args[0][0]


def test_resolve_mixes_known_and_new_tickers():
    with patch("gorilatrader.requests.get", return_value=_binance_response(0.08)):
        resolved = resolve_assets_from_tickers("BTC,DOGE")

    assert resolved["BTC"] == DEFAULT_ASSETS["BTC"]
    assert resolved["DOGE"]["symbol"] == "DOGEUSDT"
