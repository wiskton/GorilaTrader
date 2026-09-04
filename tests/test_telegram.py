"""Testes do TelegramNotifier: fica desativado sem credenciais (sem tentar
rede), e send_sync reporta sucesso/falha reais em vez de assumir sucesso -
regressão do bug em que --test-telegram sempre dizia "enviado" mesmo quando
a chamada à API falhava (ex.: bot não é membro do canal)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from gorilatrader import TelegramNotifier


def test_disabled_without_credentials():
    notifier = TelegramNotifier(bot_token=None, chat_id=None)
    assert notifier.enabled is False


def test_disabled_send_sync_does_not_call_network():
    notifier = TelegramNotifier(bot_token=None, chat_id=None)
    with patch("gorilatrader.requests.post") as mock_post:
        ok, detail = notifier.send_sync("teste")
    assert ok is False
    mock_post.assert_not_called()


def test_send_sync_reports_success_on_http_200():
    notifier = TelegramNotifier(bot_token="TOKEN", chat_id="@canal")
    fake_response = MagicMock(status_code=200)
    with patch("gorilatrader.requests.post", return_value=fake_response) as mock_post:
        ok, detail = notifier.send_sync("teste")
    assert ok is True
    assert detail == "OK"
    mock_post.assert_called_once()


def test_send_sync_reports_failure_detail_on_http_error():
    """Regressão: antes o CLI --test-telegram sempre imprimia sucesso; agora
    send_sync precisa propagar o motivo real da falha (ex.: bot não é membro)."""
    notifier = TelegramNotifier(bot_token="TOKEN", chat_id="@canal")
    fake_response = MagicMock(status_code=403, text='{"description":"Forbidden: bot is not a member of the channel chat"}')
    with patch("gorilatrader.requests.post", return_value=fake_response):
        ok, detail = notifier.send_sync("teste")
    assert ok is False
    assert "403" in detail
    assert "not a member" in detail


def test_send_sync_reports_failure_on_network_exception():
    notifier = TelegramNotifier(bot_token="TOKEN", chat_id="@canal")
    with patch("gorilatrader.requests.post", side_effect=ConnectionError("sem rede")):
        ok, detail = notifier.send_sync("teste")
    assert ok is False
    assert "sem rede" in detail
