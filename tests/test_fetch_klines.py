"""Testes de CryptoAnalyzer.fetch_klines: fallback Binance -> Bybit, e uma
regressão para o símbolo passado ao Bybit (havia um `.replace("USDT","USDT")`
sem efeito que sugeria uma conversão nunca implementada - o símbolo deve
chegar intacto na URL do Bybit)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import requests

from gorilatrader import CryptoAnalyzer

BINANCE_ROW = [1700000000000, "100.0", "101.0", "99.0", "100.5", "1000.0",
               1700003600000, "100000.0", 10, "500.0", "50000.0", "0"]

BYBIT_ROW = ["1700000000000", "100.0", "101.0", "99.0", "100.5", "1000.0", "100000.0"]


def _http_error_response():
    resp = MagicMock(status_code=400)
    resp.raise_for_status.side_effect = requests.exceptions.HTTPError("400 Bad Request")
    return resp


def test_fetch_klines_uses_binance_when_available():
    ok_response = MagicMock(status_code=200)
    ok_response.raise_for_status.return_value = None
    ok_response.json.return_value = [BINANCE_ROW] * 60

    with patch("gorilatrader.requests.get", return_value=ok_response) as mock_get:
        df = CryptoAnalyzer.fetch_klines("BTCUSDT", "binance_spot", limit=60)

    assert df is not None
    assert len(df) == 60
    mock_get.assert_called_once()
    assert "binance.com" in mock_get.call_args[0][0]


def test_fetch_klines_falls_back_to_bybit_when_binance_fails():
    bybit_response = MagicMock(status_code=200)
    bybit_response.raise_for_status.return_value = None
    bybit_response.json.return_value = {"result": {"list": [BYBIT_ROW] * 60}}

    with patch("gorilatrader.requests.get", side_effect=[_http_error_response(), bybit_response]) as mock_get:
        df = CryptoAnalyzer.fetch_klines("BTCUSDT", "binance_spot", limit=60)

    assert df is not None
    assert len(df) == 60
    assert mock_get.call_count == 2
    bybit_url = mock_get.call_args_list[1][0][0]
    assert "bybit.com" in bybit_url
    # regressão: o símbolo deve chegar intacto na URL do Bybit, sem mangling
    assert "symbol=BTCUSDT" in bybit_url


def test_fetch_klines_returns_none_when_both_exchanges_fail():
    with patch("gorilatrader.requests.get", side_effect=[_http_error_response(), _http_error_response()]):
        df = CryptoAnalyzer.fetch_klines("BTCUSDT", "binance_spot", limit=60)
    assert df is None


def test_fetch_klines_returns_none_when_bybit_has_no_data():
    empty_bybit_response = MagicMock(status_code=200)
    empty_bybit_response.raise_for_status.return_value = None
    empty_bybit_response.json.return_value = {"result": {"list": []}}

    with patch("gorilatrader.requests.get", side_effect=[_http_error_response(), empty_bybit_response]):
        df = CryptoAnalyzer.fetch_klines("BTCUSDT", "binance_spot", limit=60)
    assert df is None


def test_fetch_klines_uses_futures_url_for_futures_exchange():
    ok_response = MagicMock(status_code=200)
    ok_response.raise_for_status.return_value = None
    ok_response.json.return_value = [BINANCE_ROW] * 60

    with patch("gorilatrader.requests.get", return_value=ok_response) as mock_get:
        CryptoAnalyzer.fetch_klines("HYPEUSDT", "binance_futures", limit=60)

    assert "fapi.binance.com" in mock_get.call_args[0][0]
