"""Testes dos favoritos do dashboard web como lista única e persistida do
servidor: favoritar um ticker o registra de verdade em ASSETS (então o
monitor de alertas em segundo plano passa a tocar apito/Telegram/abrir
posição no modo papel pra ele, igual um ativo de config.json), desfavoritar
remove - exceto ativos que já vinham de config.json antes de qualquer
favorito, esses nunca saem do monitor por aqui."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

import webserver


def _fake_request():
    return SimpleNamespace(cookies={})


@pytest.fixture(autouse=True)
def _isolate_favorites_state(tmp_path, monkeypatch):
    """Cada teste começa com ASSETS/_favorite_tickers do jeito que estavam
    (sem favoritos de um teste vazando pro outro) e nunca escreve no
    web_favorites.json real do projeto."""
    monkeypatch.setattr(webserver, "FAVORITES_PATH", str(tmp_path / "web_favorites.json"))
    original_assets = dict(webserver.ASSETS)
    original_favorites = set(webserver._favorite_tickers)
    yield
    webserver.ASSETS.clear()
    webserver.ASSETS.update(original_assets)
    webserver._favorite_tickers.clear()
    webserver._favorite_tickers.update(original_favorites)
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


def test_list_favorites_starts_empty():
    assert webserver.api_list_favorites(_fake_request()) == {}


def test_add_favorite_registers_it_as_a_monitored_asset():
    with patch("gorilatrader.requests.get", return_value=_binance_response(0.08)):
        payload = webserver.api_add_favorite("doge", _fake_request())

    assert payload == {"key": "DOGE", "name": "DOGE", "icon": "🪙", "decimals": 4}
    assert "DOGE" in webserver.ASSETS  # entra no monitor de alertas/modo papel
    assert "DOGE" in webserver._favorite_tickers
    assert webserver.api_list_favorites(_fake_request()) == {
        "DOGE": {"name": "DOGE", "icon": "🪙", "decimals": 4}
    }


def test_add_favorite_persists_to_disk():
    with patch("gorilatrader.requests.get", return_value=_binance_response(0.08)):
        webserver.api_add_favorite("doge", _fake_request())

    with open(webserver.FAVORITES_PATH, encoding="utf-8") as f:
        import json
        assert json.load(f) == ["DOGE"]


def test_add_favorite_404_for_unresolvable_ticker_and_does_not_mutate_state():
    with patch("gorilatrader.requests.get", return_value=_empty_response()):
        with pytest.raises(HTTPException) as exc_info:
            webserver.api_add_favorite("naoexistetickerxyz", _fake_request())

    assert exc_info.value.status_code == 404
    assert "NAOEXISTETICKERXYZ" not in webserver.ASSETS
    assert "NAOEXISTETICKERXYZ" not in webserver._favorite_tickers


def test_remove_favorite_stops_monitoring_it():
    with patch("gorilatrader.requests.get", return_value=_binance_response(0.08)):
        webserver.api_add_favorite("doge", _fake_request())

    result = webserver.api_remove_favorite("doge", _fake_request())

    assert result == {"ok": True}
    assert "DOGE" not in webserver.ASSETS
    assert "DOGE" not in webserver._favorite_tickers


def test_remove_favorite_never_removes_a_real_configured_asset():
    """BTC é um ativo real (config.json), não um favorito - desfavoritar
    (mesmo que nunca tenha sido favoritado) nunca pode tirá-lo do monitor."""
    assert "BTC" in webserver._original_asset_keys

    result = webserver.api_remove_favorite("btc", _fake_request())

    assert result == {"ok": True}
    assert "BTC" in webserver.ASSETS


def test_load_web_favorites_restores_persisted_tickers(tmp_path, monkeypatch):
    import json

    path = tmp_path / "web_favorites.json"
    path.write_text(json.dumps(["DOGE"]), encoding="utf-8")
    monkeypatch.setattr(webserver, "FAVORITES_PATH", str(path))

    with patch("gorilatrader.requests.get", return_value=_binance_response(0.08)):
        webserver._load_web_favorites()

    assert "DOGE" in webserver.ASSETS
    assert "DOGE" in webserver._favorite_tickers


def test_load_web_favorites_skips_tickers_that_no_longer_resolve(tmp_path, monkeypatch):
    import json

    path = tmp_path / "web_favorites.json"
    path.write_text(json.dumps(["NAOEXISTETICKERXYZ"]), encoding="utf-8")
    monkeypatch.setattr(webserver, "FAVORITES_PATH", str(path))

    with patch("gorilatrader.requests.get", return_value=_empty_response()):
        webserver._load_web_favorites()

    assert "NAOEXISTETICKERXYZ" not in webserver.ASSETS
    assert "NAOEXISTETICKERXYZ" not in webserver._favorite_tickers


def test_load_web_favorites_tolerates_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(webserver, "FAVORITES_PATH", str(tmp_path / "does_not_exist.json"))
    webserver._load_web_favorites()  # não deve levantar
    assert webserver._favorite_tickers == set()


def test_load_web_favorites_tolerates_corrupted_file(tmp_path, monkeypatch):
    path = tmp_path / "web_favorites.json"
    path.write_text("isso não é json", encoding="utf-8")
    monkeypatch.setattr(webserver, "FAVORITES_PATH", str(path))
    webserver._load_web_favorites()  # não deve levantar
    assert webserver._favorite_tickers == set()
