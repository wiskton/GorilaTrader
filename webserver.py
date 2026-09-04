"""
GorilaTrader Web - dashboard web com gráfico profissional (Lightweight Charts)
sobre o mesmo motor de análise do terminal (gorilatrader.py).

Rode com:
    python3 gorilatrader.py --serve
    python3 gorilatrader.py --serve --port 8080
"""

from __future__ import annotations

import asyncio
import math
import os
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import List, Optional

import numpy as np
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse

from gorilatrader import (
    ASSETS,
    DEFAULT_ASSETS,
    PAPER_TRADING_CFG,
    TELEGRAM_CFG,
    CryptoAnalyzer,
    GorilaTraderTerminal,
    MarketData,
    _detect_display_decimals,
    logger,
    resolve_telegram_credentials,
)

BAR_SECONDS = 3600  # candles de 1h
WS_INTERVAL_SECONDS = 20  # cadência de push do WebSocket, mesma ordem do terminal
ALERT_CHECK_INTERVAL_SECONDS = 60  # cadência do monitor de alertas em segundo plano
WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")

# O dashboard web é só visualização - sem este monitor rodando em segundo
# plano, sinais de COMPRA/VENDA e alertas extremos (RSI/Bollinger) nunca
# disparariam (nem apito, nem Telegram) enquanto só o `--serve` estivesse no
# ar. Reaproveita a mesma lógica de check_and_alert/check_extreme_alerts do
# terminal, então TODO alerta gerado - venha do terminal ou do dashboard web -
# passa pelo mesmo caminho e vai para o Telegram (se configurado). Pela mesma
# razão, o modo papel (paper_trading.py) também roda aqui - do contrário
# nenhuma posição simulada abriria/fecharia enquanto só o dashboard web
# estivesse no ar.
_telegram_token, _telegram_chat_id = resolve_telegram_credentials(TELEGRAM_CFG)
alert_monitor = GorilaTraderTerminal(
    sound_enabled=True,
    telegram_token=_telegram_token,
    telegram_chat_id=_telegram_chat_id,
    paper_trading_enabled=PAPER_TRADING_CFG.get("enabled", True),
    paper_trading_max_holding_hours=PAPER_TRADING_CFG.get("max_holding_hours", 200),
)
_alert_data_map: dict = {}

# Ativos "favoritos" digitados no navegador (sidebar) que não estão em ASSETS
# (config.json) - resolvidos sob demanda (ver resolve_asset_config) e mantidos
# em cache aqui pra não repetir a detecção de casas decimais (que bate na
# exchange) a cada requisição de gráfico/snapshot/WebSocket. Não entram no
# monitor de alertas/modo papel em segundo plano - são só pra visualização.
_extra_assets_cache: dict = {}


def resolve_asset_config(key: str) -> Optional[dict]:
    """Igual ao resolve_assets_from_tickers usado pelo --assets do terminal,
    mas mais rígido: lá um símbolo que não existe cai pra decimais=2 e segue
    em frente (baixo custo, é só uma linha "Erro de conexão" no dashboard);
    aqui devolve None pra virar 404 - sem essa validação, um ticker inventado
    viraria um favorito "fantasma" salvo no navegador que nunca carrega dado."""
    key = key.upper()
    if key in ASSETS:
        return ASSETS[key]
    if key in _extra_assets_cache:
        return _extra_assets_cache[key]
    if key in DEFAULT_ASSETS:
        cfg = DEFAULT_ASSETS[key]
        _extra_assets_cache[key] = cfg
        return cfg

    symbol = f"{key}USDT"
    df = CryptoAnalyzer.fetch_klines(symbol, "binance_spot", interval="1h", limit=2)
    if df is None or df.empty:
        return None

    cfg = {
        "name": key,
        "symbol": symbol,
        "exchange": "binance_spot",
        "icon": "🪙",
        "decimals": _detect_display_decimals(float(df["close"].iloc[-1])),
    }
    _extra_assets_cache[key] = cfg
    return cfg


async def _alert_monitor_loop():
    while True:
        try:
            await asyncio.to_thread(alert_monitor.refresh, _alert_data_map)
        except Exception:
            logger.exception("Falha no loop de monitoramento de alertas do dashboard web")
        await asyncio.sleep(ALERT_CHECK_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_alert_monitor_loop())
    yield
    task.cancel()


app = FastAPI(title="GorilaTrader Web", lifespan=lifespan)


def _clean(value) -> Optional[float]:
    """JSON não aceita NaN - converte para null."""
    if value is None:
        return None
    try:
        if math.isnan(value):
            return None
    except TypeError:
        return None
    return float(value)


def _series_points(times: List[int], values) -> List[dict]:
    out = []
    for t, v in zip(times, values):
        cv = _clean(v)
        if cv is not None:
            out.append({"time": t, "value": cv})
    return out


def build_chart_payload(key: str, config: dict) -> dict:
    """Recalcula os indicadores sobre a série INTEIRA de candles (não só o
    último valor, como em CryptoAnalyzer.analyze_dataframe) para alimentar o
    gráfico. Mesmas fórmulas de gorilatrader.py - mantenha os dois em sincronia
    caso a estratégia mude."""
    df = CryptoAnalyzer.fetch_klines(config["symbol"], config["exchange"], interval="1h", limit=250)
    if df is None or len(df) < 50:
        raise HTTPException(status_code=502, detail=f"Sem dados disponíveis para {key}")

    c, h, l, v, o = df["close"], df["high"], df["low"], df["vol"], df["open"]
    times = (df["open_time"].astype("int64") // 1000).tolist()

    ema9 = c.ewm(span=9, adjust=False).mean()
    ema21 = c.ewm(span=21, adjust=False).mean()
    ema50 = c.ewm(span=50, adjust=False).mean()
    ema200 = c.ewm(span=min(len(c), 200), adjust=False).mean()

    delta = c.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=13, adjust=False).mean()
    avg_loss = loss.ewm(com=13, adjust=False).mean()
    rsi = 100 - (100 / (1 + avg_gain / (avg_loss + 1e-9)))

    ema12 = c.ewm(span=12, adjust=False).mean()
    ema26 = c.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    macd_hist = macd_line - signal_line

    sma20 = c.rolling(20).mean()
    std20 = c.rolling(20).std()
    bb_upper = sma20 + 2 * std20
    bb_lower = sma20 - 2 * std20

    donchian_upper = h.rolling(20).max()
    donchian_lower = l.rolling(20).min()

    obv = (np.sign(c.diff().fillna(0)) * v).cumsum()

    tenkan = (h.rolling(9).max() + l.rolling(9).min()) / 2
    kijun = (h.rolling(26).max() + l.rolling(26).min()) / 2
    senkou_a = (tenkan + kijun) / 2
    senkou_b = (h.rolling(52).max() + l.rolling(52).min()) / 2

    # A Nuvem de Ichimoku é projetada 26 períodos à frente do candle onde foi
    # calculada - por isso desloca-se o eixo do tempo, não os valores.
    cloud_times = times[26:] + [times[-1] + BAR_SECONDS * i for i in range(1, 27)]

    candles = [
        {"time": t, "open": float(op), "high": float(hi), "low": float(lo), "close": float(cl)}
        for t, op, hi, lo, cl in zip(times, o, h, l, c)
    ]
    volume = [
        {"time": t, "value": float(vol), "color": "rgba(0,214,120,0.5)" if cl >= op else "rgba(255,90,90,0.5)"}
        for t, op, cl, vol in zip(times, o, c, v)
    ]

    return {
        "key": key,
        "name": config["name"],
        "decimals": config["decimals"],
        "candles": candles,
        "volume": volume,
        "ema9": _series_points(times, ema9),
        "ema21": _series_points(times, ema21),
        "ema50": _series_points(times, ema50),
        "ema200": _series_points(times, ema200),
        "bb_upper": _series_points(times, bb_upper),
        "bb_lower": _series_points(times, bb_lower),
        "bb_middle": _series_points(times, sma20),
        "donchian_upper": _series_points(times, donchian_upper),
        "donchian_lower": _series_points(times, donchian_lower),
        "ichimoku_tenkan": _series_points(times, tenkan),
        "ichimoku_kijun": _series_points(times, kijun),
        "ichimoku_senkou_a": _series_points(cloud_times, senkou_a.tolist()),
        "ichimoku_senkou_b": _series_points(cloud_times, senkou_b.tolist()),
        "rsi": _series_points(times, rsi),
        "macd_line": _series_points(times, macd_line),
        "macd_signal": _series_points(times, signal_line),
        "macd_hist": _series_points(times, macd_hist),
        "obv": _series_points(times, obv),
    }


@app.get("/api/assets")
def api_assets():
    return {
        key: {"name": cfg["name"], "icon": cfg["icon"], "decimals": cfg["decimals"]}
        for key, cfg in ASSETS.items()
    }


@app.get("/api/paper-trading")
def api_paper_trading():
    """Performance do modo papel (mesmo motor que roda em segundo plano no
    monitor de alertas - ver alert_monitor.paper) para exibição no dashboard
    web, equivalente ao --paper-report do terminal."""
    engine = alert_monitor.paper
    if engine is None:
        return {"enabled": False, "summary": {}, "open": [], "closed": [], "decimals": {}}
    return {
        "enabled": True,
        "summary": engine.summary(),
        "open": [asdict(t) for t in engine.open_trades.values()],
        "closed": [asdict(t) for t in engine.closed_trades[-30:]],
        "decimals": {key: cfg["decimals"] for key, cfg in ASSETS.items()},
    }


@app.get("/api/resolve/{ticker}")
def api_resolve(ticker: str):
    """Resolve um ticker digitado no navegador (favoritos) que pode não estar
    em ASSETS - ver resolve_asset_config."""
    key = ticker.upper()
    cfg = resolve_asset_config(key)
    if cfg is None:
        raise HTTPException(status_code=404, detail=f"Não foi possível resolver {key}")
    return {"key": key, "name": cfg["name"], "icon": cfg["icon"], "decimals": cfg["decimals"]}


@app.get("/api/chart/{key}")
def api_chart(key: str):
    key = key.upper()
    cfg = resolve_asset_config(key)
    if cfg is None:
        raise HTTPException(status_code=404, detail="Ativo desconhecido")
    try:
        return JSONResponse(build_chart_payload(key, cfg))
    except HTTPException:
        raise
    except Exception:
        logger.exception("Falha ao montar payload do gráfico para %s", key)
        raise HTTPException(status_code=500, detail="Erro interno ao calcular indicadores")


def snapshot_payload(item: MarketData) -> dict:
    return {
        "price": item.price,
        "change_1h": item.change_1h,
        "change_24h": item.change_24h,
        "rsi": item.rsi,
        "macd_hist": item.macd_hist,
        "signal": item.signal,
        "score": item.score,
        "stop_loss": item.stop_loss,
        "take_profit_1": item.take_profit_1,
        "take_profit_2": item.take_profit_2,
        "channel_breakout": item.channel_breakout,
        "obv_trend": item.obv_trend,
        "ichimoku_bias": item.ichimoku_bias,
        "bb_zscore": item.bb_zscore,
        "bollinger_status": item.bollinger_status,
        "mtf_bias": item.mtf_bias,
        "reasons": item.reasons,
    }


@app.get("/api/snapshot/{key}")
def api_snapshot(key: str):
    key = key.upper()
    cfg = resolve_asset_config(key)
    if cfg is None:
        raise HTTPException(status_code=404, detail="Ativo desconhecido")
    item = CryptoAnalyzer.analyze_asset(key, cfg)
    if item is None:
        raise HTTPException(status_code=502, detail="Falha ao obter dados (veja gorilatrader.log)")
    return snapshot_payload(item)


@app.websocket("/ws/{key}")
async def ws_updates(websocket: WebSocket, key: str):
    """Empurra gráfico + snapshot a cada WS_INTERVAL_SECONDS, substituindo o
    polling do frontend. As chamadas de rede (fetch_klines/analyze_asset) são
    síncronas e bloqueantes, então rodam em thread separada (asyncio.to_thread)
    para não travar outras conexões no mesmo processo."""
    key = key.upper()
    config = await asyncio.to_thread(resolve_asset_config, key)
    if config is None:
        await websocket.close(code=1008)
        return

    await websocket.accept()

    try:
        while True:
            chart, chart_error = None, None
            try:
                chart = await asyncio.to_thread(build_chart_payload, key, config)
            except HTTPException as exc:
                chart_error = exc.detail
            except Exception:
                logger.exception("Falha ao montar payload do gráfico (WS) para %s", key)
                chart_error = "Erro interno ao calcular indicadores"

            snapshot, snapshot_error = None, None
            try:
                item = await asyncio.to_thread(CryptoAnalyzer.analyze_asset, key, config)
                if item is None:
                    snapshot_error = "Falha ao obter dados (veja gorilatrader.log)"
                else:
                    snapshot = snapshot_payload(item)
            except Exception:
                logger.exception("Falha ao montar snapshot (WS) para %s", key)
                snapshot_error = "Erro interno ao calcular indicadores"

            await websocket.send_json({
                "type": "update",
                "key": key,
                "chart": chart,
                "chart_error": chart_error,
                "snapshot": snapshot,
                "snapshot_error": snapshot_error,
            })

            await asyncio.sleep(WS_INTERVAL_SECONDS)
    except WebSocketDisconnect:
        pass


@app.get("/", response_class=HTMLResponse)
def index():
    path = os.path.join(WEB_DIR, "index.html")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def run_server(host: str = "127.0.0.1", port: int = 8000):
    import uvicorn

    uvicorn.run(app, host=host, port=port, log_level="warning")
