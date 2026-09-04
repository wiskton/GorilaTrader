#!/usr/bin/env python3
"""
GorilaTrader - Analisador Quantitativo de Cripto (Gráfico 1h)
Monitor em tempo real no terminal com alertas sonoros (apito) para Compra e Venda.
Ativos monitorados: Bitcoin (BTC), Ethereum (ETH), Solana (SOL), Pepe (PEPE) e Hyperliquid (HYPE).
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import struct
import subprocess
import sys
import tempfile
import threading
import time
import wave
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import requests
from rich import box
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# ---------------------------------------------------------------------------
# Logging (falhas de rede/API vão para gorilatrader.log em vez de sumir em silêncio)
# ---------------------------------------------------------------------------

LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gorilatrader.log")
logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("gorilatrader")

# ---------------------------------------------------------------------------
# Configuração dos Ativos Monitorados e dos Pesos da Matriz de Confluência
# Pode ser sobrescrita por config.json (mesma pasta do script) sem editar o
# código - veja config.example.json para o formato aceito.
# ---------------------------------------------------------------------------

DEFAULT_ASSETS = {
    "BTC": {
        "name": "Bitcoin",
        "symbol": "BTCUSDT",
        "exchange": "binance_spot",
        "icon": "₿",
        "decimals": 2,
    },
    "ETH": {
        "name": "Ethereum",
        "symbol": "ETHUSDT",
        "exchange": "binance_spot",
        "icon": "⟠",
        "decimals": 2,
    },
    "SOL": {
        "name": "Solana",
        "symbol": "SOLUSDT",
        "exchange": "binance_spot",
        "icon": "◎",
        "decimals": 2,
    },
    "PEPE": {
        "name": "Pepe",
        "symbol": "PEPEUSDT",
        "exchange": "binance_spot",
        "icon": "🐸",
        "decimals": 8,
    },
    "HYPE": {
        "name": "Hyperliquid",
        "symbol": "HYPEUSDT",
        "exchange": "binance_futures",
        "icon": "⚡",
        "decimals": 3,
    },
}

# Pontuação de cada fator da matriz de confluência (-100 a +100 no total).
# Ajustável via a chave "weights" em config.json sem tocar no código.
DEFAULT_WEIGHTS = {
    "trend_full": 35,       # Preço > EMA9 > EMA21 > EMA50 (ou o inverso)
    "trend_partial": 20,    # Alinhamento parcial de EMA9/EMA21
    "trend_ema200": 10,     # Preço vs. EMA200 (tendência primária)
    "macd_cross": 25,       # Cruzamento fresco do histograma MACD
    "macd_accel": 15,       # Histograma MACD acelerando na mesma direção
    "rsi_extreme": 20,      # RSI < 30 (sobrevendido) ou > 70 (sobrecomprado)
    "rsi_exit": 25,         # RSI saindo de zona de sobrevenda/sobrecompra
    "rsi_trend_zone": 15,   # RSI na zona de tendência (50-65) ou fraqueza (35-48)
    "bollinger_band": 15,   # Preço tocando banda de Bollinger
    "volume_spike": 10,     # Volume >= 1.5x a média de 20 períodos
    "channel_breakout": 15, # Rompimento do canal Donchian(20)
    "obv_confirm": 8,       # OBV confirma a direção do preço
    "obv_divergence": 5,    # Divergência entre OBV e preço
    "ichimoku_cloud": 10,   # Posição do preço em relação à Nuvem de Ichimoku
    "ichimoku_tk_cross": 10,  # Cruzamento Tenkan/Kijun
}

API_URLS = {
    "binance_spot": "https://api.binance.com/api/v3/klines",
    "binance_futures": "https://fapi.binance.com/fapi/v1/klines",
    "bybit_spot": "https://api.bybit.com/v5/market/kline",
}

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


def load_config(path: str = CONFIG_PATH) -> Tuple[dict, dict, dict]:
    """Carrega ativos, pesos e credenciais do Telegram de config.json, mesclando
    com os padrões.

    Se o arquivo não existir ou estiver malformado, usa somente os padrões
    embutidos - o programa nunca deixa de funcionar por causa de config.json.
    """
    assets = dict(DEFAULT_ASSETS)
    weights = dict(DEFAULT_WEIGHTS)
    telegram: dict = {}

    if not os.path.exists(path):
        return assets, weights, telegram

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        logger.error("Falha ao ler %s: %s. Usando configuração padrão.", path, exc)
        return assets, weights, telegram

    if isinstance(data.get("assets"), dict) and data["assets"]:
        assets = data["assets"]
    if isinstance(data.get("weights"), dict):
        weights.update(data["weights"])
    if isinstance(data.get("telegram"), dict):
        telegram = data["telegram"]

    return assets, weights, telegram


def resolve_telegram_credentials(telegram_cfg: dict) -> Tuple[Optional[str], Optional[str]]:
    """Variáveis de ambiente têm prioridade sobre config.json (evita segredo em arquivo versionado)."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN") or telegram_cfg.get("bot_token")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID") or telegram_cfg.get("chat_id")
    return token, chat_id


ASSETS, WEIGHTS, TELEGRAM_CFG = load_config()

# ---------------------------------------------------------------------------
# Persistência do Histórico de Alertas (sobrevive a reinícios do programa)
# ---------------------------------------------------------------------------

ALERTS_HISTORY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "alerts_history.json")
MAX_HISTORY_ENTRIES = 200


def load_alert_history(path: str = ALERTS_HISTORY_PATH) -> List[dict]:
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except Exception as exc:
        logger.warning("Falha ao ler histórico de alertas (%s): %s", path, exc)
    return []


def save_alert_history(history: List[dict], path: str = ALERTS_HISTORY_PATH) -> None:
    try:
        trimmed = history[-MAX_HISTORY_ENTRIES:]
        tmp_path = path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(trimmed, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    except Exception:
        logger.warning("Falha ao salvar histórico de alertas", exc_info=True)


# ---------------------------------------------------------------------------
# Módulo de Áudio / Apito (Sintetizador Nativo WAV + aplay / bell)
# ---------------------------------------------------------------------------

class SoundEngine:
    """Gera apitos melódicos em tempo real sem dependências externas."""

    def __init__(self, enabled: bool = True, use_voice: bool = False):
        self.enabled = enabled
        self.use_voice = use_voice
        self.tmp_dir = tempfile.gettempdir()
        self.has_aplay = self._check_command("aplay")
        self.has_paplay = self._check_command("paplay")
        self.has_spdsay = self._check_command("spd-say")

    @staticmethod
    def _check_command(cmd: str) -> bool:
        try:
            return subprocess.run(["which", cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
        except Exception:
            return False

    def _generate_wav(self, frequencies: List[Tuple[float, float]], filename: str) -> str:
        """Gera um arquivo WAV temporário com uma sequência de frequências e durações."""
        path = os.path.join(self.tmp_dir, filename)
        sample_rate = 44100
        total_samples = []

        for freq, dur in frequencies:
            n_samples = int(sample_rate * dur)
            for i in range(n_samples):
                fade = min(1.0, i / 200, (n_samples - i) / 200)
                val = int(32767.0 * 0.45 * fade * math.sin(2.0 * math.pi * freq * i / sample_rate))
                total_samples.append(val)
            total_samples.extend([0] * int(sample_rate * 0.015))

        with wave.open(path, "w") as wav:
            wav.setparams((1, 2, sample_rate, len(total_samples), "NONE", "not compressed"))
            raw = struct.pack(f"<{len(total_samples)}h", *total_samples)
            wav.writeframes(raw)

        return path

    def _play_wav_async(self, path: str):
        def _runner():
            try:
                if self.has_aplay:
                    subprocess.run(["aplay", "-q", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
                elif self.has_paplay:
                    subprocess.run(["paplay", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
                else:
                    logger.debug("Nenhum player de áudio (aplay/paplay) disponível para tocar o apito.")
            except Exception:
                logger.debug("Falha ao reproduzir apito sonoro", exc_info=True)
            finally:
                try:
                    if os.path.exists(path):
                        os.remove(path)
                except OSError:
                    pass

        threading.Thread(target=_runner, daemon=True).start()

    def play_buy_alert(self, asset_name: str = ""):
        """Apito melódico de COMPRA: acorde ascendente animado (C5 -> E5 -> G5)."""
        if not self.enabled:
            return

        try:
            sys.stdout.write("\a")
            sys.stdout.flush()
        except Exception:
            pass

        notes = [(523.25, 0.10), (659.25, 0.10), (783.99, 0.22)]
        wav_path = self._generate_wav(notes, f"gorilatrader_buy_{int(time.time()*1000)}.wav")
        self._play_wav_async(wav_path)

        if self.use_voice and self.has_spdsay:
            subprocess.Popen(
                ["spd-say", "-l", "pt", "-t", "female3", f"Sinal de Compra no {asset_name}"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

    def play_sell_alert(self, asset_name: str = ""):
        """Apito de VENDA: alerta descendente incisivo (A5 -> F5 -> D5)."""
        if not self.enabled:
            return

        try:
            sys.stdout.write("\a")
            sys.stdout.flush()
        except Exception:
            pass

        notes = [(880.0, 0.11), (698.46, 0.11), (587.33, 0.25)]
        wav_path = self._generate_wav(notes, f"gorilatrader_sell_{int(time.time()*1000)}.wav")
        self._play_wav_async(wav_path)

        if self.use_voice and self.has_spdsay:
            subprocess.Popen(
                ["spd-say", "-l", "pt", "-t", "male1", f"Sinal de Venda no {asset_name}"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )


# ---------------------------------------------------------------------------
# Notificações Telegram (opcional - todos os avisos também são enviados)
# ---------------------------------------------------------------------------

class TelegramNotifier:
    """Envia os alertas do GorilaTrader para um chat do Telegram via Bot API.

    Fica automaticamente desativado se não houver credenciais configuradas
    (variáveis de ambiente TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID, ou a seção
    "telegram" em config.json) - o programa nunca falha por causa disso.
    """

    API_BASE = "https://api.telegram.org"

    def __init__(self, bot_token: Optional[str] = None, chat_id: Optional[str] = None):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.enabled = bool(bot_token and chat_id)
        if not self.enabled:
            logger.info(
                "Telegram não configurado (defina TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID, "
                "ou a seção 'telegram' em config.json) - alertas não serão enviados para o Telegram."
            )

    def send(self, text: str) -> None:
        """Envia a mensagem de forma assíncrona (não bloqueia o loop do dashboard)."""
        if not self.enabled:
            return

        def _runner():
            try:
                url = f"{self.API_BASE}/bot{self.bot_token}/sendMessage"
                r = requests.post(
                    url,
                    json={"chat_id": self.chat_id, "text": text, "parse_mode": "HTML"},
                    timeout=8,
                )
                if r.status_code != 200:
                    logger.warning("Falha ao enviar alerta ao Telegram: HTTP %s - %s", r.status_code, r.text[:200])
            except Exception:
                logger.warning("Erro ao enviar alerta ao Telegram", exc_info=True)

        threading.Thread(target=_runner, daemon=True).start()


# ---------------------------------------------------------------------------
# Motor de Indicadores Técnicos e Análise Quantitativa (1h)
# ---------------------------------------------------------------------------

@dataclass
class MarketData:
    asset_key: str
    name: str
    symbol: str
    price: float
    change_1h: float
    change_24h: float
    rsi: float
    macd_val: float
    macd_sig: float
    macd_hist: float
    prev_macd_hist: float
    ema9: float
    ema21: float
    ema50: float
    ema200: float
    bb_upper: float
    bb_lower: float
    bb_middle: float
    bb_zscore: float  # distância do preço à média em desvios-padrão (Bollinger 20)
    atr: float
    volume_ratio: float
    donchian_upper: float
    donchian_lower: float
    channel_breakout: str  # ALTA, BAIXA, —
    obv_trend: str  # ALTA, BAIXA, NEUTRO
    ichimoku_tenkan: float
    ichimoku_kijun: float
    ichimoku_cloud_top: Optional[float]
    ichimoku_cloud_bottom: Optional[float]
    ichimoku_bias: str  # Acima da Nuvem, Abaixo da Nuvem, Dentro da Nuvem, Indisponível
    signal: str  # FORTE COMPRA, COMPRA, NEUTRO, VENDA, FORTE VENDA
    score: int  # -100 a +100
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    reasons: List[str]
    timestamp: datetime = field(default_factory=datetime.now)


class CryptoAnalyzer:
    """Análise técnica institucional para o gráfico de 1h."""

    @staticmethod
    def _fetch_binance(url_key: str, symbol: str, interval: str, limit: int) -> Optional[pd.DataFrame]:
        url = f"{API_URLS[url_key]}?symbol={symbol}&interval={interval}&limit={limit}"
        r = requests.get(url, timeout=8)
        r.raise_for_status()
        data = r.json()
        df = pd.DataFrame(data, columns=[
            "open_time", "open", "high", "low", "close", "vol",
            "close_time", "qvol", "trades", "tb_base", "tb_quote", "ignore"
        ])
        for col in ["open", "high", "low", "close", "vol"]:
            df[col] = df[col].astype(float)
        return df

    @staticmethod
    def _fetch_bybit(symbol: str, limit: int) -> Optional[pd.DataFrame]:
        url = f"{API_URLS['bybit_spot']}?category=spot&symbol={symbol}&interval=60&limit={limit}"
        r = requests.get(url, timeout=8)
        r.raise_for_status()
        raw_list = r.json().get("result", {}).get("list", [])
        if not raw_list:
            return None
        df = pd.DataFrame(raw_list[::-1], columns=["open_time", "open", "high", "low", "close", "vol", "turnover"])
        for col in ["open", "high", "low", "close", "vol"]:
            df[col] = df[col].astype(float)
        return df

    @classmethod
    def fetch_klines(cls, symbol: str, exchange: str, interval: str = "1h", limit: int = 100) -> Optional[pd.DataFrame]:
        url_key = "binance_futures" if exchange == "binance_futures" else "binance_spot"
        try:
            return cls._fetch_binance(url_key, symbol, interval, limit)
        except Exception as exc:
            logger.warning("Binance (%s) falhou para %s: %s. Tentando fallback Bybit...", url_key, symbol, exc)

        # Fallback Bybit se Binance falhar (mesmo formato de símbolo, ex.: BTCUSDT)
        try:
            df = cls._fetch_bybit(symbol, limit)
            if df is None:
                logger.error("Bybit não retornou candles para %s. Sem dados disponíveis.", symbol)
            return df
        except Exception as exc:
            logger.error("Bybit também falhou para %s: %s. Sem dados disponíveis.", symbol, exc)

        return None

    @classmethod
    def analyze_asset(cls, key: str, config: dict, weights: Optional[dict] = None) -> Optional[MarketData]:
        df = cls.fetch_klines(config["symbol"], config["exchange"], interval="1h", limit=250)
        if df is None or len(df) < 50:
            logger.warning("Dados insuficientes para %s (%s candles)", key, 0 if df is None else len(df))
            return None
        return cls.analyze_dataframe(key, config, df, weights)

    @classmethod
    def analyze_dataframe(
        cls, key: str, config: dict, df: pd.DataFrame, weights: Optional[dict] = None
    ) -> Optional[MarketData]:
        """Calcula os indicadores e a matriz de confluência a partir de um
        DataFrame de candles já carregado (separado de analyze_asset para
        permitir testar a lógica de decisão sem depender de rede)."""
        if df is None or len(df) < 50:
            return None
        w = weights or WEIGHTS

        c = df["close"]
        h = df["high"]
        l = df["low"]
        v = df["vol"]

        # 1. EMAs (Tendência e Suportes Dinâmicos)
        ema9 = c.ewm(span=9, adjust=False).mean()
        ema21 = c.ewm(span=21, adjust=False).mean()
        ema50 = c.ewm(span=50, adjust=False).mean()
        ema200 = c.ewm(span=min(len(c), 200), adjust=False).mean()

        # 2. RSI (14 períodos - Suavização Wilder)
        delta = c.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(com=13, adjust=False).mean()
        avg_loss = loss.ewm(com=13, adjust=False).mean()
        rs = avg_gain / (avg_loss + 1e-9)
        rsi_series = 100 - (100 / (1 + rs))

        # 3. MACD (12, 26, 9)
        ema12 = c.ewm(span=12, adjust=False).mean()
        ema26 = c.ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        macd_hist = macd_line - signal_line

        # 4. Bollinger Bands (20, 2)
        sma20 = c.rolling(20).mean()
        std20 = c.rolling(20).std()
        bb_upper = sma20 + 2 * std20
        bb_lower = sma20 - 2 * std20

        # 5. ATR (Average True Range - 14)
        tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
        atr_series = tr.ewm(com=13, adjust=False).mean()

        # 6. Volume Relativo
        vol_ma20 = v.rolling(20).mean()
        current_vol_ratio = float(v.iloc[-1] / (vol_ma20.iloc[-1] + 1e-9))

        # 7. On-Balance Volume (OBV) - confirma ou denuncia divergência entre preço e fluxo
        obv = (np.sign(c.diff().fillna(0)) * v).cumsum()

        # 8. Canal de Donchian (20) - rompimento de máxima/mínima recente
        donchian_upper = h.rolling(20).max()
        donchian_lower = l.rolling(20).min()

        # 9. Ichimoku Kinko Hyo (Tenkan 9, Kijun 26, Senkou Span A/B 52, deslocado 26)
        tenkan = (h.rolling(9).max() + l.rolling(9).min()) / 2
        kijun = (h.rolling(26).max() + l.rolling(26).min()) / 2
        senkou_a = (tenkan + kijun) / 2
        senkou_b = (h.rolling(52).max() + l.rolling(52).min()) / 2

        # Valores atuais e anteriores
        price = float(c.iloc[-1])
        open_1h = float(df["open"].iloc[-1])
        change_1h = ((price - open_1h) / open_1h) * 100.0

        idx_24h = max(0, len(c) - 25)
        price_24h_ago = float(c.iloc[idx_24h])
        change_24h = ((price - price_24h_ago) / price_24h_ago) * 100.0

        rsi = float(rsi_series.iloc[-1])
        prev_rsi = float(rsi_series.iloc[-2])

        m_line = float(macd_line.iloc[-1])
        s_line = float(signal_line.iloc[-1])
        m_hist = float(macd_hist.iloc[-1])
        prev_m_hist = float(macd_hist.iloc[-2])

        e9 = float(ema9.iloc[-1])
        e21 = float(ema21.iloc[-1])
        e50 = float(ema50.iloc[-1])
        e200 = float(ema200.iloc[-1])

        b_up = float(bb_upper.iloc[-1])
        b_low = float(bb_lower.iloc[-1])
        b_mid = float(sma20.iloc[-1])
        b_std = float(std20.iloc[-1])
        bb_zscore = (price - b_mid) / (b_std + 1e-9)

        atr = float(atr_series.iloc[-1])

        # Rompimento de canal: compara o preço com a máxima/mínima dos 20 períodos
        # ANTERIORES (exclui a barra atual) para detectar um rompimento fresco.
        d_upper_now = float(donchian_upper.iloc[-1])
        d_lower_now = float(donchian_lower.iloc[-1])
        d_upper_prev = float(donchian_upper.iloc[-2])
        d_lower_prev = float(donchian_lower.iloc[-2])
        channel_breakout_up = price > d_upper_prev
        channel_breakout_down = price < d_lower_prev
        channel_breakout = "ALTA" if channel_breakout_up else ("BAIXA" if channel_breakout_down else "—")

        # OBV: compara o fluxo de volume acumulado com o preço 10 períodos atrás
        # para confirmar tendência ou flagrar divergência oculta.
        obv_up = bool(obv.iloc[-1] > obv.iloc[-10])
        price_up = price > float(c.iloc[-10])
        if obv_up and price_up:
            obv_trend = "ALTA"
        elif not obv_up and not price_up:
            obv_trend = "BAIXA"
        else:
            obv_trend = "NEUTRO"

        # Ichimoku: exige histórico suficiente para o Senkou Span B (52) deslocado 26
        # períodos à frente - a "nuvem" válida agora é a projeção feita 26 barras atrás.
        ich_tenkan = float(tenkan.iloc[-1])
        ich_kijun = float(kijun.iloc[-1])
        cloud_idx = len(c) - 1 - 26
        ichimoku_ready = cloud_idx >= 51  # senkou_b precisa de 52 candles válidos até cloud_idx
        if ichimoku_ready:
            cloud_a = float(senkou_a.iloc[cloud_idx])
            cloud_b = float(senkou_b.iloc[cloud_idx])
            cloud_top = max(cloud_a, cloud_b)
            cloud_bottom = min(cloud_a, cloud_b)
            if price > cloud_top:
                ichimoku_bias = "Acima da Nuvem"
            elif price < cloud_bottom:
                ichimoku_bias = "Abaixo da Nuvem"
            else:
                ichimoku_bias = "Dentro da Nuvem"
        else:
            cloud_top = None
            cloud_bottom = None
            ichimoku_bias = "Indisponível"

        fresh_tk_bull = float(tenkan.iloc[-2]) <= float(kijun.iloc[-2]) and ich_tenkan > ich_kijun
        fresh_tk_bear = float(tenkan.iloc[-2]) >= float(kijun.iloc[-2]) and ich_tenkan < ich_kijun

        # -------------------------------------------------------------------
        # Matriz de Decisão e Confluência Quantitativa (-100 a +100)
        # -------------------------------------------------------------------
        score = 0
        reasons = []

        # --- A) TENDÊNCIA E ALINHAMENTO DE MÉDIAS ---
        if price > e9 > e21 > e50:
            score += w["trend_full"]
            reasons.append("Alinhamento clássico de alta (Preço > EMA9 > EMA21 > EMA50)")
        elif price > e21 and e9 > e21:
            score += w["trend_partial"]
            reasons.append("Tendência de alta de curto prazo (EMA9 > EMA21)")
        elif price < e9 < e21 < e50:
            score -= w["trend_full"]
            reasons.append("Alinhamento clássico de baixa (Preço < EMA9 < EMA21 < EMA50)")
        elif price < e21 and e9 < e21:
            score -= w["trend_partial"]
            reasons.append("Tendência de baixa de curto prazo (EMA9 < EMA21)")

        if price > e200:
            score += w["trend_ema200"]
        else:
            score -= w["trend_ema200"]

        # --- B) MOMENTUM MACD ---
        fresh_bull_cross = (prev_m_hist <= 0 and m_hist > 0)
        fresh_bear_cross = (prev_m_hist >= 0 and m_hist < 0)

        if fresh_bull_cross:
            score += w["macd_cross"]
            reasons.append("Cruzamento altista recente no MACD (Gatilho de Compra)")
        elif m_hist > 0 and m_hist > prev_m_hist:
            score += w["macd_accel"]
            reasons.append("Histograma MACD positivo e acelerando")
        elif fresh_bear_cross:
            score -= w["macd_cross"]
            reasons.append("Cruzamento baixista recente no MACD (Gatilho de Venda)")
        elif m_hist < 0 and m_hist < prev_m_hist:
            score -= w["macd_accel"]
            reasons.append("Histograma MACD negativo e acelerando para baixo")

        # --- C) FORÇA RELATIVA - RSI ---
        if rsi < 30:
            score += w["rsi_extreme"]
            reasons.append(f"RSI extremamente sobrevendido ({rsi:.1f}) - potencial repique")
        elif prev_rsi < 35 and rsi >= 35:
            score += w["rsi_exit"]
            reasons.append(f"RSI saindo da sobrevenda rompendo 35 ({rsi:.1f})")
        elif 50 <= rsi <= 65 and rsi > prev_rsi:
            score += w["rsi_trend_zone"]
            reasons.append(f"RSI na zona ideal de tendência de alta ({rsi:.1f})")
        elif rsi > 70:
            score -= w["rsi_extreme"]
            reasons.append(f"RSI extremamente sobrecomprado ({rsi:.1f}) - risco de correção")
        elif prev_rsi > 65 and rsi <= 65:
            score -= w["rsi_exit"]
            reasons.append(f"RSI perdendo força saindo de sobrecompra ({rsi:.1f})")
        elif 35 <= rsi <= 48 and rsi < prev_rsi:
            score -= w["rsi_trend_zone"]
            reasons.append(f"RSI na zona de fraqueza baixista ({rsi:.1f})")

        # --- D) VOLATILIDADE E BANDAS DE BOLLINGER ---
        if price <= b_low * 1.005:
            score += w["bollinger_band"]
            reasons.append("Preço tocando a Banda Inferior de Bollinger (suporte)")
        elif price >= b_up * 0.995:
            score -= w["bollinger_band"]
            reasons.append("Preço tocando a Banda Superior de Bollinger (resistência)")

        # --- E) CONFIRMAÇÃO DE VOLUME - PICO RELATIVO ---
        if current_vol_ratio >= 1.5:
            if change_1h > 0:
                score += w["volume_spike"]
                reasons.append(f"Volume expressivo de alta ({current_vol_ratio:.1f}x da média)")
            else:
                score -= w["volume_spike"]
                reasons.append(f"Volume expressivo de venda ({current_vol_ratio:.1f}x da média)")

        # --- F) ROMPIMENTO DE CANAL - DONCHIAN 20 ---
        if channel_breakout_up:
            score += w["channel_breakout"]
            reasons.append("Rompimento do canal Donchian(20) - nova máxima de 20 períodos")
        elif channel_breakout_down:
            score -= w["channel_breakout"]
            reasons.append("Rompimento do canal Donchian(20) - nova mínima de 20 períodos")

        # --- G) FLUXO DE VOLUME - OBV (detecta divergência oculta) ---
        if obv_trend == "ALTA":
            score += w["obv_confirm"]
            reasons.append("OBV confirma fluxo comprador (acumulação)")
        elif obv_trend == "BAIXA":
            score -= w["obv_confirm"]
            reasons.append("OBV confirma fluxo vendedor (distribuição)")
        elif not obv_up and price_up:
            score -= w["obv_divergence"]
            reasons.append("Divergência de baixa: preço sobe mas OBV cai (fraqueza oculta)")
        elif obv_up and not price_up:
            score += w["obv_divergence"]
            reasons.append("Divergência de alta: preço cai mas OBV sobe (acumulação oculta)")

        # --- H) ICHIMOKU KINKO HYO ---
        if ichimoku_ready:
            if price > cloud_top:
                score += w["ichimoku_cloud"]
                reasons.append("Preço acima da Nuvem de Ichimoku (viés estrutural de alta)")
            elif price < cloud_bottom:
                score -= w["ichimoku_cloud"]
                reasons.append("Preço abaixo da Nuvem de Ichimoku (viés estrutural de baixa)")
            else:
                reasons.append("Preço dentro da Nuvem de Ichimoku (estrutura indefinida)")

            if fresh_tk_bull:
                score += w["ichimoku_tk_cross"]
                reasons.append("Cruzamento altista Tenkan/Kijun (Ichimoku)")
            elif fresh_tk_bear:
                score -= w["ichimoku_tk_cross"]
                reasons.append("Cruzamento baixista Tenkan/Kijun (Ichimoku)")

        # Normaliza pontuação
        score = max(-100, min(100, score))

        # Classificação do Sinal
        if score >= 50:
            signal = "FORTE COMPRA"
        elif score >= 25:
            signal = "COMPRA"
        elif score <= -50:
            signal = "FORTE VENDA"
        elif score <= -25:
            signal = "VENDA"
        else:
            signal = "NEUTRO"

        # Gerenciamento de Risco (Stop Loss & Take Profits com ATR)
        safe_atr = max(atr, price * 0.005)
        if "COMPRA" in signal:
            sl = price - (1.5 * safe_atr)
            tp1 = price + (2.0 * safe_atr)
            tp2 = price + (3.5 * safe_atr)
        elif "VENDA" in signal:
            sl = price + (1.5 * safe_atr)
            tp1 = price - (2.0 * safe_atr)
            tp2 = price - (3.5 * safe_atr)
        elif score >= 0:
            # NEUTRO com viés levemente altista: níveis apenas como referência
            sl = price - (1.5 * safe_atr)
            tp1 = price + (2.0 * safe_atr)
            tp2 = price + (3.5 * safe_atr)
        else:
            # NEUTRO com viés levemente baixista: níveis apenas como referência
            sl = price + (1.5 * safe_atr)
            tp1 = price - (2.0 * safe_atr)
            tp2 = price - (3.5 * safe_atr)

        return MarketData(
            asset_key=key,
            name=config["name"],
            symbol=config["symbol"],
            price=price,
            change_1h=change_1h,
            change_24h=change_24h,
            rsi=rsi,
            macd_val=m_line,
            macd_sig=s_line,
            macd_hist=m_hist,
            prev_macd_hist=prev_m_hist,
            ema9=e9,
            ema21=e21,
            ema50=e50,
            ema200=e200,
            bb_upper=b_up,
            bb_lower=b_low,
            bb_middle=b_mid,
            bb_zscore=bb_zscore,
            atr=atr,
            volume_ratio=current_vol_ratio,
            donchian_upper=d_upper_now,
            donchian_lower=d_lower_now,
            channel_breakout=channel_breakout,
            obv_trend=obv_trend,
            ichimoku_tenkan=ich_tenkan,
            ichimoku_kijun=ich_kijun,
            ichimoku_cloud_top=cloud_top,
            ichimoku_cloud_bottom=cloud_bottom,
            ichimoku_bias=ichimoku_bias,
            signal=signal,
            score=score,
            stop_loss=sl,
            take_profit_1=tp1,
            take_profit_2=tp2,
            reasons=reasons,
        )


# ---------------------------------------------------------------------------
# Interface Terminal Interativa com Rich
# ---------------------------------------------------------------------------

class GorilaTraderTerminal:
    """Gerenciador do loop em tempo real e visualização no terminal."""

    def __init__(
        self,
        interval: int = 30,
        sound_enabled: bool = True,
        use_voice: bool = False,
        telegram_token: Optional[str] = None,
        telegram_chat_id: Optional[str] = None,
    ):
        self.interval = interval
        self.sound = SoundEngine(enabled=sound_enabled, use_voice=use_voice)
        self.telegram = TelegramNotifier(telegram_token, telegram_chat_id)
        self.console = Console()
        self.history_alerts: List[dict] = load_alert_history()
        self.last_signals: Dict[str, str] = {}
        self.last_rsi_extreme: Dict[str, Optional[str]] = {}
        self.last_bb_extreme: Dict[str, Optional[str]] = {}
        self.stale: Dict[str, bool] = {}
        self.iteration = 0

    def fetch_all(self) -> Dict[str, Optional[MarketData]]:
        """Busca e analisa todos os ativos em paralelo (evita ~5x latência sequencial)."""
        results: Dict[str, Optional[MarketData]] = {}
        with ThreadPoolExecutor(max_workers=len(ASSETS)) as executor:
            futures = {
                executor.submit(CryptoAnalyzer.analyze_asset, key, config): key
                for key, config in ASSETS.items()
            }
            for future in as_completed(futures):
                key = futures[future]
                try:
                    results[key] = future.result()
                except Exception:
                    logger.exception("Erro inesperado ao analisar %s", key)
                    results[key] = None
        return results

    def refresh(self, data_map: Dict[str, MarketData]) -> Dict[str, MarketData]:
        """Atualiza data_map com os resultados mais recentes e dispara alertas."""
        for key, res in self.fetch_all().items():
            if res:
                data_map[key] = res
                self.stale[key] = False
                self.check_and_alert(res)
                self.check_extreme_alerts(res)
            else:
                self.stale[key] = True
        return data_map

    def format_price(self, price: float, decimals: int) -> str:
        if decimals >= 6:
            return f"${price:.8f}"
        elif decimals == 3:
            return f"${price:.3f}"
        else:
            return f"${price:,.2f}"

    def build_dashboard(self, data_map: Dict[str, MarketData], countdown: int) -> Layout:
        layout = Layout()
        layout.split(
            Layout(name="header", size=3),
            Layout(name="main", size=15),
            Layout(name="details", size=9),
            Layout(name="footer", size=3),
        )

        sound_status = "[bold green]🔊 APITO ATIVO[/bold green]" if self.sound.enabled else "[yellow]🔇 MUDO[/yellow]"
        telegram_status = "[bold green]📨 TELEGRAM ATIVO[/bold green]" if self.telegram.enabled else "[dim]📨 Telegram off[/dim]"
        time_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        header_text = Text.from_markup(
            f" [bold cyan]GORILATRADER[/bold cyan] · Análise 1h Cripto em Tempo Real · {sound_status} · {telegram_status} · 🕒 {time_str}"
        )
        layout["header"].update(Panel(header_text, style="cyan", box=box.ROUNDED))

        table = Table(box=box.ROUNDED, expand=True, header_style="bold bright_white on grey23")
        table.add_column("Ativo", justify="left", style="bold", width=16)
        table.add_column("Preço Atual", justify="right", width=15)
        table.add_column("1h %", justify="right", width=9)
        table.add_column("24h %", justify="right", width=9)
        table.add_column("RSI (14)", justify="right", width=10)
        table.add_column("MACD Hist", justify="right", width=11)
        table.add_column("Tendência", justify="center", width=14)
        table.add_column("Ichimoku", justify="center", width=17)
        table.add_column("Canal(20)", justify="center", width=12)
        table.add_column("SINAL 1H", justify="center", width=17)
        table.add_column("Score", justify="center", width=8)
        table.add_column("Stop Loss", justify="right", width=14)
        table.add_column("Take Profit 1", justify="right", width=14)
        table.add_column("Take Profit 2", justify="right", width=14)

        for key, config in ASSETS.items():
            item = data_map.get(key)
            icon = config["icon"]
            decimals = config["decimals"]

            if not item:
                status = "[red]❌ Erro de conexão[/red]" if self.stale.get(key) else "[dim]Carregando...[/dim]"
                table.add_row(f"{icon} {key}", status, "—", "—", "—", "—", "—", "—", "—", "—", "—", "—", "—", "—")
                continue

            p_str = self.format_price(item.price, decimals)
            sl_str = self.format_price(item.stop_loss, decimals)
            tp1_str = self.format_price(item.take_profit_1, decimals)
            tp2_str = self.format_price(item.take_profit_2, decimals)

            c1h_color = "green" if item.change_1h >= 0 else "red"
            c1h_str = f"[{c1h_color}]{item.change_1h:+.2f}%[/{c1h_color}]"

            c24_color = "green" if item.change_24h >= 0 else "red"
            c24_str = f"[{c24_color}]{item.change_24h:+.2f}%[/{c24_color}]"

            if item.rsi >= 70:
                rsi_str = f"[bold red]{item.rsi:.1f} ⚠️[/bold red]"
            elif item.rsi <= 30:
                rsi_str = f"[bold green]{item.rsi:.1f} 🟢[/bold green]"
            elif item.rsi >= 50:
                rsi_str = f"[cyan]{item.rsi:.1f}[/cyan]"
            else:
                rsi_str = f"[yellow]{item.rsi:.1f}[/yellow]"

            if item.price > item.ema9 > item.ema21 > item.ema50:
                trend_str = "[bold green]▲ Alta Forte[/bold green]"
            elif item.price > item.ema21:
                trend_str = "[green]▲ Alta[/green]"
            elif item.price < item.ema9 < item.ema21 < item.ema50:
                trend_str = "[bold red]▼ Baixa Forte[/bold red]"
            elif item.price < item.ema21:
                trend_str = "[red]▼ Baixa[/red]"
            else:
                trend_str = "[yellow]◆ Lateral[/yellow]"

            if item.macd_hist > 0:
                macd_str = f"[green]+{item.macd_hist:.4f}[/green]"
            elif item.macd_hist < 0:
                macd_str = f"[red]{item.macd_hist:.4f}[/red]"
            else:
                macd_str = "0.0000"

            if item.ichimoku_bias == "Acima da Nuvem":
                ichimoku_str = "[bold green]▲ Acima Nuvem[/bold green]"
            elif item.ichimoku_bias == "Abaixo da Nuvem":
                ichimoku_str = "[bold red]▼ Abaixo Nuvem[/bold red]"
            elif item.ichimoku_bias == "Dentro da Nuvem":
                ichimoku_str = "[yellow]◆ Na Nuvem[/yellow]"
            else:
                ichimoku_str = "[dim]Indisponível[/dim]"

            if item.channel_breakout == "ALTA":
                channel_str = "[bold green]⤴ Rompeu[/bold green]"
            elif item.channel_breakout == "BAIXA":
                channel_str = "[bold red]⤵ Rompeu[/bold red]"
            else:
                channel_str = "[dim]— dentro[/dim]"

            if item.signal == "FORTE COMPRA":
                sig_str = "[bold white on dark_green] 🟢 FORTE COMPRA [/bold white on dark_green]"
            elif item.signal == "COMPRA":
                sig_str = "[bold green]🟢 COMPRA[/bold green]"
            elif item.signal == "FORTE VENDA":
                sig_str = "[bold white on dark_red] 🔴 FORTE VENDA [/bold white on dark_red]"
            elif item.signal == "VENDA":
                sig_str = "[bold red]🔴 VENDA[/bold red]"
            else:
                sig_str = "[grey62]⚪ AGUARDAR[/grey62]"

            if item.score > 0:
                score_str = f"[green]+{item.score}[/green]"
            elif item.score < 0:
                score_str = f"[red]{item.score}[/red]"
            else:
                score_str = "0"

            asset_label = f"{icon} [bold]{key}[/bold] [dim]({config['name']})[/dim]"
            if self.stale.get(key):
                asset_label += " [yellow]⚠[/yellow]"

            table.add_row(
                asset_label,
                p_str,
                c1h_str,
                c24_str,
                rsi_str,
                macd_str,
                trend_str,
                ichimoku_str,
                channel_str,
                sig_str,
                score_str,
                f"[red]{sl_str}[/red]",
                f"[green]{tp1_str}[/green]",
                f"[bold green]{tp2_str}[/bold green]",
            )

        layout["main"].update(Panel(table, title="[bold]📊 Monitor Gráfico de 1 Hora (Corte Técnico)[/bold]", border_style="blue"))

        alert_table = Table(box=box.SIMPLE, expand=True)
        alert_table.add_column("Horário", width=12, style="dim")
        alert_table.add_column("Ativo", width=10, style="bold")
        alert_table.add_column("Sinal Emitido", width=18)
        alert_table.add_column("Preço Entrada", width=16)
        alert_table.add_column("Justificativa Técnica (Confluências)")

        if not self.history_alerts:
            alert_table.add_row("—", "—", "[dim]Nenhum alarme disparado nesta sessão ainda. Aguardando gatilhos...[/dim]", "—", "—")
        else:
            for al in reversed(self.history_alerts[-4:]):
                sig_fmt = f"[bold green]{al['signal']}[/bold green]" if "COMPRA" in al["signal"] else f"[bold red]{al['signal']}[/bold red]"
                alert_table.add_row(
                    al["time"],
                    al["asset"],
                    sig_fmt,
                    al["price"],
                    al["reason"],
                )

        layout["details"].update(
            Panel(alert_table, title="[bold]🔔 Histórico de Apitos e Sinais Disparados[/bold]", border_style="magenta")
        )

        footer_text = Text.from_markup(
            f" [dim]Próxima atualização em:[/dim] [bold yellow]{countdown:02d}s[/bold yellow] · "
            f"[dim]Pressione [bold white]Ctrl+C[/bold white] para sair · Alertas sonoros habilitados automaticamente na transição de sinal.[/dim]"
        )
        layout["footer"].update(Panel(footer_text, style="grey50", box=box.ROUNDED))

        return layout

    def _record_alert(self, item: MarketData, label: str, bullish: bool, detail: str):
        """Ponto único de disparo de qualquer aviso: apito, histórico (persistido) e Telegram."""
        key = item.asset_key
        p_str = self.format_price(item.price, ASSETS[key]["decimals"])

        if bullish:
            self.sound.play_buy_alert(item.name)
        else:
            self.sound.play_sell_alert(item.name)

        self.history_alerts.append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "asset": f"{ASSETS[key]['icon']} {key}",
            "signal": label,
            "price": p_str,
            "reason": detail,
        })
        self.history_alerts = self.history_alerts[-MAX_HISTORY_ENTRIES:]
        save_alert_history(self.history_alerts)

        emoji = "🟢" if bullish else "🔴"
        text = (
            f"{emoji} <b>GorilaTrader</b> · {ASSETS[key]['icon']} <b>{key}</b>\n"
            f"{label}\n"
            f"Preço: {p_str}\n"
            f"{detail}\n"
            f"🕒 {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"
        )
        self.telegram.send(text)

    def check_and_alert(self, item: MarketData):
        """Verifica se houve mudança de sinal (COMPRA/VENDA) e dispara o aviso."""
        key = item.asset_key
        last_sig = self.last_signals.get(key)
        current_sig = item.signal

        if current_sig in ("COMPRA", "FORTE COMPRA") and last_sig not in ("COMPRA", "FORTE COMPRA"):
            reason_summary = " · ".join(item.reasons[:2]) if item.reasons else "Confluência altista confirmada"
            self._record_alert(item, current_sig, bullish=True, detail=reason_summary)
        elif current_sig in ("VENDA", "FORTE VENDA") and last_sig not in ("VENDA", "FORTE VENDA"):
            reason_summary = " · ".join(item.reasons[:2]) if item.reasons else "Confluência baixista confirmada"
            self._record_alert(item, current_sig, bullish=False, detail=reason_summary)

        self.last_signals[key] = current_sig

    def check_extreme_alerts(self, item: MarketData):
        """Alertas independentes do score: RSI estourado (>80/<20) e rompimento
        muito forte das Bandas de Bollinger (>= 2.5 desvios-padrão da média)."""
        key = item.asset_key

        if item.rsi >= 80:
            rsi_state = "OVERBOUGHT"
        elif item.rsi <= 20:
            rsi_state = "OVERSOLD"
        else:
            rsi_state = None

        if rsi_state and self.last_rsi_extreme.get(key) != rsi_state:
            if rsi_state == "OVERBOUGHT":
                self._record_alert(
                    item, "⚠ RSI ESTOURADO (SOBRECOMPRA)", bullish=False,
                    detail=f"RSI({item.rsi:.1f}) acima de 80 - risco elevado de correção",
                )
            else:
                self._record_alert(
                    item, "⚠ RSI ESTOURADO (SOBREVENDA)", bullish=True,
                    detail=f"RSI({item.rsi:.1f}) abaixo de 20 - potencial repique forte",
                )
        self.last_rsi_extreme[key] = rsi_state

        if item.bb_zscore >= 2.5:
            bb_state = "UPPER"
        elif item.bb_zscore <= -2.5:
            bb_state = "LOWER"
        else:
            bb_state = None

        if bb_state and self.last_bb_extreme.get(key) != bb_state:
            if bb_state == "UPPER":
                self._record_alert(
                    item, "⚠ ROMPIMENTO FORTE - BANDA SUPERIOR DE BOLLINGER", bullish=False,
                    detail=f"Preço a {item.bb_zscore:+.1f}σ da média (Bollinger 20) - exaustão de alta",
                )
            else:
                self._record_alert(
                    item, "⚠ ROMPIMENTO FORTE - BANDA INFERIOR DE BOLLINGER", bullish=True,
                    detail=f"Preço a {item.bb_zscore:+.1f}σ da média (Bollinger 20) - exaustão de baixa",
                )
        self.last_bb_extreme[key] = bb_state

    def run_once(self):
        """Executa uma análise detalhada imediata e imprime no terminal."""
        self.console.print("\n[bold cyan]═══════════════════════════════════════════════════════════════════════════════[/bold cyan]")
        self.console.print(" [bold white on blue] GORILATRADER · RELATÓRIO DO GRÁFICO DE 1 HORA [/bold white on blue]")
        self.console.print(f" [dim]Data/Hora: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')} · Timeframe: 1H[/dim]")
        self.console.print("[bold cyan]═══════════════════════════════════════════════════════════════════════════════[/bold cyan]\n")

        results = self.fetch_all()
        for key, config in ASSETS.items():
            item = results.get(key)
            if not item:
                self.console.print(f"[red]❌ Erro ao obter dados para {key} (veja gorilatrader.log)[/red]")
                continue

            dec = config["decimals"]
            p_str = self.format_price(item.price, dec)
            sl_str = self.format_price(item.stop_loss, dec)
            tp1_str = self.format_price(item.take_profit_1, dec)
            tp2_str = self.format_price(item.take_profit_2, dec)

            if "COMPRA" in item.signal:
                badge = f"[bold white on dark_green] {item.signal} [/bold white on dark_green]"
                recom = f"[bold green]Momento de COMPRAR a {p_str}[/bold green]"
            elif "VENDA" in item.signal:
                badge = f"[bold white on dark_red] {item.signal} [/bold white on dark_red]"
                recom = f"[bold red]Momento de VENDER a {p_str}[/bold red]"
            else:
                badge = "[bold white on grey37] AGUARDAR / NEUTRO [/bold white on grey37]"
                recom = "[yellow]Momento de AGUARDAR confirmação (sem entrada clara)[/yellow]"

            table = Table(box=box.MINIMAL_DOUBLE_HEAD, show_header=False, expand=True)
            table.add_column("Campo", style="bold cyan", width=22)
            table.add_column("Valor")

            table.add_row("Ativo", f"{config['icon']} [bold]{key}[/bold] - {config['name']}")
            table.add_row("Cotação Atual", f"[bold]{p_str}[/bold] (1h: {item.change_1h:+.2f}% | 24h: {item.change_24h:+.2f}%)")
            table.add_row("Diagnóstico Quant", f"{badge}  Score Confluência: [bold]{item.score:+d}[/bold]")
            table.add_row("Recomendação", recom)
            table.add_row("Médias Móveis (1h)", f"EMA9: {self.format_price(item.ema9, dec)} | EMA21: {self.format_price(item.ema21, dec)} | EMA50: {self.format_price(item.ema50, dec)}")
            table.add_row("Indicadores de Impulso", f"RSI(14): [bold]{item.rsi:.1f}[/bold] | MACD Hist: [bold]{item.macd_hist:.4f}[/bold] | ATR(14): {self.format_price(item.atr, dec)}")

            channel_str_r1 = f"[bold]{item.channel_breakout}[/bold]" if item.channel_breakout != "—" else "sem rompimento"
            table.add_row(
                "Canal & Volume (OBV)",
                f"Donchian(20): {self.format_price(item.donchian_lower, dec)} – {self.format_price(item.donchian_upper, dec)} "
                f"| Rompimento: {channel_str_r1} | OBV: [bold]{item.obv_trend}[/bold]",
            )

            if item.ichimoku_bias != "Indisponível":
                cloud_range = f"{self.format_price(item.ichimoku_cloud_bottom, dec)} – {self.format_price(item.ichimoku_cloud_top, dec)}"
            else:
                cloud_range = "histórico insuficiente"
            table.add_row(
                "Ichimoku (9/26/52)",
                f"Tenkan: {self.format_price(item.ichimoku_tenkan, dec)} | Kijun: {self.format_price(item.ichimoku_kijun, dec)} "
                f"| Nuvem: {cloud_range} | Posição: [bold]{item.ichimoku_bias}[/bold]",
            )

            table.add_row("Gerenciamento de Risco", f"Stop Loss: [bold red]{sl_str}[/bold red] | Take Profit 1: [bold green]{tp1_str}[/bold green] | Take Profit 2: [bold green]{tp2_str}[/bold green]")

            if item.reasons:
                reasons_str = "\n".join(f" • {r}" for r in item.reasons)
                table.add_row("Fatores Técnicos", reasons_str)

            self.console.print(Panel(table, border_style="cyan" if "COMPRA" in item.signal else ("red" if "VENDA" in item.signal else "grey50")))

    def start_loop(self):
        """Inicia o loop contínuo no terminal com atualização periódica e apitos."""
        self.console.clear()
        data_map: Dict[str, MarketData] = {}

        with self.console.status("[bold green]Conectando às exchanges e analisando gráficos de 1h...[/bold green]"):
            data_map = self.refresh(data_map)

        countdown = self.interval
        screen_mode = sys.stdout.isatty()
        with Live(self.build_dashboard(data_map, countdown), refresh_per_second=2, console=self.console, screen=screen_mode) as live:
            while True:
                try:
                    time.sleep(1)
                    countdown -= 1

                    if countdown <= 0:
                        data_map = self.refresh(data_map)
                        countdown = self.interval

                    live.update(self.build_dashboard(data_map, countdown))

                except KeyboardInterrupt:
                    break


# ---------------------------------------------------------------------------
# Entrada Principal (CLI)
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="GorilaTrader - Analisador de Cripto no Gráfico de 1h com Alertas Sonoros (Apito)"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=30,
        help="Intervalo de atualização em segundos no terminal (padrão: 30s)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Executa uma única análise técnica detalhada e encerra",
    )
    parser.add_argument(
        "--no-sound",
        action="store_true",
        help="Desativa os alertas sonoros (apitos)",
    )
    parser.add_argument(
        "--voice",
        action="store_true",
        help="Ativa locução sintética além do apito sonoro (requer spd-say no Linux)",
    )
    parser.add_argument(
        "--test-sound",
        action="store_true",
        help="Toca os apitos de Compra e Venda para teste e encerra",
    )
    parser.add_argument(
        "--no-telegram",
        action="store_true",
        help="Desativa o envio de alertas para o Telegram mesmo se TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID estiverem configurados",
    )
    parser.add_argument(
        "--test-telegram",
        action="store_true",
        help="Envia uma mensagem de teste para o Telegram configurado e encerra",
    )

    args = parser.parse_args()

    telegram_token, telegram_chat_id = resolve_telegram_credentials(TELEGRAM_CFG)
    if args.no_telegram:
        telegram_token, telegram_chat_id = None, None

    if args.test_telegram:
        console = Console()
        notifier = TelegramNotifier(telegram_token, telegram_chat_id)
        if not notifier.enabled:
            console.print("[red]❌ Telegram não configurado. Defina TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID (ou config.json).[/red]")
            return
        console.print("[bold yellow]📨 Enviando mensagem de teste para o Telegram...[/bold yellow]")
        notifier.send("🦍 <b>GorilaTrader</b>\nMensagem de teste - a integração com o Telegram está funcionando!")
        time.sleep(2)
        console.print("[bold green]✅ Mensagem enviada (verifique o Telegram).[/bold green]")
        return

    if args.test_sound:
        console = Console()
        console.print("[bold yellow]🔊 Testando apito sonoro de COMPRA...[/bold yellow]")
        se = SoundEngine(enabled=True, use_voice=args.voice)
        se.play_buy_alert("Bitcoin")
        time.sleep(1.8)
        console.print("[bold yellow]🔊 Testando apito sonoro de VENDA...[/bold yellow]")
        se.play_sell_alert("Bitcoin")
        time.sleep(1.8)
        console.print("[bold green]✅ Teste de som concluído com sucesso![/bold green]")
        return

    trader = GorilaTraderTerminal(
        interval=max(5, args.interval),
        sound_enabled=not args.no_sound,
        use_voice=args.voice,
        telegram_token=telegram_token,
        telegram_chat_id=telegram_chat_id,
    )

    if args.once:
        trader.run_once()
    else:
        try:
            trader.start_loop()
        except KeyboardInterrupt:
            pass
        print("\n🦍 GorilaTrader encerrado com sucesso. Bons trades!")


if __name__ == "__main__":
    main()
