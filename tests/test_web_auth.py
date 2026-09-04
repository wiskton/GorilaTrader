"""Testes da autenticação simples do dashboard web (opcional, liga sozinha
quando uma senha é configurada) - assinatura/validação do cookie de sessão,
proteção das rotas HTTP e do WebSocket, e o fluxo de login/logout."""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

import webserver


@pytest.fixture
def auth_enabled(monkeypatch):
    """Liga a autenticação (senha "segredo123") só para o teste, sem afetar
    o resto da suíte (que roda com autenticação desativada)."""
    monkeypatch.setattr(webserver, "AUTH_ENABLED", True)
    monkeypatch.setattr(webserver, "_WEB_PASSWORD", "segredo123")
    return "segredo123"


def _request_with_cookie(token):
    cookies = {} if token is None else {webserver.SESSION_COOKIE: token}
    return SimpleNamespace(cookies=cookies)


def test_session_always_valid_when_auth_disabled():
    assert webserver._is_valid_session(None) is True
    assert webserver._is_valid_session("qualquer-coisa-invalida") is True


def test_session_round_trip_when_auth_enabled(auth_enabled):
    token = webserver._make_session_token()
    assert webserver._is_valid_session(token) is True


def test_session_rejects_missing_or_malformed_token(auth_enabled):
    assert webserver._is_valid_session(None) is False
    assert webserver._is_valid_session("") is False
    assert webserver._is_valid_session("sem-ponto-separador") is False


def test_session_rejects_tampered_signature(auth_enabled):
    token = webserver._make_session_token()
    payload, _, _sig = token.rpartition(".")
    tampered = f"{payload}.0000000000000000000000000000000000000000000000000000000000000000"
    assert webserver._is_valid_session(tampered) is False


def test_session_rejects_expired_token(auth_enabled, monkeypatch):
    old_payload = str(int(time.time()) - webserver.SESSION_TTL_SECONDS - 10)
    expired_token = f"{old_payload}.{webserver._sign(old_payload)}"
    assert webserver._is_valid_session(expired_token) is False


def test_require_auth_raises_401_without_valid_session(auth_enabled):
    with pytest.raises(HTTPException) as exc_info:
        webserver.require_auth(_request_with_cookie(None))
    assert exc_info.value.status_code == 401


def test_require_auth_passes_with_valid_session(auth_enabled):
    token = webserver._make_session_token()
    webserver.require_auth(_request_with_cookie(token))  # não deve levantar


def test_index_redirects_to_login_when_auth_enabled_without_session(auth_enabled):
    response = webserver.index(_request_with_cookie(None))
    assert response.status_code in (302, 307)
    assert response.headers["location"] == "/login"


def test_index_serves_dashboard_with_valid_session(auth_enabled):
    token = webserver._make_session_token()
    response = webserver.index(_request_with_cookie(token))
    assert "GorilaTrader" in response  # resposta "crua" (str) fora do ciclo real de request ASGI


def test_index_serves_dashboard_when_auth_disabled():
    response = webserver.index(_request_with_cookie(None))
    assert "GorilaTrader" in response


def test_login_form_shows_page_when_auth_enabled(auth_enabled):
    response = webserver.login_form()
    assert "password" in response


def test_login_form_redirects_home_when_auth_disabled():
    response = webserver.login_form()
    assert response.status_code in (302, 307)
    assert response.headers["location"] == "/"


def test_login_submit_sets_cookie_on_correct_password(auth_enabled):
    response = webserver.login_submit(password="segredo123")
    assert response.status_code == 303
    set_cookie = response.headers.get("set-cookie", "")
    assert webserver.SESSION_COOKIE in set_cookie
    assert "httponly" in set_cookie.lower()


def test_login_submit_rejects_wrong_password(auth_enabled):
    response = webserver.login_submit(password="senha-errada")
    assert response.status_code == 401
    assert webserver.SESSION_COOKIE not in response.headers.get("set-cookie", "")


def test_logout_clears_cookie_and_redirects():
    response = webserver.logout()
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_ws_updates_closes_connection_without_valid_session(auth_enabled):
    fake_ws = SimpleNamespace(cookies={}, close=AsyncMock())
    asyncio.run(webserver.ws_updates(fake_ws, "BTC"))
    fake_ws.close.assert_awaited_once_with(code=4401)
