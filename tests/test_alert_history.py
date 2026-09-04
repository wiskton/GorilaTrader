"""Testes de persistência do histórico de alertas (alerts_history.json)."""

from __future__ import annotations

from gorilatrader import load_alert_history, save_alert_history


def test_load_missing_file_returns_empty_list(tmp_path):
    path = tmp_path / "alerts_history.json"
    assert load_alert_history(str(path)) == []


def test_save_and_load_round_trip(tmp_path):
    path = tmp_path / "alerts_history.json"
    history = [
        {"time": "10:00:00", "asset": "₿ BTC", "signal": "COMPRA", "price": "$1", "reason": "teste"},
        {"time": "10:05:00", "asset": "⟠ ETH", "signal": "VENDA", "price": "$2", "reason": "teste2"},
    ]
    save_alert_history(history, str(path))
    assert load_alert_history(str(path)) == history


def test_save_trims_to_max_entries(tmp_path):
    path = tmp_path / "alerts_history.json"
    history = [{"time": str(i), "asset": "X", "signal": "COMPRA", "price": "$1", "reason": "r"} for i in range(250)]
    save_alert_history(history, str(path))
    loaded = load_alert_history(str(path))
    assert len(loaded) == 200
    assert loaded[-1]["time"] == "249"  # mantém os mais recentes


def test_load_corrupted_file_returns_empty_list(tmp_path):
    path = tmp_path / "alerts_history.json"
    path.write_text("isso não é json", encoding="utf-8")
    assert load_alert_history(str(path)) == []
