"""Testa cada fator da matriz de confluência de CryptoAnalyzer.analyze_dataframe
isoladamente: para cada fator, zera todos os outros pesos e dá o valor 10 só
para o fator sob teste. Se o cenário sintético dispara a condição esperada, o
score final é exatamente +10 ou -10 (nenhum outro fator pode contribuir) - o
que torna o teste imune a ruído incidental de outros fatores disparando junto.
"""

from __future__ import annotations

import pytest

from gorilatrader import ASSETS, CryptoAnalyzer
from tests.conftest import ZERO_WEIGHTS, build_df

# (id, weight_key, kwargs para build_df, sinal esperado (+1/-1), trecho da razão esperada)
CASES = [
    ("trend_full bull", "trend_full",
     dict(prefix_n=200, tail_steps=[0.006] * 40), +1, "Alinhamento clássico de alta"),
    ("trend_full bear", "trend_full",
     dict(prefix_n=200, tail_steps=[-0.006] * 40), -1, "Alinhamento clássico de baixa"),

    ("trend_partial bull", "trend_partial",
     dict(prefix_n=150, tail_steps=[-0.004] * 60 + [0.006] * 15), +1, "Tendência de alta de curto prazo"),
    ("trend_partial bear", "trend_partial",
     dict(prefix_n=150, tail_steps=[0.004] * 60 + [-0.006] * 15), -1, "Tendência de baixa de curto prazo"),

    ("trend_ema200 bull", "trend_ema200",
     dict(prefix_n=200, tail_steps=[0.006] * 40), +1, None),
    ("trend_ema200 bear", "trend_ema200",
     dict(prefix_n=200, tail_steps=[-0.006] * 40), -1, None),

    ("macd_cross bull", "macd_cross",
     dict(prefix_n=200, tail_steps=[-0.006] * 20 + [0.012] * 3), +1, "Cruzamento altista recente no MACD"),
    ("macd_cross bear", "macd_cross",
     dict(prefix_n=200, tail_steps=[0.006] * 20 + [-0.012] * 3), -1, "Cruzamento baixista recente no MACD"),

    ("macd_accel bull", "macd_accel",
     dict(prefix_n=230, tail_steps=[0.004] * 10), +1, "Histograma MACD positivo e acelerando"),
    ("macd_accel bear", "macd_accel",
     dict(prefix_n=230, tail_steps=[-0.004] * 10), -1, "Histograma MACD negativo e acelerando"),

    ("rsi_extreme oversold", "rsi_extreme",
     dict(prefix_n=240, tail_steps=[-0.02] * 15), +1, "RSI extremamente sobrevendido"),
    ("rsi_extreme overbought", "rsi_extreme",
     dict(prefix_n=240, tail_steps=[0.02] * 15), -1, "RSI extremamente sobrecomprado"),

    ("rsi_exit bull", "rsi_exit",
     dict(prefix_n=230, tail_steps=[-0.007] * 3 + [0.02]), +1, "RSI saindo da sobrevenda"),
    ("rsi_exit bear", "rsi_exit",
     dict(prefix_n=230, tail_steps=[0.007] * 3 + [-0.02]), -1, "RSI perdendo força saindo de sobrecompra"),

    ("rsi_trend_zone bull", "rsi_trend_zone",
     dict(prefix_n=199, tail_steps=[0.0018, -0.0012] * 15 + [0.0018]), +1, "RSI na zona ideal de tendência de alta"),
    ("rsi_trend_zone bear", "rsi_trend_zone",
     dict(prefix_n=199, tail_steps=[-0.0018, 0.0012] * 15 + [-0.0018]), -1, "RSI na zona de fraqueza baixista"),

    ("bollinger_band bull (banda inferior)", "bollinger_band",
     dict(prefix_n=240, tail_steps=[0.0] * 14 + [-0.06]), +1, "Banda Inferior de Bollinger"),
    ("bollinger_band bear (banda superior)", "bollinger_band",
     dict(prefix_n=240, tail_steps=[0.0] * 14 + [0.06]), -1, "Banda Superior de Bollinger"),

    ("volume_spike bull", "volume_spike",
     dict(prefix_n=240, tail_steps=[0.0] * 19 + [0.01], tail_vols=[5000]), +1, "Volume expressivo de alta"),
    ("volume_spike bear", "volume_spike",
     dict(prefix_n=240, tail_steps=[0.0] * 19 + [-0.01], tail_vols=[5000]), -1, "Volume expressivo de venda"),

    ("channel_breakout bull", "channel_breakout",
     dict(prefix_n=240, tail_steps=[0.0] * 14 + [0.06]), +1, "nova máxima de 20 períodos"),
    ("channel_breakout bear", "channel_breakout",
     dict(prefix_n=240, tail_steps=[0.0] * 14 + [-0.06]), -1, "nova mínima de 20 períodos"),

    ("obv_confirm bull", "obv_confirm",
     dict(prefix_n=200, tail_steps=[0.006] * 40), +1, "OBV confirma fluxo comprador"),
    ("obv_confirm bear", "obv_confirm",
     dict(prefix_n=200, tail_steps=[-0.006] * 40), -1, "OBV confirma fluxo vendedor"),

    ("obv_divergence bull (acumulação oculta)", "obv_divergence",
     dict(prefix_n=220,
          tail_steps=[-0.002, -0.002, 0.003, -0.002, -0.002, 0.003, -0.002, -0.002, -0.002, -0.001],
          tail_vols=[1000, 1000, 9000, 1000, 1000, 9000, 1000, 1000, 1000, 1000]),
     +1, "Divergência de alta"),
    ("obv_divergence bear (fraqueza oculta)", "obv_divergence",
     dict(prefix_n=220,
          tail_steps=[0.002, 0.002, -0.003, 0.002, 0.002, -0.003, 0.002, 0.002, 0.002, 0.001],
          tail_vols=[1000, 1000, 9000, 1000, 1000, 9000, 1000, 1000, 1000, 1000]),
     -1, "Divergência de baixa"),

    ("ichimoku_cloud bull", "ichimoku_cloud",
     dict(prefix_n=200, tail_steps=[0.006] * 40), +1, "Preço acima da Nuvem de Ichimoku"),
    ("ichimoku_cloud bear", "ichimoku_cloud",
     dict(prefix_n=200, tail_steps=[-0.006] * 40), -1, "Preço abaixo da Nuvem de Ichimoku"),

    ("ichimoku_tk_cross bull", "ichimoku_tk_cross",
     dict(prefix_n=191, tail_steps=[-0.006] * 30 + [0.015] * 9), +1, "Cruzamento altista Tenkan/Kijun"),
    ("ichimoku_tk_cross bear", "ichimoku_tk_cross",
     dict(prefix_n=191, tail_steps=[0.006] * 30 + [-0.015] * 9), -1, "Cruzamento baixista Tenkan/Kijun"),
]


@pytest.mark.parametrize(
    "case_id,weight_key,build_kwargs,sign,reason_substr",
    CASES,
    ids=[c[0] for c in CASES],
)
def test_isolated_factor(case_id, weight_key, build_kwargs, sign, reason_substr):
    df = build_df(**build_kwargs)
    weights = dict(ZERO_WEIGHTS)
    weights[weight_key] = 10

    item = CryptoAnalyzer.analyze_dataframe("TEST", ASSETS["BTC"], df, weights)

    assert item is not None, f"{case_id}: analyze_dataframe retornou None (dados insuficientes)"
    assert item.score == 10 * sign, f"{case_id}: score={item.score} (esperado {10 * sign}) reasons={item.reasons}"
    if reason_substr:
        assert any(reason_substr in r for r in item.reasons), (
            f"{case_id}: trecho {reason_substr!r} não encontrado em {item.reasons}"
        )
