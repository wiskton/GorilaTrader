"""Testes de integração do motor de análise: classificação de sinal,
gerenciamento de risco (SL/TP) e uma regressão específica para o bug em que
a EMA200 na prática usava um span menor (limit de candles insuficiente)."""

from __future__ import annotations

import pandas as pd

from gorilatrader import ASSETS, DEFAULT_WEIGHTS, CryptoAnalyzer
from tests.conftest import build_df


def test_strong_uptrend_classifies_as_buy_signal():
    df = build_df(prefix_n=200, tail_steps=[0.006] * 40)
    item = CryptoAnalyzer.analyze_dataframe("TEST", ASSETS["BTC"], df, DEFAULT_WEIGHTS)
    assert item is not None
    assert "COMPRA" in item.signal
    assert item.score > 0


def test_strong_downtrend_classifies_as_sell_signal():
    df = build_df(prefix_n=200, tail_steps=[-0.006] * 40)
    item = CryptoAnalyzer.analyze_dataframe("TEST", ASSETS["BTC"], df, DEFAULT_WEIGHTS)
    assert item is not None
    assert "VENDA" in item.signal
    assert item.score < 0


def test_score_is_clipped_to_valid_range():
    df = build_df(prefix_n=200, tail_steps=[0.006] * 40)
    # pesos exagerados de propósito para forçar o score bruto além de 100
    huge_weights = {k: 1000 for k in DEFAULT_WEIGHTS}
    item = CryptoAnalyzer.analyze_dataframe("TEST", ASSETS["BTC"], df, huge_weights)
    assert item is not None
    assert -100 <= item.score <= 100


def test_stop_loss_and_take_profit_direction_for_buy():
    df = build_df(prefix_n=200, tail_steps=[0.006] * 40)
    item = CryptoAnalyzer.analyze_dataframe("TEST", ASSETS["BTC"], df, DEFAULT_WEIGHTS)
    assert item is not None and "COMPRA" in item.signal
    assert item.stop_loss < item.price < item.take_profit_1 < item.take_profit_2


def test_stop_loss_and_take_profit_direction_for_sell():
    df = build_df(prefix_n=200, tail_steps=[-0.006] * 40)
    item = CryptoAnalyzer.analyze_dataframe("TEST", ASSETS["BTC"], df, DEFAULT_WEIGHTS)
    assert item is not None and "VENDA" in item.signal
    assert item.take_profit_2 < item.take_profit_1 < item.price < item.stop_loss


def test_neutral_stop_loss_follows_score_bias():
    """Regressão: NEUTRO costumava sempre usar o lado de compra para SL/TP,
    mesmo com viés de score negativo (levemente baixista)."""
    zero_weights = {k: 0 for k in DEFAULT_WEIGHTS}
    zero_weights["trend_ema200"] = 5  # pequeno o bastante para não virar sinal de VENDA

    df_bear_bias = build_df(prefix_n=200, tail_steps=[-0.006] * 40)
    item = CryptoAnalyzer.analyze_dataframe("TEST", ASSETS["BTC"], df_bear_bias, zero_weights)
    assert item is not None
    assert item.signal == "NEUTRO"
    assert item.score < 0
    # viés baixista -> SL acima do preço (lado de venda), não abaixo
    assert item.stop_loss > item.price
    assert item.take_profit_1 < item.price


def test_ema200_uses_full_200_period_span():
    """Regressão: fetch_klines usava limit=120, então EMA200 na prática virava
    uma EMA120. Com limit=250 (produção) o DataFrame tem candles suficientes
    para o span=200 completo - este teste confere que analyze_dataframe usa
    o span correto (min(len, 200)) e não um valor menor arbitrário."""
    df = build_df(prefix_n=200, tail_steps=[0.006] * 40)  # n = 240
    item = CryptoAnalyzer.analyze_dataframe("TEST", ASSETS["BTC"], df, DEFAULT_WEIGHTS)
    assert item is not None

    expected_span = min(len(df), 200)
    assert expected_span == 200, "fixture precisa ter >=200 candles para este teste ser significativo"

    expected_ema200 = float(df["close"].ewm(span=expected_span, adjust=False).mean().iloc[-1])
    assert item.ema200 == expected_ema200

    # Uma EMA de span menor (ex.: 120, o bug original) teria reagido mais
    # rápido à tendência recente e ficaria visivelmente diferente da EMA200 real.
    wrong_span_ema = float(df["close"].ewm(span=120, adjust=False).mean().iloc[-1])
    assert item.ema200 != wrong_span_ema


def test_analyze_dataframe_returns_none_for_insufficient_data():
    df = build_df(prefix_n=10, tail_steps=[0.01] * 5)  # só 15 candles, mínimo é 50
    item = CryptoAnalyzer.analyze_dataframe("TEST", ASSETS["BTC"], df, DEFAULT_WEIGHTS)
    assert item is None
