"""
GorilaTrader - Backtest da matriz de confluência.

Rode com:
    python3 gorilatrader.py --backtest BTC
    python3 gorilatrader.py --backtest BTC --backtest-days 90

Metodologia (importante para interpretar os resultados):

- Em cada barra i, o sinal é calculado usando SOMENTE os candles até e
  incluindo i (`df.iloc[:i+1]`) - a mesma janela que o motor veria "ao vivo"
  naquele momento. Não há vazamento de dados futuros na geração do sinal.
- Uma "entrada" só abre quando o sinal muda para COMPRA/FORTE COMPRA ou
  VENDA/FORTE VENDA (mesma lógica anti-spam do dashboard: check_and_alert).
  Só uma posição por vez é simulada.
- Depois de aberta, a posição É resolvida olhando os candles seguintes de
  verdade (isso não é "trapaça" - é exatamente o que queremos medir: o que
  teria acontecido depois do sinal).
- Se STOP e algum alvo (TP1/TP2) são tocados na MESMA barra, assume-se que o
  STOP foi atingido primeiro (padrão conservador - não temos dados de tick).
- O Stop Loss é fixo (não usa trailing stop / breakeven após TP1), refletindo
  exatamente os níveis que o app mostra no momento do sinal.
- Se nenhum alvo/stop for tocado em `max_holding_bars` candles, a posição é
  encerrada a mercado (marcação pelo fechamento da última barra observada).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import pandas as pd
import requests

from gorilatrader import API_URLS, CryptoAnalyzer, logger

MAX_HOLDING_BARS_DEFAULT = 200  # ~8 dias em candles de 1h
WARMUP_BARS_DEFAULT = 100  # candles antes de começar a gerar sinais (aquece EMAs/RSI/Ichimoku)


def fetch_extended_klines(symbol: str, exchange: str, total_candles: int, interval: str = "1h") -> pd.DataFrame:
    """Busca um histórico maior que o limite de 1000 candles por request da
    Binance, paginando para trás com o parâmetro `endTime`."""
    url_key = "binance_futures" if exchange == "binance_futures" else "binance_spot"
    base_url = API_URLS[url_key]

    columns = ["open_time", "open", "high", "low", "close", "vol",
               "close_time", "qvol", "trades", "tb_base", "tb_quote", "ignore"]

    batches: List[list] = []
    end_time: Optional[int] = None
    collected = 0
    max_requests = 30  # trava de segurança (30k candles ~ 3.4 anos de 1h)

    for _ in range(max_requests):
        url = f"{base_url}?symbol={symbol}&interval={interval}&limit=1000"
        if end_time is not None:
            url += f"&endTime={end_time}"
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break

        batches.insert(0, batch)
        collected += len(batch)
        end_time = batch[0][0] - 1

        if collected >= total_candles or len(batch) < 1000:
            break
        time.sleep(0.2)  # não martelar a API

    if not batches:
        raise RuntimeError(f"Nenhum dado retornado pela Binance para {symbol}")

    all_rows = [row for batch in batches for row in batch]
    df = pd.DataFrame(all_rows, columns=columns)
    df = df.drop_duplicates(subset="open_time").sort_values("open_time").reset_index(drop=True)
    for col in ["open", "high", "low", "close", "vol"]:
        df[col] = df[col].astype(float)

    if len(df) > total_candles:
        df = df.iloc[-total_candles:].reset_index(drop=True)

    return df


@dataclass
class Trade:
    direction: str          # COMPRA ou VENDA
    signal: str              # sinal exato que abriu a entrada (ex.: FORTE COMPRA)
    entry_idx: int
    entry_time: int
    entry_price: float
    sl: float
    tp1: float
    tp2: float
    exit_idx: int = -1
    exit_time: int = -1
    exit_price: float = 0.0
    outcome: str = ""        # STOP, STOP_AFTER_TP1, TP1, TP1_TIMEOUT, TP2, TIMEOUT
    r_multiple: float = 0.0
    pct_return: float = 0.0
    bars_held: int = 0

    def resolve(self, exit_idx: int, exit_price: float, outcome: str, df: pd.DataFrame):
        self.exit_idx = exit_idx
        self.exit_time = int(df["open_time"].iloc[exit_idx])
        self.exit_price = exit_price
        self.outcome = outcome
        self.bars_held = exit_idx - self.entry_idx

        risk = abs(self.entry_price - self.sl) or 1e-9
        if self.direction == "COMPRA":
            self.r_multiple = (self.exit_price - self.entry_price) / risk
            self.pct_return = (self.exit_price / self.entry_price - 1) * 100
        else:
            self.r_multiple = (self.entry_price - self.exit_price) / risk
            self.pct_return = (self.entry_price / self.exit_price - 1) * 100


def _resolve_trade(df: pd.DataFrame, trade: Trade, max_holding_bars: int) -> None:
    n = len(df)
    end_idx = min(trade.entry_idx + max_holding_bars, n - 1)
    reached_tp1 = False

    for j in range(trade.entry_idx + 1, end_idx + 1):
        bar_high = float(df["high"].iloc[j])
        bar_low = float(df["low"].iloc[j])

        if trade.direction == "COMPRA":
            hit_sl = bar_low <= trade.sl
            hit_tp1 = bar_high >= trade.tp1
            hit_tp2 = bar_high >= trade.tp2
        else:
            hit_sl = bar_high >= trade.sl
            hit_tp1 = bar_low <= trade.tp1
            hit_tp2 = bar_low <= trade.tp2

        if hit_sl:
            outcome = "STOP_AFTER_TP1" if reached_tp1 else "STOP"
            trade.resolve(j, trade.sl, outcome, df)
            return
        if hit_tp2:
            trade.resolve(j, trade.tp2, "TP2", df)
            return
        if hit_tp1:
            reached_tp1 = True

    # esgotou max_holding_bars sem tocar STOP nem TP2 - fecha a mercado
    outcome = "TP1_TIMEOUT" if reached_tp1 else "TIMEOUT"
    trade.resolve(end_idx, float(df["close"].iloc[end_idx]), outcome, df)


def simulate(
    key: str,
    config: dict,
    df: pd.DataFrame,
    weights: Optional[dict] = None,
    warmup: int = WARMUP_BARS_DEFAULT,
    max_holding_bars: int = MAX_HOLDING_BARS_DEFAULT,
) -> List[Trade]:
    """Percorre o histórico barra a barra gerando sinais sem look-ahead
    (cada sinal só vê candles até aquele ponto) e simula a entrada/saída de
    UMA posição por vez seguindo a mesma regra anti-spam do dashboard.

    Depois que uma entrada é aberta em `i` e resolvida em `exit_idx`, o
    cursor pula direto para `exit_idx + 1` - sem isso, o loop continuaria
    avaliando sinais em i+1, i+2... e abriria novas entradas sobrepostas
    "no passado" (antes da posição anterior sequer ter fechado em tempo
    simulado), o que não faz sentido para uma conta com uma posição por vez.
    """
    trades: List[Trade] = []
    last_signal: Optional[str] = None
    n = len(df)
    i = warmup

    while i < n:
        window = df.iloc[: i + 1]
        item = CryptoAnalyzer.analyze_dataframe(key, config, window, weights)
        if item is None:
            i += 1
            continue

        current_signal = item.signal
        is_fresh_buy = current_signal in ("COMPRA", "FORTE COMPRA") and last_signal not in ("COMPRA", "FORTE COMPRA")
        is_fresh_sell = current_signal in ("VENDA", "FORTE VENDA") and last_signal not in ("VENDA", "FORTE VENDA")

        if is_fresh_buy or is_fresh_sell:
            trade = Trade(
                direction="COMPRA" if is_fresh_buy else "VENDA",
                signal=current_signal,
                entry_idx=i,
                entry_time=int(df["open_time"].iloc[i]),
                entry_price=item.price,
                sl=item.stop_loss,
                tp1=item.take_profit_1,
                tp2=item.take_profit_2,
            )
            _resolve_trade(df, trade, max_holding_bars)
            trades.append(trade)
            i = trade.exit_idx + 1
            last_signal = None  # ficamos fora do mercado durante a resolução - recomeça do zero
            continue

        last_signal = current_signal
        i += 1

    return trades


WIN_OUTCOMES = {"TP1", "TP1_TIMEOUT", "TP2"}
LOSS_OUTCOMES = {"STOP", "STOP_AFTER_TP1"}


def summarize(trades: List[Trade]) -> Dict[str, dict]:
    groups: Dict[str, List[Trade]] = {"TODOS": trades, "COMPRA": [], "VENDA": []}
    for t in trades:
        groups[t.direction].append(t)

    summary = {}
    for name, ts in groups.items():
        if not ts:
            summary[name] = {"trades": 0}
            continue
        wins = [t for t in ts if t.outcome in WIN_OUTCOMES]
        losses = [t for t in ts if t.outcome in LOSS_OUTCOMES]
        by_outcome: Dict[str, int] = {}
        for t in ts:
            by_outcome[t.outcome] = by_outcome.get(t.outcome, 0) + 1

        summary[name] = {
            "trades": len(ts),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": len(wins) / len(ts) * 100,
            "avg_r": sum(t.r_multiple for t in ts) / len(ts),
            "avg_pct": sum(t.pct_return for t in ts) / len(ts),
            "total_r": sum(t.r_multiple for t in ts),
            "avg_bars_held": sum(t.bars_held for t in ts) / len(ts),
            "by_outcome": by_outcome,
        }
    return summary


def run_backtest(key: str, config: dict, days: int = 60, weights: Optional[dict] = None):
    warmup = WARMUP_BARS_DEFAULT
    total_candles = warmup + days * 24 + MAX_HOLDING_BARS_DEFAULT
    logger.info("Backtest %s: buscando %d candles de histórico...", key, total_candles)

    df = fetch_extended_klines(config["symbol"], config["exchange"], total_candles)
    if len(df) < warmup + 50:
        raise RuntimeError(f"Histórico insuficiente retornado ({len(df)} candles) para rodar o backtest")

    trades = simulate(key, config, df, weights=weights, warmup=warmup)
    summary = summarize(trades)
    return trades, summary


def print_backtest_report(console, key: str, config: dict, trades: List[Trade], summary: Dict[str, dict]):
    from datetime import datetime

    from rich import box
    from rich.panel import Panel
    from rich.table import Table

    dec = config["decimals"]

    def fmt_price(p: float) -> str:
        if dec >= 6:
            return f"${p:.8f}"
        if dec == 3:
            return f"${p:.3f}"
        return f"${p:,.2f}"

    header = Table(box=box.SIMPLE, show_header=False, expand=True)
    header.add_column(style="bold cyan", width=20)
    header.add_column()
    for name in ("TODOS", "COMPRA", "VENDA"):
        s = summary.get(name, {"trades": 0})
        if s["trades"] == 0:
            header.add_row(name, "[dim]nenhuma entrada[/dim]")
            continue
        outcomes = " · ".join(f"{k}: {v}" for k, v in s["by_outcome"].items())
        header.add_row(
            name,
            f"[bold]{s['trades']}[/bold] entradas · taxa de acerto [bold]{s['win_rate']:.1f}%[/bold] "
            f"({s['wins']}W / {s['losses']}L) · R médio [bold]{s['avg_r']:+.2f}[/bold] · "
            f"soma de R [bold]{s['total_r']:+.2f}[/bold] · retorno médio [bold]{s['avg_pct']:+.2f}%[/bold] "
            f"· {s['avg_bars_held']:.0f}h em média\n[dim]{outcomes}[/dim]",
        )
    console.print(Panel(header, title=f"[bold]📊 Backtest {key} - Resumo[/bold]", border_style="cyan"))

    if not trades:
        console.print("[yellow]Nenhuma entrada foi gerada no período - tente aumentar --backtest-days.[/yellow]")
        return

    table = Table(box=box.ROUNDED, expand=True, header_style="bold bright_white on grey23")
    table.add_column("Entrada", width=17)
    table.add_column("Sinal", width=15)
    table.add_column("Preço Entrada", justify="right", width=14)
    table.add_column("Saída", width=17)
    table.add_column("Resultado", width=15)
    table.add_column("Preço Saída", justify="right", width=14)
    table.add_column("R", justify="right", width=7)
    table.add_column("Retorno", justify="right", width=9)

    win_color, loss_color = "green", "red"
    for t in trades[-30:]:  # só as últimas 30 no terminal para não poluir
        outcome_color = win_color if t.outcome in WIN_OUTCOMES else (loss_color if t.outcome in LOSS_OUTCOMES else "yellow")
        table.add_row(
            datetime.fromtimestamp(t.entry_time / 1000).strftime("%d/%m %H:%M"),
            f"[{'green' if t.direction == 'COMPRA' else 'red'}]{t.signal}[/]",
            fmt_price(t.entry_price),
            datetime.fromtimestamp(t.exit_time / 1000).strftime("%d/%m %H:%M"),
            f"[{outcome_color}]{t.outcome}[/{outcome_color}]",
            fmt_price(t.exit_price),
            f"[{outcome_color}]{t.r_multiple:+.2f}[/{outcome_color}]",
            f"[{outcome_color}]{t.pct_return:+.2f}%[/{outcome_color}]",
        )

    title = f"[bold]Últimas {min(30, len(trades))} entradas (de {len(trades)} no total)[/bold]"
    console.print(Panel(table, title=title, border_style="blue"))
