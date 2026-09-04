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


OKX_ROW = ["1700000000000", "100.0", "101.0", "99.0", "100.5", "1000.0", "100500.0", "100500.0", "1"]

KRAKEN_ROW = [1700000000, "100.0", "101.0", "99.0", "100.5", "100.2", "1000.0", 42]


def test_fetch_klines_uses_okx_when_configured():
    ok_response = MagicMock(status_code=200)
    ok_response.raise_for_status.return_value = None
    # OKX retorna do mais recente para o mais antigo
    ok_response.json.return_value = {"code": "0", "data": [OKX_ROW] * 60}

    with patch("gorilatrader.requests.get", return_value=ok_response) as mock_get:
        df = CryptoAnalyzer.fetch_klines("BTC-USDT", "okx", limit=60)

    assert df is not None
    assert len(df) == 60
    url = mock_get.call_args[0][0]
    assert "okx.com" in url
    assert "instId=BTC-USDT" in url
    assert "bar=1H" in url


def test_fetch_klines_okx_maps_4h_interval():
    ok_response = MagicMock(status_code=200)
    ok_response.raise_for_status.return_value = None
    ok_response.json.return_value = {"code": "0", "data": [OKX_ROW] * 60}

    with patch("gorilatrader.requests.get", return_value=ok_response) as mock_get:
        CryptoAnalyzer.fetch_klines("BTC-USDT", "okx", interval="4h", limit=60)

    assert "bar=4H" in mock_get.call_args[0][0]


def test_fetch_klines_returns_none_when_okx_has_no_data():
    empty_response = MagicMock(status_code=200)
    empty_response.raise_for_status.return_value = None
    empty_response.json.return_value = {"code": "0", "data": []}

    with patch("gorilatrader.requests.get", return_value=empty_response):
        df = CryptoAnalyzer.fetch_klines("BTC-USDT", "okx", limit=60)
    assert df is None


def test_fetch_klines_returns_none_when_okx_request_fails():
    with patch("gorilatrader.requests.get", return_value=_http_error_response()):
        df = CryptoAnalyzer.fetch_klines("BTC-USDT", "okx", limit=60)
    assert df is None


def test_fetch_klines_uses_kraken_when_configured():
    ok_response = MagicMock(status_code=200)
    ok_response.raise_for_status.return_value = None
    ok_response.json.return_value = {"error": [], "result": {"XBTUSDT": [KRAKEN_ROW] * 60, "last": 1700003600}}

    with patch("gorilatrader.requests.get", return_value=ok_response) as mock_get:
        df = CryptoAnalyzer.fetch_klines("XBTUSDT", "kraken", limit=60)

    assert df is not None
    assert len(df) == 60
    # segundos (Kraken) convertidos para milissegundos (mesmo formato interno das outras exchanges)
    assert df["open_time"].iloc[0] == KRAKEN_ROW[0] * 1000
    url = mock_get.call_args[0][0]
    assert "kraken.com" in url
    assert "pair=XBTUSDT" in url
    assert "interval=60" in url


def test_fetch_klines_kraken_maps_4h_interval():
    ok_response = MagicMock(status_code=200)
    ok_response.raise_for_status.return_value = None
    ok_response.json.return_value = {"error": [], "result": {"XBTUSDT": [KRAKEN_ROW] * 60, "last": 1700003600}}

    with patch("gorilatrader.requests.get", return_value=ok_response) as mock_get:
        CryptoAnalyzer.fetch_klines("XBTUSDT", "kraken", interval="4h", limit=60)

    assert "interval=240" in mock_get.call_args[0][0]


def test_fetch_klines_returns_none_when_kraken_returns_error():
    error_response = MagicMock(status_code=200)
    error_response.raise_for_status.return_value = None
    error_response.json.return_value = {"error": ["EQuery:Unknown asset pair"], "result": {}}

    with patch("gorilatrader.requests.get", return_value=error_response):
        df = CryptoAnalyzer.fetch_klines("XBTUSDT", "kraken", limit=60)
    assert df is None


def test_fetch_klines_returns_none_when_kraken_request_fails():
    with patch("gorilatrader.requests.get", return_value=_http_error_response()):
        df = CryptoAnalyzer.fetch_klines("XBTUSDT", "kraken", limit=60)
    assert df is None
