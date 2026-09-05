"""Testes do backend do dashboard web (webserver.py): resolução de ativos
"favoritos" digitados no navegador (que podem não estar em ASSETS) e o
endpoint de performance do modo papel. Chama as funções das rotas FastAPI
diretamente (sem TestClient/ASGI) - elas são funções Python comuns, então
isso evita depender de um cliente HTTP só pra testar a lógica."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

import webserver
from paper_trading import PaperTrade


@pytest.fixture(autouse=True)
def _clear_extra_assets_cache():
    webserver._extra_assets_cache.clear()
    yield
    webserver._extra_assets_cache.clear()


def _binance_response(price: float):
    row = [1700000000000, str(price), str(price), str(price), str(price),
           "1000.0", 1700003600000, "0.0", 10, "0.0", "0.0", "0"]
    resp = MagicMock(status_code=200)
    resp.raise_for_status.return_value = None
    resp.json.return_value = [row, row]
    return resp


def _empty_response():
    resp = MagicMock(status_code=200)
    resp.raise_for_status.return_value = None
    resp.json.return_value = []
    return resp


def _fake_request():
    """Autenticação está desativada neste ambiente de teste (sem senha
    configurada), então require_auth passa direto independente de cookies -
    só precisa de um objeto com `.cookies` pra bater a assinatura da rota."""
    return SimpleNamespace(cookies={})


def test_resolve_asset_config_reuses_currently_configured_asset():
    cfg = webserver.resolve_asset_config("btc")
    assert cfg is webserver.ASSETS["BTC"]


def test_resolve_asset_config_falls_back_to_default_asset(monkeypatch):
    monkeypatch.setattr(webserver, "ASSETS", {"ETH": webserver.ASSETS["ETH"]})
    cfg = webserver.resolve_asset_config("btc")
    assert cfg == webserver.DEFAULT_ASSETS["BTC"]


def test_resolve_asset_config_builds_new_asset_with_detected_decimals():
    with patch("gorilatrader.requests.get", return_value=_binance_response(0.08)):
        cfg = webserver.resolve_asset_config("doge")

    assert cfg == {
        "name": "DOGE",
        "symbol": "DOGEUSDT",
        "exchange": "binance_spot",
        "icon": "🪙",
        "decimals": 4,
    }


def test_resolve_asset_config_returns_none_when_symbol_not_found():
    with patch("gorilatrader.requests.get", return_value=_empty_response()):
        cfg = webserver.resolve_asset_config("naoexistetickerxyz")
    assert cfg is None


def test_resolve_asset_config_caches_new_asset_across_calls():
    with patch("gorilatrader.requests.get", return_value=_binance_response(0.08)) as mock_get:
        webserver.resolve_asset_config("doge")
        webserver.resolve_asset_config("doge")

    assert mock_get.call_count == 1


def test_api_resolve_returns_payload_for_known_ticker():
    payload = webserver.api_resolve("btc", _fake_request())
    assert payload == {"key": "BTC", "name": "Bitcoin", "icon": "₿", "decimals": 2}


def test_api_resolve_returns_404_for_unresolvable_ticker():
    with patch("gorilatrader.requests.get", return_value=_empty_response()):
        with pytest.raises(HTTPException) as exc_info:
            webserver.api_resolve("naoexistetickerxyz", _fake_request())
    assert exc_info.value.status_code == 404


def test_api_chart_uses_resolved_favorite_not_in_assets():
    row = [1700000000000, "0.08", "0.08", "0.08", "0.08",
           "1000.0", 1700003600000, "0.0", 10, "0.0", "0.0", "0"]
    resp = MagicMock(status_code=200)
    resp.raise_for_status.return_value = None
    resp.json.return_value = [row] * 60

    with patch("gorilatrader.requests.get", return_value=resp):
        response = webserver.api_chart("doge", _fake_request())

    import json
    payload = json.loads(response.body)
    assert payload["key"] == "DOGE"
    assert len(payload["candles"]) == 60


def test_api_chart_includes_ema14_and_volume_ma21():
    row = [1700000000000, "100.0", "101.0", "99.0", "100.5", "1000.0",
           1700003600000, "0.0", 10, "0.0", "0.0", "0"]
    resp = MagicMock(status_code=200)
    resp.raise_for_status.return_value = None
    resp.json.return_value = [row] * 60

    with patch("gorilatrader.requests.get", return_value=resp):
        response = webserver.api_chart("btc", _fake_request())

    import json
    payload = json.loads(response.body)
    assert "ema14" in payload
    assert "volume_ma21" in payload
    assert len(payload["ema14"]) == 60
    assert payload["interval"] == "1h"


def test_api_chart_rejects_invalid_interval():
    with pytest.raises(HTTPException) as exc_info:
        webserver.api_chart("btc", _fake_request(), interval="2h")
    assert exc_info.value.status_code == 400


def test_api_chart_uses_requested_interval():
    row = [1700000000000, "100.0", "101.0", "99.0", "100.5", "1000.0",
           1700003600000, "0.0", 10, "0.0", "0.0", "0"]
    resp = MagicMock(status_code=200)
    resp.raise_for_status.return_value = None
    resp.json.return_value = [row] * 60

    with patch("gorilatrader.requests.get", return_value=resp) as mock_get:
        response = webserver.api_chart("btc", _fake_request(), interval="4h")

    import json
    payload = json.loads(response.body)
    assert payload["interval"] == "4h"
    assert "interval=4h" in mock_get.call_args[0][0]


def test_api_chart_404_for_unresolvable_ticker():
    with patch("gorilatrader.requests.get", return_value=_empty_response()):
        with pytest.raises(HTTPException) as exc_info:
            webserver.api_chart("naoexistetickerxyz", _fake_request())
    assert exc_info.value.status_code == 404


def test_api_paper_trading_reports_disabled_when_engine_missing(monkeypatch):
    monkeypatch.setattr(webserver.alert_monitor, "paper", None)
    payload = webserver.api_paper_trading(_fake_request())
    assert payload == {"enabled": False, "summary": {}, "open": [], "closed": [], "decimals": {}}


def test_api_paper_trading_reports_open_and_closed_trades(monkeypatch):
    fake_engine = MagicMock()
    fake_engine.summary.return_value = {"TODOS": {"trades": 1}}
    open_trade = PaperTrade(
        asset_key="BTC", direction="COMPRA", signal="COMPRA",
        entry_time="2026-01-01T00:00:00", entry_price=100.0, sl=95.0, tp1=105.0, tp2=110.0,
    )
    closed_trade = PaperTrade(
        asset_key="ETH", direction="VENDA", signal="VENDA",
        entry_time="2026-01-01T00:00:00", entry_price=50.0, sl=52.0, tp1=48.0, tp2=45.0,
    )
    closed_trade.close(45.0, "TP2")
    fake_engine.open_trades = {"BTC": open_trade}
    fake_engine.closed_trades = [closed_trade]
    monkeypatch.setattr(webserver.alert_monitor, "paper", fake_engine)

    payload = webserver.api_paper_trading(_fake_request())

    assert payload["enabled"] is True
    assert payload["summary"] == {"TODOS": {"trades": 1}}
    assert payload["open"][0]["asset_key"] == "BTC"
    assert payload["closed"][0]["outcome"] == "TP2"
    assert payload["decimals"]["BTC"] == webserver.ASSETS["BTC"]["decimals"]


def test_api_paper_trading_limits_closed_trades_to_last_30(monkeypatch):
    fake_engine = MagicMock()
    fake_engine.summary.return_value = {}
    fake_engine.open_trades = {}
    trades = []
    for i in range(40):
        t = PaperTrade(
            asset_key="BTC", direction="COMPRA", signal="COMPRA",
            entry_time=f"2026-01-01T00:00:{i:02d}", entry_price=100.0, sl=95.0, tp1=105.0, tp2=110.0,
        )
        t.close(110.0, "TP2")
        trades.append(t)
    fake_engine.closed_trades = trades
    monkeypatch.setattr(webserver.alert_monitor, "paper", fake_engine)

    payload = webserver.api_paper_trading(_fake_request())

    assert len(payload["closed"]) == 30
    assert payload["closed"][0]["entry_time"] == "2026-01-01T00:00:10"


def test_favicon_serves_the_project_icon():
    response = webserver.favicon()
    assert response.media_type == "image/png"
    assert response.path == webserver.FAVICON_PATH
    import os
    assert os.path.exists(webserver.FAVICON_PATH)
