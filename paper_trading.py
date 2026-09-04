"""
GorilaTrader - Modo Papel (paper trading).

Diferente do backtest.py (que roda sobre histórico já fechado, sem espera),
o modo papel acompanha os sinais AO VIVO: quando o sinal de um ativo muda
para COMPRA/VENDA (mesma regra anti-spam de check_and_alert), abre uma
posição simulada no preço do momento com o SL/TP1/TP2 exibidos naquele
instante. A cada ciclo de atualização (terminal ou --serve), o preço mais
recente é comparado aos níveis para decidir se a posição fecha: STOP, TP2
ou timeout por tempo (marca TP1 como atingido no caminho, sem fechar - só
fecha no TP2, no STOP ou no timeout, igual ao motor de backtest). Nenhuma
ordem real é enviada a lugar nenhum - é só contabilidade para medir a
performance real da estratégia com o tempo.

Limitação conhecida: como a checagem só acontece a cada ciclo (ex.: a cada
20-60s), um pavio (wick) muito rápido entre duas checagens pode não ser
capturado - isso é amostragem por preço "de fechamento" periódico, não dado
de tick real.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Dict, List, Optional

from gorilatrader import logger

if TYPE_CHECKING:
    from gorilatrader import MarketData

MAX_CLOSED_TRADES = 300
DEFAULT_MAX_HOLDING_HOURS = 200  # mesma janela do backtest (200 candles de 1h)

# Mesmos códigos de resultado do motor de backtest (backtest.py) - mantém os
# dois comparáveis lado a lado.
WIN_OUTCOMES = {"TP1", "TP1_TIMEOUT", "TP2"}
LOSS_OUTCOMES = {"STOP", "STOP_AFTER_TP1"}


@dataclass
class PaperTrade:
    asset_key: str
    direction: str  # COMPRA ou VENDA
    signal: str  # sinal exato que abriu a entrada (ex.: FORTE COMPRA)
    entry_time: str  # ISO 8601
    entry_price: float
    sl: float
    tp1: float
    tp2: float
    reached_tp1: bool = False
    exit_time: Optional[str] = None
    exit_price: Optional[float] = None
    outcome: Optional[str] = None  # STOP, STOP_AFTER_TP1, TP1_TIMEOUT, TP2, TIMEOUT
    r_multiple: Optional[float] = None
    pct_return: Optional[float] = None

    def close(self, exit_price: float, outcome: str) -> None:
        self.exit_time = datetime.now().isoformat(timespec="seconds")
        self.exit_price = exit_price
        self.outcome = outcome

        risk = abs(self.entry_price - self.sl) or 1e-9
        if self.direction == "COMPRA":
            self.r_multiple = (exit_price - self.entry_price) / risk
            self.pct_return = (exit_price / self.entry_price - 1) * 100
        else:
            self.r_multiple = (self.entry_price - exit_price) / risk
            self.pct_return = (self.entry_price / exit_price - 1) * 100


class PaperTradingEngine:
    """Uma posição simulada por vez por ativo, persistida em disco entre
    reinícios (mesmo padrão de alerts_history.json em gorilatrader.py)."""

    def __init__(self, path: str, max_holding_hours: int = DEFAULT_MAX_HOLDING_HOURS):
        self.path = path
        self.max_holding_hours = max_holding_hours
        self.open_trades: Dict[str, PaperTrade] = {}
        self.closed_trades: List[PaperTrade] = []
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.open_trades = {k: PaperTrade(**v) for k, v in data.get("open", {}).items()}
            self.closed_trades = [PaperTrade(**v) for v in data.get("closed", [])]
        except Exception:
            logger.exception("Falha ao carregar %s, começando o modo papel do zero", self.path)
            self.open_trades, self.closed_trades = {}, []

    def _save(self) -> None:
        try:
            data = {
                "open": {k: asdict(v) for k, v in self.open_trades.items()},
                "closed": [asdict(t) for t in self.closed_trades[-MAX_CLOSED_TRADES:]],
            }
            tmp_path = f"{self.path}.tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self.path)
        except Exception:
            logger.warning("Falha ao salvar %s", self.path, exc_info=True)

    def maybe_open(self, item: "MarketData", is_fresh_buy: bool, is_fresh_sell: bool) -> Optional[PaperTrade]:
        """Abre uma posição simulada só na transição de sinal (mesma regra
        anti-spam de check_and_alert) e só se não houver uma já aberta para
        o ativo."""
        if not (is_fresh_buy or is_fresh_sell):
            return None
        if item.asset_key in self.open_trades:
            return None

        trade = PaperTrade(
            asset_key=item.asset_key,
            direction="COMPRA" if is_fresh_buy else "VENDA",
            signal=item.signal,
            entry_time=datetime.now().isoformat(timespec="seconds"),
            entry_price=item.price,
            sl=item.stop_loss,
            tp1=item.take_profit_1,
            tp2=item.take_profit_2,
        )
        self.open_trades[item.asset_key] = trade
        self._save()
        logger.info("Modo papel: abriu %s %s @ %.8f", trade.direction, item.asset_key, item.price)
        return trade

    def update(self, item: "MarketData") -> Optional[PaperTrade]:
        """Verifica a posição aberta (se houver) do ativo contra o preço
        atual: fecha em STOP, TP2 ou timeout; marca TP1 no caminho."""
        trade = self.open_trades.get(item.asset_key)
        if trade is None:
            return None

        price = item.price
        if trade.direction == "COMPRA":
            hit_sl = price <= trade.sl
            hit_tp1 = price >= trade.tp1
            hit_tp2 = price >= trade.tp2
        else:
            hit_sl = price >= trade.sl
            hit_tp1 = price <= trade.tp1
            hit_tp2 = price <= trade.tp2

        if hit_sl:
            return self._close(trade, trade.sl, "STOP_AFTER_TP1" if trade.reached_tp1 else "STOP")
        if hit_tp2:
            return self._close(trade, trade.tp2, "TP2")
        if hit_tp1 and not trade.reached_tp1:
            trade.reached_tp1 = True
            self._save()

        elapsed_hours = (datetime.now() - datetime.fromisoformat(trade.entry_time)).total_seconds() / 3600
        if elapsed_hours >= self.max_holding_hours:
            return self._close(trade, price, "TP1_TIMEOUT" if trade.reached_tp1 else "TIMEOUT")

        return None

    def _close(self, trade: PaperTrade, exit_price: float, outcome: str) -> PaperTrade:
        trade.close(exit_price, outcome)
        del self.open_trades[trade.asset_key]
        self.closed_trades.append(trade)
        self.closed_trades = self.closed_trades[-MAX_CLOSED_TRADES:]
        self._save()
        logger.info(
            "Modo papel: fechou %s %s @ %.8f (%s, R=%.2f)",
            trade.direction, trade.asset_key, exit_price, outcome, trade.r_multiple,
        )
        return trade

    def summary(self) -> Dict[str, dict]:
        groups: Dict[str, List[PaperTrade]] = {"TODOS": self.closed_trades, "COMPRA": [], "VENDA": []}
        for t in self.closed_trades:
            groups[t.direction].append(t)

        out: Dict[str, dict] = {}
        for name, ts in groups.items():
            if not ts:
                out[name] = {"trades": 0}
                continue
            wins = [t for t in ts if t.outcome in WIN_OUTCOMES]
            losses = [t for t in ts if t.outcome in LOSS_OUTCOMES]
            by_outcome: Dict[str, int] = {}
            for t in ts:
                by_outcome[t.outcome] = by_outcome.get(t.outcome, 0) + 1
            out[name] = {
                "trades": len(ts),
                "wins": len(wins),
                "losses": len(losses),
                "win_rate": len(wins) / len(ts) * 100,
                "avg_r": sum(t.r_multiple for t in ts) / len(ts),
                "total_r": sum(t.r_multiple for t in ts),
                "avg_pct": sum(t.pct_return for t in ts) / len(ts),
                "by_outcome": by_outcome,
            }
        return out


def _format_price(price: float, decimals: int) -> str:
    if decimals >= 6:
        return f"${price:.8f}"
    if decimals == 3:
        return f"${price:.3f}"
    return f"${price:,.2f}"


def print_paper_trading_report(console, assets: dict, engine: PaperTradingEngine) -> None:
    """Relatório no terminal (Rich) da performance acumulada do modo papel -
    mesmo estilo visual do relatório de --backtest."""
    from rich import box
    from rich.panel import Panel
    from rich.table import Table

    summary = engine.summary()
    header = Table(box=box.SIMPLE, show_header=False, expand=True)
    header.add_column(style="bold cyan", width=20)
    header.add_column()
    for name in ("TODOS", "COMPRA", "VENDA"):
        s = summary.get(name, {"trades": 0})
        if s["trades"] == 0:
            header.add_row(name, "[dim]nenhuma entrada fechada ainda[/dim]")
            continue
        outcomes = " · ".join(f"{k}: {v}" for k, v in s["by_outcome"].items())
        header.add_row(
            name,
            f"[bold]{s['trades']}[/bold] entradas · taxa de acerto [bold]{s['win_rate']:.1f}%[/bold] "
            f"({s['wins']}W / {s['losses']}L) · R médio [bold]{s['avg_r']:+.2f}[/bold] · "
            f"soma de R [bold]{s['total_r']:+.2f}[/bold] · retorno médio [bold]{s['avg_pct']:+.2f}%[/bold]\n"
            f"[dim]{outcomes}[/dim]",
        )
    console.print(Panel(header, title="[bold]📝 Modo Papel - Resumo[/bold]", border_style="cyan"))

    if engine.open_trades:
        open_table = Table(box=box.ROUNDED, expand=True, header_style="bold bright_white on grey23")
        open_table.add_column("Ativo", width=10)
        open_table.add_column("Direção", width=10)
        open_table.add_column("Entrada", width=19)
        open_table.add_column("Preço Entrada", justify="right", width=14)
        open_table.add_column("SL", justify="right", width=14)
        open_table.add_column("TP1", justify="right", width=14)
        open_table.add_column("TP2", justify="right", width=14)
        open_table.add_column("TP1 atingido?", width=13)
        for key, t in engine.open_trades.items():
            cfg = assets.get(key, {})
            dec = cfg.get("decimals", 2)
            open_table.add_row(
                f"{cfg.get('icon', '')} {key}",
                f"[{'green' if t.direction == 'COMPRA' else 'red'}]{t.direction}[/]",
                t.entry_time,
                _format_price(t.entry_price, dec),
                _format_price(t.sl, dec),
                _format_price(t.tp1, dec),
                _format_price(t.tp2, dec),
                "✅" if t.reached_tp1 else "—",
            )
        console.print(Panel(open_table, title="[bold]Posições abertas no modo papel[/bold]", border_style="yellow"))
    else:
        console.print("[dim]Nenhuma posição aberta no modo papel no momento.[/dim]")

    if not engine.closed_trades:
        console.print(
            "[yellow]Nenhuma entrada fechada ainda - deixe o GorilaTrader rodando "
            "(terminal ou --serve) para acumular histórico.[/yellow]"
        )
        return

    table = Table(box=box.ROUNDED, expand=True, header_style="bold bright_white on grey23")
    table.add_column("Ativo", width=8)
    table.add_column("Entrada", width=19)
    table.add_column("Sinal", width=15)
    table.add_column("Preço Entrada", justify="right", width=14)
    table.add_column("Saída", width=19)
    table.add_column("Resultado", width=15)
    table.add_column("Preço Saída", justify="right", width=14)
    table.add_column("R", justify="right", width=7)
    table.add_column("Retorno", justify="right", width=9)

    for t in engine.closed_trades[-30:]:
        outcome_color = "green" if t.outcome in WIN_OUTCOMES else ("red" if t.outcome in LOSS_OUTCOMES else "yellow")
        cfg = assets.get(t.asset_key, {})
        dec = cfg.get("decimals", 2)
        table.add_row(
            f"{cfg.get('icon', '')} {t.asset_key}",
            t.entry_time,
            f"[{'green' if t.direction == 'COMPRA' else 'red'}]{t.signal}[/]",
            _format_price(t.entry_price, dec),
            t.exit_time or "—",
            f"[{outcome_color}]{t.outcome}[/{outcome_color}]",
            _format_price(t.exit_price, dec) if t.exit_price is not None else "—",
            f"[{outcome_color}]{t.r_multiple:+.2f}[/{outcome_color}]",
            f"[{outcome_color}]{t.pct_return:+.2f}%[/{outcome_color}]",
        )

    title = f"[bold]Últimas {min(30, len(engine.closed_trades))} entradas fechadas (de {len(engine.closed_trades)} no total)[/bold]"
    console.print(Panel(table, title=title, border_style="blue"))
