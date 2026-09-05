#!/usr/bin/env python3
"""
GorilaTrader - Analisador Quantitativo de Cripto (Gráfico 1h)
Monitor em tempo real no terminal com alertas sonoros (apito) para Compra e Venda.
Ativos monitorados: Bitcoin (BTC), Ethereum (ETH), Solana (SOL), Pepe (PEPE) e Hyperliquid (HYPE).
"""

from __future__ import annotations

import argparse
import html
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
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text

# ---------------------------------------------------------------------------
# Diretório de dados: config.json, alerts_history.json e gorilatrader.log.
# Por padrão fica ao lado do script (uso local); em Docker, defina
# GORILATRADER_DATA_DIR apontando para um volume montado, para o estado
# sobreviver a restarts/rebuilds do container.
# ---------------------------------------------------------------------------

DATA_DIR = os.environ.get("GORILATRADER_DATA_DIR") or os.path.dirname(os.path.abspath(__file__))
os.makedirs(DATA_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Logging (falhas de rede/API vão para gorilatrader.log em vez de sumir em silêncio)
# ---------------------------------------------------------------------------

LOG_PATH = os.path.join(DATA_DIR, "gorilatrader.log")
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
    "mtf_confirmation": 15,  # Viés de 1h alinhado (ou não) com a tendência de 4h
}

API_URLS = {
    "binance_spot": "https://api.binance.com/api/v3/klines",
    "binance_futures": "https://fapi.binance.com/fapi/v1/klines",
    "bybit_spot": "https://api.bybit.com/v5/market/kline",
    "okx": "https://www.okx.com/api/v5/market/candles",
    "kraken": "https://api.kraken.com/0/public/OHLC",
}

# Formato do intervalo varia por exchange: Binance/Bybit usam "3m"/"5m"/.../"1M"
# direto, OKX usa maiúsculas pra hora/dia/semana/mês e Kraken usa minutos como
# inteiro (e não tem candle nativo de 3min nem de 1 mês - cai pro mais próximo
# que ela tem: 5min e 15 dias respectivamente).
_OKX_INTERVAL_MAP = {
    "3m": "3m", "5m": "5m", "15m": "15m", "1h": "1H", "4h": "4H",
    "1d": "1D", "1w": "1W", "1M": "1M",
}
_KRAKEN_INTERVAL_MAP = {
    "3m": 5, "5m": 5, "15m": 15, "1h": 60, "4h": 240,
    "1d": 1440, "1w": 10080, "1M": 21600,
}

# Timeframes selecionáveis pra análise principal (pergunta interativa na
# primeira execução, ou --timeframe). Cada um tem um timeframe de confirmação
# MTF proporcionalmente maior (ver CONFIRMAÇÃO MULTI-TIMEFRAME em analyze_dataframe).
AVAILABLE_TIMEFRAMES = ["15m", "1h", "4h", "1d"]
DEFAULT_TIMEFRAME = "1h"
MTF_TIMEFRAME_MAP = {"15m": "1h", "1h": "4h", "4h": "1d", "1d": "1w"}
TIMEFRAME_LABELS = {"15m": "15M", "1h": "1H", "4h": "4H", "1d": "1D", "1w": "1W"}
TIMEFRAME_FULL_LABELS = {"15m": "15 Minutos", "1h": "1 Hora", "4h": "4 Horas", "1d": "1 Dia", "1w": "1 Semana"}
TIMEFRAME_MINUTES = {"15m": 15, "1h": 60, "4h": 240, "1d": 1440, "1w": 10080}

CONFIG_PATH = os.path.join(DATA_DIR, "config.json")
USER_SETTINGS_PATH = os.path.join(DATA_DIR, "user_settings.json")


DEFAULT_PAPER_TRADING_CFG = {
    "enabled": True,
    "max_holding_hours": 200,  # mesma janela do backtest (MAX_HOLDING_BARS_DEFAULT, em candles de 1h)
}

DEFAULT_WEB_AUTH_CFG = {
    "password": "",  # vazio = autenticação desativada (padrão, compatível com o comportamento anterior)
}


def load_config(path: str = CONFIG_PATH) -> Tuple[dict, dict, dict, dict, dict]:
    """Carrega ativos, pesos, credenciais do Telegram, config do modo papel e
    da autenticação do dashboard web de config.json, mesclando com os padrões.

    Se o arquivo não existir ou estiver malformado, usa somente os padrões
    embutidos - o programa nunca deixa de funcionar por causa de config.json.
    """
    assets = dict(DEFAULT_ASSETS)
    weights = dict(DEFAULT_WEIGHTS)
    telegram: dict = {}
    paper_trading = dict(DEFAULT_PAPER_TRADING_CFG)
    web_auth = dict(DEFAULT_WEB_AUTH_CFG)

    if not os.path.exists(path):
        return assets, weights, telegram, paper_trading, web_auth

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        logger.error("Falha ao ler %s: %s. Usando configuração padrão.", path, exc)
        return assets, weights, telegram, paper_trading, web_auth

    if isinstance(data.get("assets"), dict) and data["assets"]:
        assets = data["assets"]
    if isinstance(data.get("weights"), dict):
        weights.update(data["weights"])
    if isinstance(data.get("telegram"), dict):
        telegram = data["telegram"]
    if isinstance(data.get("paper_trading"), dict):
        paper_trading.update(data["paper_trading"])
    if isinstance(data.get("web_auth"), dict):
        web_auth.update(data["web_auth"])

    return assets, weights, telegram, paper_trading, web_auth


def resolve_telegram_credentials(telegram_cfg: dict) -> Tuple[Optional[str], Optional[str]]:
    """Variáveis de ambiente têm prioridade sobre config.json (evita segredo em arquivo versionado)."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN") or telegram_cfg.get("bot_token")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID") or telegram_cfg.get("chat_id")
    return token, chat_id


def resolve_web_password(web_auth_cfg: dict) -> Optional[str]:
    """Senha do dashboard web (--serve). Variável de ambiente tem prioridade
    sobre config.json. Vazio/None = autenticação desativada (comportamento
    padrão, igual antes desse recurso existir)."""
    password = os.environ.get("GORILATRADER_WEB_PASSWORD") or web_auth_cfg.get("password")
    return password or None


ASSETS, WEIGHTS, TELEGRAM_CFG, PAPER_TRADING_CFG, WEB_AUTH_CFG = load_config()

# Timeframe do gráfico principal em uso nesta execução - ver load_or_prompt_settings.
TIMEFRAME = DEFAULT_TIMEFRAME

# ---------------------------------------------------------------------------
# Seleção de ativos digitada pela pessoa (--assets ou prompt interativo no
# terminal), sem precisar editar config.json.
# ---------------------------------------------------------------------------


def _detect_display_decimals(price: float) -> int:
    """Heurística de casas decimais pra exibição a partir do preço - mesmo
    espírito de BTC (2 casas) vs. PEPE (8 casas): quanto menor o preço
    unitário, mais casas decimais precisa pra não arredondar tudo pra zero."""
    if price >= 1:
        return 2
    if price >= 0.01:
        return 4
    if price >= 0.0001:
        return 6
    return 8


def resolve_assets_from_tickers(raw: str, console: Optional[Console] = None) -> dict:
    """Constrói um dict de ativos (mesmo formato de DEFAULT_ASSETS/config.json)
    a partir de uma lista de tickers digitados pela pessoa (ex.: "BTC, eth, doge").

    Um ticker já conhecido (nos ativos atualmente configurados ou nos padrões
    embutidos) reaproveita nome/exchange/ícone/decimais já curados. Um ticker
    novo assume par USDT na Binance spot e detecta as casas decimais de
    exibição buscando o preço atual - se a busca falhar, cai para 2 casas e
    avisa (o símbolo pode simplesmente não existir na Binance)."""
    tickers = [t.strip().upper() for t in raw.replace(";", ",").split(",") if t.strip()]
    resolved: dict = {}
    for ticker in tickers:
        if ticker in ASSETS:
            resolved[ticker] = ASSETS[ticker]
        elif ticker in DEFAULT_ASSETS:
            resolved[ticker] = DEFAULT_ASSETS[ticker]
        else:
            symbol = f"{ticker}USDT"
            df = CryptoAnalyzer.fetch_klines(symbol, "binance_spot", interval="1h", limit=2)
            if df is not None and len(df):
                decimals = _detect_display_decimals(float(df["close"].iloc[-1]))
            else:
                decimals = 2
                if console:
                    console.print(
                        f"[yellow]⚠ Não encontrei {symbol} na Binance agora - "
                        f"vou incluir {ticker} mesmo assim, mas pode não ter dados.[/yellow]"
                    )
            resolved[ticker] = {
                "name": ticker,
                "symbol": symbol,
                "exchange": "binance_spot",
                "icon": "🪙",
                "decimals": decimals,
            }
    return resolved


def load_user_settings(path: str = USER_SETTINGS_PATH) -> Optional[dict]:
    """Lê os ativos/timeframe escolhidos na última vez que a pergunta
    interativa foi respondida (ver load_or_prompt_settings). None se nunca
    foi respondida ainda ou o arquivo está corrompido (nesse caso a pergunta
    volta a aparecer, como se fosse a primeira execução)."""
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except Exception as exc:
        logger.warning("Falha ao ler %s: %s. Vou perguntar de novo.", path, exc)
    return None


def save_user_settings(assets_raw: str, timeframe: str, path: str = USER_SETTINGS_PATH) -> None:
    try:
        tmp_path = path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump({"assets": assets_raw, "timeframe": timeframe}, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    except Exception:
        logger.warning("Falha ao salvar %s", path, exc_info=True)


def load_or_prompt_settings(headless_mode: bool, console: Optional[Console] = None) -> None:
    """Carrega os ativos e o timeframe salvos em USER_SETTINGS_PATH (ajusta
    os globais ASSETS/TIMEFRAME). Se ainda não existe nada salvo e a sessão é
    interativa, pergunta uma única vez (ativos + timeframe) e salva a
    resposta - nas próximas execuções não pergunta mais (use --reconfigure
    pra apagar a preferência salva e responder de novo)."""
    global ASSETS, TIMEFRAME

    saved = load_user_settings()
    if saved is not None:
        raw_assets = saved.get("assets")
        if raw_assets:
            ASSETS = resolve_assets_from_tickers(raw_assets, console=console)
        tf = saved.get("timeframe")
        if tf in AVAILABLE_TIMEFRAMES:
            TIMEFRAME = tf
        return

    if headless_mode or not sys.stdin.isatty():
        return

    console = console or Console()
    raw = Prompt.ask(
        "[bold cyan]🦍 Quais criptos você quer acompanhar?[/bold cyan] "
        "[dim](ex.: BTC,ETH,DOGE — Enter para usar os ativos configurados)[/dim]",
        default="",
        console=console,
    )
    if raw.strip():
        ASSETS = resolve_assets_from_tickers(raw, console=console)
        assets_to_save = raw.strip()
    else:
        assets_to_save = ",".join(ASSETS.keys())

    tf_choice = Prompt.ask(
        "[bold cyan]🕒 Qual timeframe você quer ficar analisando?[/bold cyan] "
        f"[dim]({' / '.join(AVAILABLE_TIMEFRAMES)} — Enter para {DEFAULT_TIMEFRAME})[/dim]",
        default=DEFAULT_TIMEFRAME,
        choices=AVAILABLE_TIMEFRAMES,
        show_choices=False,
        console=console,
    )
    TIMEFRAME = tf_choice if tf_choice in AVAILABLE_TIMEFRAMES else DEFAULT_TIMEFRAME

    save_user_settings(assets_to_save, TIMEFRAME, USER_SETTINGS_PATH)
    console.print(
        f"[dim]✅ Preferências salvas ({os.path.basename(USER_SETTINGS_PATH)}) - "
        "não vou perguntar de novo. Use --reconfigure pra mudar depois.[/dim]"
    )


# ---------------------------------------------------------------------------
# Persistência do Histórico de Alertas (sobrevive a reinícios do programa)
# ---------------------------------------------------------------------------

ALERTS_HISTORY_PATH = os.path.join(DATA_DIR, "alerts_history.json")
MAX_HISTORY_ENTRIES = 200

# Estado do modo papel (posições simuladas abertas/fechadas) - ver paper_trading.py
PAPER_TRADES_PATH = os.path.join(DATA_DIR, "paper_trades.json")


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

    def send_sync(self, text: str) -> Tuple[bool, str]:
        """Envia a mensagem e espera a resposta - usado por --test-telegram
        para reportar sucesso/falha reais em vez de assumir sucesso."""
        if not self.enabled:
            return False, "Telegram não configurado."
        try:
            url = f"{self.API_BASE}/bot{self.bot_token}/sendMessage"
            r = requests.post(
                url,
                json={"chat_id": self.chat_id, "text": text, "parse_mode": "HTML"},
                timeout=8,
            )
            if r.status_code == 200:
                return True, "OK"
            return False, f"HTTP {r.status_code}: {r.text[:300]}"
        except Exception as exc:
            return False, str(exc)

    def send(self, text: str) -> None:
        """Envia a mensagem de forma assíncrona (não bloqueia o loop do dashboard)."""
        if not self.enabled:
            return

        def _runner():
            ok, detail = self.send_sync(text)
            if not ok:
                logger.warning("Falha ao enviar alerta ao Telegram: %s", detail)

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
    bollinger_status: str  # Dentro do Canal, Rompeu Superior, Rompeu Inferior
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
    mtf_bias: Optional[str]  # ALTA, BAIXA ou None (tendência do candle de 4h)
    signal: str  # FORTE COMPRA, COMPRA, NEUTRO, VENDA, FORTE VENDA
    score: int  # -100 a +100
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    reasons: List[str]
    timestamp: datetime = field(default_factory=datetime.now)


class CryptoAnalyzer:
    """Análise técnica institucional para o gráfico de 1h."""

    # Cache do candle de timeframe maior (4h) usado no filtro de confirmação
    # multi-timeframe: um candle de 4h só fecha a cada 4h, então buscá-lo a
    # cada ciclo de 1h (ou a cada 20-30s no dashboard web) seria desperdício
    # de requisições. {"SYMBOL:interval": (timestamp_do_fetch, df)}
    _mtf_cache: Dict[str, Tuple[float, Optional[pd.DataFrame]]] = {}
    MTF_CACHE_TTL_SECONDS = 900  # 15 min

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

    @staticmethod
    def _fetch_okx(symbol: str, interval: str, limit: int) -> Optional[pd.DataFrame]:
        """`symbol` no formato nativo da OKX (ex.: BTC-USDT, com hífen)."""
        bar = _OKX_INTERVAL_MAP.get(interval, interval.upper())
        url = f"{API_URLS['okx']}?instId={symbol}&bar={bar}&limit={limit}"
        r = requests.get(url, timeout=8)
        r.raise_for_status()
        rows = r.json().get("data", [])
        if not rows:
            return None
        rows = rows[::-1]  # OKX retorna do candle mais recente para o mais antigo
        df = pd.DataFrame(rows, columns=[
            "open_time", "open", "high", "low", "close", "vol", "vol_ccy", "vol_ccy_quote", "confirm"
        ])
        for col in ["open", "high", "low", "close", "vol"]:
            df[col] = df[col].astype(float)
        return df

    @staticmethod
    def _fetch_kraken(symbol: str, interval: str, limit: int) -> Optional[pd.DataFrame]:
        """`symbol` no formato nativo da Kraken (ex.: XBTUSDT). A Kraken devolve
        os candles sob uma chave própria do par (que pode não ser idêntica ao
        `pair` pedido, ex.: BTC -> XBT) - por isso pegamos a única lista de
        candles do resultado, ignorando a chave "last"."""
        kraken_interval = _KRAKEN_INTERVAL_MAP.get(interval, 60)
        url = f"{API_URLS['kraken']}?pair={symbol}&interval={kraken_interval}"
        r = requests.get(url, timeout=8)
        r.raise_for_status()
        payload = r.json()
        if payload.get("error"):
            logger.warning("Kraken retornou erro para %s: %s", symbol, payload["error"])
            return None

        candle_lists = [v for k, v in payload.get("result", {}).items() if k != "last"]
        if not candle_lists or not candle_lists[0]:
            return None
        rows = candle_lists[0]
        if limit:
            rows = rows[-limit:]

        df = pd.DataFrame(rows, columns=["open_time", "open", "high", "low", "close", "vwap", "vol", "count"])
        df["open_time"] = (df["open_time"].astype(float) * 1000).astype("int64")  # segundos -> ms
        for col in ["open", "high", "low", "close", "vol"]:
            df[col] = df[col].astype(float)
        return df

    @classmethod
    def fetch_klines(cls, symbol: str, exchange: str, interval: str = "1h", limit: int = 100) -> Optional[pd.DataFrame]:
        if exchange == "okx":
            try:
                df = cls._fetch_okx(symbol, interval, limit)
                if df is None:
                    logger.error("OKX não retornou candles para %s. Sem dados disponíveis.", symbol)
                return df
            except Exception as exc:
                logger.error("OKX falhou para %s: %s. Sem dados disponíveis.", symbol, exc)
                return None

        if exchange == "kraken":
            try:
                df = cls._fetch_kraken(symbol, interval, limit)
                if df is None:
                    logger.error("Kraken não retornou candles para %s. Sem dados disponíveis.", symbol)
                return df
            except Exception as exc:
                logger.error("Kraken falhou para %s: %s. Sem dados disponíveis.", symbol, exc)
                return None

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
    def fetch_mtf_klines(cls, symbol: str, exchange: str, interval: str = "4h", limit: int = 120) -> Optional[pd.DataFrame]:
        """Busca o timeframe maior usado no filtro de confirmação, com cache
        (ver MTF_CACHE_TTL_SECONDS) para não bater na API a cada atualização."""
        cache_key = f"{symbol}:{interval}"
        now = time.time()
        cached = cls._mtf_cache.get(cache_key)
        if cached is not None and (now - cached[0]) < cls.MTF_CACHE_TTL_SECONDS:
            return cached[1]

        df = cls.fetch_klines(symbol, exchange, interval=interval, limit=limit)
        cls._mtf_cache[cache_key] = (now, df)
        return df

    @classmethod
    def analyze_asset(cls, key: str, config: dict, weights: Optional[dict] = None) -> Optional[MarketData]:
        df = cls.fetch_klines(config["symbol"], config["exchange"], interval=TIMEFRAME, limit=250)
        if df is None or len(df) < 50:
            logger.warning("Dados insuficientes para %s (%s candles)", key, 0 if df is None else len(df))
            return None
        mtf_interval = MTF_TIMEFRAME_MAP.get(TIMEFRAME, "4h")
        mtf_df = cls.fetch_mtf_klines(config["symbol"], config["exchange"], interval=mtf_interval, limit=120)
        return cls.analyze_dataframe(key, config, df, weights, mtf_df=mtf_df)

    @classmethod
    def analyze_dataframe(
        cls,
        key: str,
        config: dict,
        df: pd.DataFrame,
        weights: Optional[dict] = None,
        mtf_df: Optional[pd.DataFrame] = None,
    ) -> Optional[MarketData]:
        """Calcula os indicadores e a matriz de confluência a partir de um
        DataFrame de candles já carregado (separado de analyze_asset para
        permitir testar a lógica de decisão sem depender de rede).

        `mtf_df` é opcional: candles de um timeframe maior (ex.: 4h) usados
        só no filtro de confirmação multi-timeframe - se omitido, esse fator
        simplesmente não contribui pontuação (score 0, sem razão listada)."""
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

        candles_per_24h = max(1, round(1440 / TIMEFRAME_MINUTES.get(TIMEFRAME, 60)))
        idx_24h = max(0, len(c) - candles_per_24h - 1)
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

        # Posição em relação ao canal de Bollinger: dentro das bandas, ou
        # fechamento além de uma delas (rompimento, diferente do simples
        # "toque" perto da banda que já compõe o score em D).
        if price > b_up:
            bollinger_status = "Rompeu Superior"
        elif price < b_low:
            bollinger_status = "Rompeu Inferior"
        else:
            bollinger_status = "Dentro do Canal"

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

        # Filtro de confirmação multi-timeframe: viés do candle de 4h (preço
        # vs EMA50 desse timeframe) comparado com o viés imediato de 1h
        # (preço vs EMA21). Reforça o score quando os dois concordam e
        # penaliza quando o sinal de 1h vai contra a tendência maior.
        mtf_bias: Optional[str] = None
        if mtf_df is not None and len(mtf_df) >= 55:
            mtf_close = mtf_df["close"]
            mtf_ema50 = mtf_close.ewm(span=50, adjust=False).mean()
            mtf_bias = "ALTA" if float(mtf_close.iloc[-1]) > float(mtf_ema50.iloc[-1]) else "BAIXA"

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

        # --- I) CONFIRMAÇÃO MULTI-TIMEFRAME ---
        if mtf_bias is not None:
            local_bias = "ALTA" if price > e21 else "BAIXA"
            mtf_label = MTF_TIMEFRAME_MAP.get(TIMEFRAME, "4h")
            main_label = TIMEFRAME
            if local_bias == mtf_bias:
                score += w["mtf_confirmation"]
                reasons.append(f"Tendência de {mtf_label} ({mtf_bias.lower()}) confirma o viés de {main_label}")
            else:
                score -= w["mtf_confirmation"]
                reasons.append(f"Tendência de {mtf_label} ({mtf_bias.lower()}) diverge do {main_label} - contra a tendência maior")

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
            bollinger_status=bollinger_status,
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
            mtf_bias=mtf_bias,
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

MAX_FETCH_WORKERS = 20  # teto de threads simultâneas na busca, mesmo com dezenas/centenas de ativos (--assets)

# Sinais de "mais certeza" - único critério usado tanto pro filtro de entrada
# quanto pro aviso de conclusão (STOP/TP) no Telegram, mantendo os dois
# consistentes: só um trade aberto por um sinal FORTE gera aviso de saída.
HIGH_CONFIDENCE_SIGNALS = ("FORTE COMPRA", "FORTE VENDA")

# Dimensões-base do layout do dashboard, calibradas originalmente pra 5 ativos
# fixos (BTC/ETH/SOL/PEPE/HYPE) - agora que qualquer quantidade de ativos pode
# ser configurada (config.json ou --assets), a tabela cresce dinamicamente com
# o número de ativos em vez de ficar travada em 15 linhas (ver build_dashboard).
BASE_MAIN_LAYOUT_SIZE = 15
BASE_DETAILS_LAYOUT_SIZE = 9
BASE_ASSET_COUNT = 5
MIN_DETAILS_LAYOUT_SIZE = 6
MIN_MAIN_LAYOUT_SIZE = 6


class GorilaTraderTerminal:
    """Gerenciador do loop em tempo real e visualização no terminal."""

    def __init__(
        self,
        interval: int = 30,
        sound_enabled: bool = True,
        use_voice: bool = False,
        telegram_token: Optional[str] = None,
        telegram_chat_id: Optional[str] = None,
        paper_trading_enabled: bool = True,
        paper_trading_max_holding_hours: int = 200,
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

        self.paper: Optional["PaperTradingEngine"] = None
        if paper_trading_enabled:
            from paper_trading import PaperTradingEngine  # import tardio: evita ciclo de import no nível de módulo

            self.paper = PaperTradingEngine(PAPER_TRADES_PATH, max_holding_hours=paper_trading_max_holding_hours)

    def fetch_all(self) -> Dict[str, Optional[MarketData]]:
        """Busca e analisa todos os ativos em paralelo (evita Nx latência sequencial).

        `max_workers` é limitado (MAX_FETCH_WORKERS) mesmo com dezenas/centenas
        de ativos configurados - sem isso, uma lista grande via --assets abriria
        uma thread por ativo e bateria na exchange com todas as requisições de
        uma vez só, arriscando rate limit (429). O ThreadPoolExecutor enfileira
        o resto normalmente, só limita quantas rodam ao mesmo tempo."""
        results: Dict[str, Optional[MarketData]] = {}
        with ThreadPoolExecutor(max_workers=min(len(ASSETS), MAX_FETCH_WORKERS) or 1) as executor:
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
                if self.paper is not None:
                    closed_trade = self.paper.update(res)
                    if closed_trade is not None and closed_trade.signal in HIGH_CONFIDENCE_SIGNALS:
                        self._record_trade_conclusion(closed_trade)
            else:
                self.stale[key] = True
        return data_map

    def format_price(self, price: float, decimals: int) -> str:
        if decimals <= 2:
            return f"${price:,.2f}"
        return f"${price:.{decimals}f}"

    def _layout_sizes(self) -> Tuple[int, int]:
        """Altura das regiões "main" (tabela de ativos) e "details" (histórico
        de alertas): cresce com o número de ativos configurados (1 linha a mais
        por ativo além dos 5 originais) e se ajusta ao terminal disponível -
        primeiro encolhe o histórico de alertas (até um mínimo), só depois a
        própria tabela, garantindo que o dashboard sempre usa a tela toda em
        vez de cortar ativos fora quando há mais de 5 configurados (--assets)."""
        header_size, footer_size = 3, 3
        main_size = BASE_MAIN_LAYOUT_SIZE + max(0, len(ASSETS) - BASE_ASSET_COUNT)
        details_size = BASE_DETAILS_LAYOUT_SIZE

        try:
            console_height = self.console.size.height
        except Exception:
            console_height = 0

        if console_height:
            available = console_height - header_size - footer_size
            overflow = (main_size + details_size) - available
            if overflow > 0:
                shrink_details = min(overflow, details_size - MIN_DETAILS_LAYOUT_SIZE)
                if shrink_details > 0:
                    details_size -= shrink_details
                    overflow -= shrink_details
                if overflow > 0:
                    main_size = max(main_size - overflow, MIN_MAIN_LAYOUT_SIZE)

        return main_size, details_size

    def build_dashboard(self, data_map: Dict[str, MarketData], countdown: int) -> Layout:
        main_size, details_size = self._layout_sizes()
        layout = Layout()
        layout.split(
            Layout(name="header", size=3),
            Layout(name="main", size=main_size),
            Layout(name="details", size=details_size),
            Layout(name="footer", size=3),
        )

        sound_status = "[bold green]🔊 APITO ATIVO[/bold green]" if self.sound.enabled else "[yellow]🔇 MUDO[/yellow]"
        telegram_status = "[bold green]📨 TELEGRAM ATIVO[/bold green]" if self.telegram.enabled else "[dim]📨 Telegram off[/dim]"
        time_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        tf_label = TIMEFRAME_LABELS.get(TIMEFRAME, "1H")
        header_text = Text.from_markup(
            f" [bold cyan]GORILATRADER[/bold cyan] · Análise {tf_label} Cripto em Tempo Real · {sound_status} · {telegram_status} · 🕒 {time_str}"
        )
        layout["header"].update(Panel(header_text, style="cyan", box=box.ROUNDED))

        table = Table(box=box.ROUNDED, expand=True, header_style="bold bright_white on grey23")
        table.add_column("Ativo", justify="left", style="bold", width=16)
        table.add_column("Preço Atual", justify="right", width=15)
        table.add_column(f"{tf_label} %", justify="right", width=9)
        table.add_column("24h %", justify="right", width=9)
        table.add_column("RSI (14)", justify="right", width=10)
        table.add_column("MACD Hist", justify="right", width=11)
        table.add_column("Tendência", justify="center", width=14)
        table.add_column("Ichimoku", justify="center", width=17)
        table.add_column("Canal Donch.", justify="center", width=12)
        table.add_column("Bollinger", justify="center", width=15)
        table.add_column(f"SINAL {tf_label}", justify="center", width=17)
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
                table.add_row(f"{icon} {key}", status, "—", "—", "—", "—", "—", "—", "—", "—", "—", "—", "—", "—", "—")
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

            if item.bollinger_status == "Rompeu Superior":
                bollinger_str = "[bold red]▲ Rompeu Sup.[/bold red]"
            elif item.bollinger_status == "Rompeu Inferior":
                bollinger_str = "[bold green]▼ Rompeu Inf.[/bold green]"
            else:
                bollinger_str = f"[dim]◆ No Canal ({item.bb_zscore:+.1f}σ)[/dim]"

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
                bollinger_str,
                sig_str,
                score_str,
                f"[red]{sl_str}[/red]",
                f"[green]{tp1_str}[/green]",
                f"[bold green]{tp2_str}[/bold green]",
            )

        tf_full_label = TIMEFRAME_FULL_LABELS.get(TIMEFRAME, "1 Hora")
        layout["main"].update(Panel(table, title=f"[bold]📊 Monitor Gráfico de {tf_full_label} (Corte Técnico)[/bold]", border_style="blue"))

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

    def _record_alert(self, item: MarketData, label: str, bullish: bool, detail: str, send_telegram: bool = True):
        """Ponto único de disparo de qualquer aviso: apito, histórico (persistido)
        e Telegram. `send_telegram=False` mantém apito e histórico normalmente,
        só pula o envio ao Telegram - usado por check_and_alert para deixar o
        Telegram seletivo (só sinais FORTE), sem afetar o resto do dashboard."""
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

        if not send_telegram:
            return

        emoji = "🟢" if bullish else "🔴"
        # Telegram usa parse_mode HTML: qualquer "<"/">" vindo de texto dinâmico
        # (ex.: fatores técnicos como "Preço < EMA9 < EMA21") é interpretado como
        # tag e derruba a mensagem inteira ("can't parse entities") - escapa tudo
        # que não é a tag literal do próprio template (<b>...</b>).
        text = (
            f"{emoji} <b>GorilaTrader</b> · {ASSETS[key]['icon']} <b>{html.escape(key)}</b>\n"
            f"{html.escape(label)}\n"
            f"Preço: {html.escape(p_str)}\n"
            f"{html.escape(detail)}\n"
            f"🕒 {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"
        )
        self.telegram.send(text)

    def _record_trade_conclusion(self, trade) -> None:
        """Avisa quando uma posição simulada do modo papel conclui (STOP/TP) -
        só chamado para trades abertos a partir de sinal FORTE (mesmo filtro de
        "mais certeza" da entrada), consistente com check_and_alert. Vai pro
        mesmo histórico de alertas do dashboard e, se configurado, pro Telegram."""
        key = trade.asset_key
        cfg = ASSETS.get(key, {})
        decimals = cfg.get("decimals", 2)
        icon = cfg.get("icon", "")
        exit_str = self.format_price(trade.exit_price, decimals)

        win = trade.outcome in ("TP1", "TP1_TIMEOUT", "TP2")
        if trade.outcome in ("STOP", "STOP_AFTER_TP1"):
            label = "🛑 STOP"
        elif trade.outcome == "TP2":
            label = "✅ TAKE PROFIT (TP2)"
        elif trade.outcome == "TP1_TIMEOUT":
            label = "✅ TAKE PROFIT PARCIAL (TP1 atingido antes do prazo)"
        else:  # TIMEOUT
            label = "⏱ ENCERRADO POR TEMPO (sem tocar SL/TP)"

        detail = f"Resultado: {trade.r_multiple:+.2f}R ({trade.pct_return:+.2f}%) · Entrada: {trade.signal}"

        self.history_alerts.append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "asset": f"{icon} {key}",
            "signal": label,
            "price": exit_str,
            "reason": detail,
        })
        self.history_alerts = self.history_alerts[-MAX_HISTORY_ENTRIES:]
        save_alert_history(self.history_alerts)

        emoji = "🟢" if win else "🔴"
        text = (
            f"{emoji} <b>GorilaTrader</b> · {icon} <b>{html.escape(key)}</b>\n"
            f"{html.escape(label)}\n"
            f"Saída: {html.escape(exit_str)}\n"
            f"{html.escape(detail)}\n"
            f"🕒 {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"
        )
        self.telegram.send(text)

    def check_and_alert(self, item: MarketData):
        """Verifica se houve mudança de sinal (COMPRA/VENDA), dispara o aviso e
        abre a posição simulada do modo papel (se habilitado) na mesma transição."""
        key = item.asset_key
        last_sig = self.last_signals.get(key)
        current_sig = item.signal
        is_fresh_buy = current_sig in ("COMPRA", "FORTE COMPRA") and last_sig not in ("COMPRA", "FORTE COMPRA")
        is_fresh_sell = current_sig in ("VENDA", "FORTE VENDA") and last_sig not in ("VENDA", "FORTE VENDA")

        if is_fresh_buy:
            reason_summary = " · ".join(item.reasons[:2]) if item.reasons else "Confluência altista confirmada"
            self._record_alert(item, current_sig, bullish=True, detail=reason_summary,
                                send_telegram=current_sig in HIGH_CONFIDENCE_SIGNALS)
        elif is_fresh_sell:
            reason_summary = " · ".join(item.reasons[:2]) if item.reasons else "Confluência baixista confirmada"
            self._record_alert(item, current_sig, bullish=False, detail=reason_summary,
                                send_telegram=current_sig in HIGH_CONFIDENCE_SIGNALS)

        if self.paper is not None:
            self.paper.maybe_open(item, is_fresh_buy, is_fresh_sell)

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
        tf_label = TIMEFRAME_LABELS.get(TIMEFRAME, "1H")
        tf_full_label = TIMEFRAME_FULL_LABELS.get(TIMEFRAME, "1 Hora")
        self.console.print("\n[bold cyan]═══════════════════════════════════════════════════════════════════════════════[/bold cyan]")
        self.console.print(f" [bold white on blue] GORILATRADER · RELATÓRIO DO GRÁFICO DE {tf_full_label.upper()} [/bold white on blue]")
        self.console.print(f" [dim]Data/Hora: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')} · Timeframe: {tf_label}[/dim]")
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
            table.add_row("Cotação Atual", f"[bold]{p_str}[/bold] ({tf_label}: {item.change_1h:+.2f}% | 24h: {item.change_24h:+.2f}%)")
            table.add_row("Diagnóstico Quant", f"{badge}  Score Confluência: [bold]{item.score:+d}[/bold]")
            table.add_row("Recomendação", recom)
            table.add_row(f"Médias Móveis ({tf_label})", f"EMA9: {self.format_price(item.ema9, dec)} | EMA21: {self.format_price(item.ema21, dec)} | EMA50: {self.format_price(item.ema50, dec)}")
            table.add_row("Indicadores de Impulso", f"RSI(14): [bold]{item.rsi:.1f}[/bold] | MACD Hist: [bold]{item.macd_hist:.4f}[/bold] | ATR(14): {self.format_price(item.atr, dec)}")

            table.add_row(
                "Bandas de Bollinger (20,2)",
                f"Inferior: {self.format_price(item.bb_lower, dec)} | Média: {self.format_price(item.bb_middle, dec)} "
                f"| Superior: {self.format_price(item.bb_upper, dec)} | Posição: [bold]{item.bollinger_status}[/bold] ({item.bb_zscore:+.1f}σ)",
            )

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

            mtf_str = f"[bold]{item.mtf_bias}[/bold]" if item.mtf_bias else "[dim]indisponível[/dim]"
            mtf_interval_label = TIMEFRAME_LABELS.get(MTF_TIMEFRAME_MAP.get(TIMEFRAME, "4h"), "4H")
            table.add_row(f"Tendência Maior ({mtf_interval_label})", f"Viés do candle de {mtf_interval_label}: {mtf_str}")

            table.add_row("Gerenciamento de Risco", f"Stop Loss: [bold red]{sl_str}[/bold red] | Take Profit 1: [bold green]{tp1_str}[/bold green] | Take Profit 2: [bold green]{tp2_str}[/bold green]")

            if item.reasons:
                reasons_str = "\n".join(f" • {r}" for r in item.reasons)
                table.add_row("Fatores Técnicos", reasons_str)

            self.console.print(Panel(table, border_style="cyan" if "COMPRA" in item.signal else ("red" if "VENDA" in item.signal else "grey50")))

    def start_loop(self):
        """Inicia o loop contínuo no terminal com atualização periódica e apitos."""
        self.console.clear()
        data_map: Dict[str, MarketData] = {}

        with self.console.status(f"[bold green]Conectando às exchanges e analisando gráficos de {TIMEFRAME_LABELS.get(TIMEFRAME, '1H')}...[/bold green]"):
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
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Sobe o dashboard web (gráfico estilo TradingView) em vez do terminal",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Porta do dashboard web ao usar --serve (padrão: 8000)",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Endereço de bind do dashboard web ao usar --serve (padrão: 127.0.0.1, use 0.0.0.0 para acesso na rede)",
    )
    parser.add_argument(
        "--backtest",
        metavar="ATIVO",
        help="Roda um backtest da matriz de decisão para o ativo informado (ex.: BTC) e encerra",
    )
    parser.add_argument(
        "--backtest-days",
        type=int,
        default=60,
        help="Quantos dias de histórico (candles de 1h) usar no --backtest (padrão: 60)",
    )
    parser.add_argument(
        "--no-paper-trading",
        action="store_true",
        help="Desativa o modo papel (simulação de execução dos sinais) nesta execução do terminal",
    )
    parser.add_argument(
        "--paper-report",
        action="store_true",
        help="Mostra o relatório de performance do modo papel (trades simulados acumulados) e encerra",
    )
    parser.add_argument(
        "--reset-paper-trading",
        action="store_true",
        help="Apaga o histórico do modo papel (paper_trades.json) e encerra",
    )
    parser.add_argument(
        "--assets",
        metavar="TICKERS",
        help="Criptos a acompanhar nesta execução, separadas por vírgula (ex.: BTC,ETH,DOGE) - "
        "sobrepõe os ativos salvos/configurados sem editar arquivo nem afetar o que fica salvo. "
        "Sem esta flag, a primeira execução pergunta interativamente quais criptos e qual "
        "timeframe acompanhar e salva a resposta - as próximas execuções carregam direto, sem "
        "perguntar de novo (veja --reconfigure).",
    )
    parser.add_argument(
        "--timeframe",
        choices=AVAILABLE_TIMEFRAMES,
        help="Timeframe do gráfico principal a analisar nesta execução - sobrepõe o timeframe "
        "salvo/configurado sem editar arquivo nem afetar o que fica salvo.",
    )
    parser.add_argument(
        "--reconfigure",
        action="store_true",
        help="Apaga os ativos/timeframe salvos e volta a perguntar interativamente na próxima execução.",
    )

    args = parser.parse_args()

    global ASSETS, TIMEFRAME
    headless_mode = bool(
        args.backtest or args.serve or args.paper_report or args.reset_paper_trading
        or args.test_telegram or args.test_sound
    )

    if args.reconfigure and os.path.exists(USER_SETTINGS_PATH):
        os.remove(USER_SETTINGS_PATH)

    # Carrega ativos/timeframe salvos como base (não pergunta se --assets/--timeframe
    # já foram passados nesta execução - eles têm prioridade e não sobrescrevem o
    # arquivo salvo, ver overrides abaixo).
    load_or_prompt_settings(headless_mode=headless_mode or bool(args.assets or args.timeframe))

    if args.assets:
        ASSETS = resolve_assets_from_tickers(args.assets, console=Console())
    if args.timeframe:
        TIMEFRAME = args.timeframe

    if args.backtest:
        console = Console()
        key = args.backtest.upper()
        if key not in ASSETS:
            console.print(f"[red]❌ Ativo desconhecido: {key}. Disponíveis: {', '.join(ASSETS)}[/red]")
            return
        try:
            from backtest import print_backtest_report, run_backtest
        except ImportError as exc:
            console.print(f"[red]❌ Dependência ausente para o backtest: {exc}[/red]")
            return
        console.print(f"[bold yellow]📊 Rodando backtest de {key} ({args.backtest_days} dias de histórico)...[/bold yellow]")
        try:
            trades, summary = run_backtest(key, ASSETS[key], days=args.backtest_days, weights=WEIGHTS)
        except Exception as exc:
            logger.exception("Falha ao rodar backtest de %s", key)
            console.print(f"[red]❌ Falha ao rodar o backtest: {exc}[/red]")
            return
        print_backtest_report(console, key, ASSETS[key], trades, summary)
        return

    if args.paper_report:
        console = Console()
        from paper_trading import PaperTradingEngine, print_paper_trading_report

        engine = PaperTradingEngine(PAPER_TRADES_PATH, max_holding_hours=PAPER_TRADING_CFG.get("max_holding_hours", 200))
        print_paper_trading_report(console, ASSETS, engine)
        return

    if args.reset_paper_trading:
        console = Console()
        if os.path.exists(PAPER_TRADES_PATH):
            os.remove(PAPER_TRADES_PATH)
        console.print("[bold green]✅ Histórico do modo papel apagado.[/bold green]")
        return

    if args.serve:
        try:
            from webserver import AUTH_ENABLED, run_server
        except ImportError as exc:
            console = Console()
            console.print(f"[red]❌ Dependências do dashboard web ausentes: {exc}[/red]")
            console.print("[yellow]Instale com: pip install fastapi 'uvicorn[standard]' python-multipart[/yellow]")
            return
        console = Console()
        console.print(f"[bold green]🦍 GorilaTrader Web em http://{args.host}:{args.port}[/bold green]")
        if args.host not in ("127.0.0.1", "localhost", "::1") and not AUTH_ENABLED:
            console.print(
                "[bold yellow]⚠ Exposto fora do localhost sem senha configurada - qualquer um na rede "
                "pode acessar. Defina GORILATRADER_WEB_PASSWORD ou 'web_auth.password' em config.json "
                "para exigir login.[/bold yellow]"
            )
        run_server(host=args.host, port=args.port)
        return

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
        ok, detail = notifier.send_sync("🦍 <b>GorilaTrader</b>\nMensagem de teste - a integração com o Telegram está funcionando!")
        if ok:
            console.print("[bold green]✅ Mensagem enviada com sucesso (verifique o Telegram).[/bold green]")
        else:
            console.print(f"[red]❌ Falha ao enviar: {detail}[/red]")
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
        paper_trading_enabled=PAPER_TRADING_CFG.get("enabled", True) and not args.no_paper_trading,
        paper_trading_max_holding_hours=PAPER_TRADING_CFG.get("max_holding_hours", 200),
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
