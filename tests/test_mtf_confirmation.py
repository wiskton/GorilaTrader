"""Testes do filtro de confirmação multi-timeframe (viés do candle de 4h
comparado com o viés imediato de 1h). Usa a mesma técnica de isolar o peso
sob teste que tests/test_scoring_matrix.py."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from gorilatrader import ASSETS, CryptoAnalyzer, DEFAULT_WEIGHTS
from tests.conftest import ZERO_WEIGHTS, build_df

LOCAL_BULL = dict(prefix_n=200, tail_steps=[0.006] * 40)  # price > e21
LOCAL_BEAR = dict(prefix_n=200, tail_steps=[-0.006] * 40)  # price < e21

MTF_ALTA = dict(prefix_n=100, tail_steps=[0.006] * 40)   # close > EMA50 do próprio timeframe
MTF_BAIXA = dict(prefix_n=100, tail_steps=[-0.006] * 40)  # close < EMA50 do próprio timeframe


def _weights(value=10):
    w = dict(ZERO_WEIGHTS)
    w["mtf_confirmation"] = value
    return w


def test_aligned_bullish_adds_score_and_confirm_reason():
    df = build_df(**LOCAL_BULL)
    mtf_df = build_df(**MTF_ALTA)
    item = CryptoAnalyzer.analyze_dataframe("TEST", ASSETS["BTC"], df, _weights(10), mtf_df=mtf_df)
    assert item is not None
    assert item.mtf_bias == "ALTA"
    assert item.score == 10
    assert any("confirma o viés de 1h" in r for r in item.reasons)


def test_misaligned_bullish_1h_against_bearish_4h_subtracts_score():
    df = build_df(**LOCAL_BULL)
    mtf_df = build_df(**MTF_BAIXA)
    item = CryptoAnalyzer.analyze_dataframe("TEST", ASSETS["BTC"], df, _weights(10), mtf_df=mtf_df)
    assert item is not None
    assert item.mtf_bias == "BAIXA"
    assert item.score == -10
    assert any("diverge do 1h" in r for r in item.reasons)


def test_aligned_bearish_adds_score():
    df = build_df(**LOCAL_BEAR)
    mtf_df = build_df(**MTF_BAIXA)
    item = CryptoAnalyzer.analyze_dataframe("TEST", ASSETS["BTC"], df, _weights(10), mtf_df=mtf_df)
    assert item is not None
    assert item.score == 10


def test_misaligned_bearish_subtracts_score():
    df = build_df(**LOCAL_BEAR)
    mtf_df = build_df(**MTF_ALTA)
    item = CryptoAnalyzer.analyze_dataframe("TEST", ASSETS["BTC"], df, _weights(10), mtf_df=mtf_df)
    assert item is not None
    assert item.score == -10


def test_missing_mtf_df_contributes_nothing():
    df = build_df(**LOCAL_BULL)
    item = CryptoAnalyzer.analyze_dataframe("TEST", ASSETS["BTC"], df, _weights(10), mtf_df=None)
    assert item is not None
    assert item.mtf_bias is None
    assert item.score == 0
    assert not any("4h" in r for r in item.reasons)


def test_mtf_df_too_short_is_ignored():
    df = build_df(**LOCAL_BULL)
    short_mtf_df = build_df(prefix_n=10, tail_steps=[0.006] * 10)  # < 55 candles
    item = CryptoAnalyzer.analyze_dataframe("TEST", ASSETS["BTC"], df, _weights(10), mtf_df=short_mtf_df)
    assert item is not None
    assert item.mtf_bias is None
    assert item.score == 0


def test_analyze_asset_fetches_and_caches_mtf_klines():
    """analyze_asset deve buscar o 4h automaticamente e reutilizar o cache
    em chamadas subsequentes (não bater na API a cada refresh)."""
    fake_row = [1700000000000, "100", "101", "99", "100.5", "1000",
                1700003600000, "100000", 10, "500", "50000", "0"]

    class FakeResp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return [fake_row] * 250

    CryptoAnalyzer._mtf_cache.clear()
    with patch("gorilatrader.requests.get", return_value=FakeResp()) as mock_get:
        item1 = CryptoAnalyzer.analyze_asset("BTC", ASSETS["BTC"], DEFAULT_WEIGHTS)
        item2 = CryptoAnalyzer.analyze_asset("BTC", ASSETS["BTC"], DEFAULT_WEIGHTS)

    assert item1 is not None and item2 is not None
    assert item1.mtf_bias is not None
    # 1 chamada de 1h + 1 chamada de 4h na primeira vez; a segunda vez só
    # busca o 1h de novo (4h vem do cache) = 3 chamadas no total, não 4.
    assert mock_get.call_count == 3
