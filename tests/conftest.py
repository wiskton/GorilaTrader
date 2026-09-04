"""Fixtures compartilhadas para os testes do GorilaTrader."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from gorilatrader import DEFAULT_WEIGHTS

ZERO_WEIGHTS = {k: 0 for k in DEFAULT_WEIGHTS}


def build_df(
    prefix_n: int,
    tail_steps,
    start: float = 1000.0,
    vol: float = 1000.0,
    seed: int = 0,
    tail_vols=None,
    prefix_noise: float = 0.0008,
) -> pd.DataFrame:
    """Gera um DataFrame OHLCV sintético: `prefix_n` barras de ruído aleatório
    (estabiliza os indicadores de longo prazo) seguidas de `tail_steps`
    (variações percentuais explícitas que desenham o padrão sob teste).

    `tail_vols`, se dado, sobrescreve o volume das últimas `len(tail_vols)`
    barras (usado para testar OBV/volume relativo).
    """
    rng = np.random.RandomState(seed)
    prefix = list(rng.normal(0, prefix_noise, prefix_n))
    pct_changes = prefix + list(tail_steps)

    closes = [start]
    for pct in pct_changes:
        closes.append(closes[-1] * (1 + pct))
    closes = np.array(closes[1:])

    highs = closes * 1.0015
    lows = closes * 0.9985
    opens = np.roll(closes, 1)
    opens[0] = closes[0]

    n = len(closes)
    vols = np.full(n, vol)
    if tail_vols is not None:
        vols[-len(tail_vols):] = tail_vols

    return pd.DataFrame({"open": opens, "high": highs, "low": lows, "close": closes, "vol": vols})


@pytest.fixture
def zero_weights():
    return dict(ZERO_WEIGHTS)
