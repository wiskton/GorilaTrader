from gorilatrader import ASSETS, CryptoAnalyzer, DEFAULT_WEIGHTS
from tests.conftest import build_df


def test_extended_trend_keeps_bias_but_blocks_late_entry():
    for step in (0.006, -0.006):
        df = build_df(prefix_n=200, tail_steps=[step] * 40)
        item = CryptoAnalyzer.analyze_dataframe('TEST', ASSETS['BTC'], df, DEFAULT_WEIGHTS)
        assert item.signal == 'NEUTRO'
        assert item.score * step > 0
        assert item.entry_blockers
        assert any('AGUARDAR' in r for r in item.reasons)


def test_filters_do_not_change_raw_score():
    df = build_df(prefix_n=200, tail_steps=[0.006] * 40)
    filtered = CryptoAnalyzer.analyze_dataframe('TEST', ASSETS['BTC'], df, DEFAULT_WEIGHTS)
    raw = CryptoAnalyzer.analyze_dataframe('TEST', ASSETS['BTC'], df, DEFAULT_WEIGHTS, entry_filters=False)
    assert filtered.score == raw.score
    assert 'COMPRA' in raw.signal
    assert filtered.adx >= 20


def test_costs_can_turn_small_profit_into_loss():
    import pandas as pd
    from backtest import Trade, summarize
    trade = Trade('COMPRA', 'COMPRA', 0, 0, 100, 95, 105, 110,
                  fee_bps=10, slippage_bps=5)
    trade.resolve(1, 100.1, 'TP1_TIMEOUT', pd.DataFrame({'open_time': [0, 3600000]}))
    assert trade.pct_return < 0
    assert summarize([trade])['TODOS']['wins'] == 0
    assert summarize([trade])['TODOS']['losses'] == 1


def test_live_feed_excludes_open_candle():
    import pandas as pd
    from unittest.mock import patch
    df = pd.DataFrame({'close_time': [999, 2001], 'close': [100, 200]})
    with patch('gorilatrader.time.time', return_value=2):
        closed = CryptoAnalyzer.closed_candles(df)
    assert closed['close'].tolist() == [100]
    assert len(df) == 2


def test_win_probability_and_assertiveness_in_market_data():
    df = build_df(prefix_n=200, tail_steps=[0.006] * 40)
    item = CryptoAnalyzer.analyze_dataframe('TEST', ASSETS['BTC'], df, DEFAULT_WEIGHTS)
    assert hasattr(item, 'win_probability')
    assert 18.0 <= item.win_probability <= 88.0
    assert hasattr(item, 'assertiveness_label')
    assert item.assertiveness_label in [
        'ALTA ASSERTIVIDADE', 'MÉDIA-ALTA ASSERTIVIDADE', 'MÉDIA (Zona Neutra)', 'BAIXA (Alto Risco / Aguardar)'
    ]
    assert hasattr(item, 'optimal_entry_timing')
    assert item.optimal_entry_timing != '—'
    assert hasattr(item, 'best_entry_zone')
    assert '$' in item.best_entry_zone
    assert 'BRT' in item.best_time_window


def test_webserver_snapshot_includes_entry_intelligence():
    import webserver
    df = build_df(prefix_n=200, tail_steps=[0.006] * 40)
    item = CryptoAnalyzer.analyze_dataframe('TEST', ASSETS['BTC'], df, DEFAULT_WEIGHTS)
    payload = webserver.snapshot_payload(item)
    for field in [
        'win_probability', 'assertiveness_label', 'best_entry_zone',
        'optimal_entry_timing', 'best_time_window', 'current_session', 'last_best_entry'
    ]:
        assert field in payload, f'Campo {field} ausente no payload do webserver'
        assert payload[field] is not None

