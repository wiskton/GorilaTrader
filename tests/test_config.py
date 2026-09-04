"""Testes de config.json: merge com os padrões, tolerância a arquivo ausente
ou malformado (o programa nunca deve quebrar por causa de config.json)."""

from __future__ import annotations

import json

from gorilatrader import DEFAULT_ASSETS, DEFAULT_PAPER_TRADING_CFG, DEFAULT_WEIGHTS, load_config


def test_load_config_returns_defaults_when_file_missing(tmp_path):
    missing_path = tmp_path / "does_not_exist.json"
    assets, weights, telegram, paper_trading = load_config(str(missing_path))
    assert assets == DEFAULT_ASSETS
    assert weights == DEFAULT_WEIGHTS
    assert telegram == {}
    assert paper_trading == DEFAULT_PAPER_TRADING_CFG


def test_load_config_merges_partial_weights(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"weights": {"rsi_extreme": 999}}), encoding="utf-8")

    assets, weights, telegram, paper_trading = load_config(str(path))

    assert assets == DEFAULT_ASSETS  # não sobrescrito, mantém o padrão
    assert weights["rsi_extreme"] == 999
    # chaves não mencionadas continuam com o valor padrão
    assert weights["macd_cross"] == DEFAULT_WEIGHTS["macd_cross"]


def test_load_config_overrides_assets_completely(tmp_path):
    path = tmp_path / "config.json"
    custom_assets = {"XRP": {"name": "Ripple", "symbol": "XRPUSDT", "exchange": "binance_spot", "icon": "X", "decimals": 4}}
    path.write_text(json.dumps({"assets": custom_assets}), encoding="utf-8")

    assets, weights, telegram, paper_trading = load_config(str(path))

    assert assets == custom_assets
    assert weights == DEFAULT_WEIGHTS


def test_load_config_reads_telegram_section(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"telegram": {"bot_token": "abc", "chat_id": "@x"}}), encoding="utf-8")

    assets, weights, telegram, paper_trading = load_config(str(path))

    assert telegram == {"bot_token": "abc", "chat_id": "@x"}


def test_load_config_falls_back_on_invalid_json(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{ isso não é json válido", encoding="utf-8")

    assets, weights, telegram, paper_trading = load_config(str(path))

    assert assets == DEFAULT_ASSETS
    assert weights == DEFAULT_WEIGHTS
    assert telegram == {}
    assert paper_trading == DEFAULT_PAPER_TRADING_CFG


def test_load_config_merges_partial_paper_trading(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"paper_trading": {"enabled": False}}), encoding="utf-8")

    _, _, _, paper_trading = load_config(str(path))

    assert paper_trading["enabled"] is False
    # chaves não mencionadas continuam com o valor padrão
    assert paper_trading["max_holding_hours"] == DEFAULT_PAPER_TRADING_CFG["max_holding_hours"]
