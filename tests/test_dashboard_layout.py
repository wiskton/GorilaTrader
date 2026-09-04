"""Testes de GorilaTraderTerminal._layout_sizes: o dashboard do terminal foi
originalmente dimensionado (altura fixa) pra exatamente 5 ativos - com
--assets/config.json aceitando qualquer quantidade, o layout precisa crescer
com o número de ativos e se ajustar ao terminal disponível, sem cortar linhas
da tabela silenciosamente."""

from __future__ import annotations

import gorilatrader as g


class FakeConsole:
    def __init__(self, height: int):
        self.size = type("Size", (), {"height": height})()


def _terminal_with_console_height(height: int) -> g.GorilaTraderTerminal:
    terminal = g.GorilaTraderTerminal.__new__(g.GorilaTraderTerminal)
    terminal.console = FakeConsole(height)
    return terminal


def _set_asset_count(monkeypatch, n: int) -> None:
    monkeypatch.setattr(g, "ASSETS", {f"A{i}": {} for i in range(n)})


def test_layout_matches_original_fixed_sizes_for_5_assets(monkeypatch):
    _set_asset_count(monkeypatch, 5)
    terminal = _terminal_with_console_height(50)
    main_size, details_size = terminal._layout_sizes()
    assert (main_size, details_size) == (g.BASE_MAIN_LAYOUT_SIZE, g.BASE_DETAILS_LAYOUT_SIZE)


def test_layout_grows_main_table_with_more_assets_when_terminal_has_room(monkeypatch):
    _set_asset_count(monkeypatch, 20)
    terminal = _terminal_with_console_height(200)
    main_size, details_size = terminal._layout_sizes()
    assert main_size == g.BASE_MAIN_LAYOUT_SIZE + (20 - g.BASE_ASSET_COUNT)
    assert details_size == g.BASE_DETAILS_LAYOUT_SIZE


def test_layout_fits_100_assets_without_clipping_on_a_tall_enough_terminal(monkeypatch):
    _set_asset_count(monkeypatch, 100)
    terminal = _terminal_with_console_height(200)
    main_size, details_size = terminal._layout_sizes()
    assert main_size == g.BASE_MAIN_LAYOUT_SIZE + (100 - g.BASE_ASSET_COUNT)
    assert details_size == g.BASE_DETAILS_LAYOUT_SIZE


def test_layout_shrinks_alert_history_before_shrinking_asset_table(monkeypatch):
    _set_asset_count(monkeypatch, 20)  # pediria main=30, details=9 -> total 39 + 6 (header/footer) = 45
    terminal = _terminal_with_console_height(45)  # cabe exatamente sem sobra
    main_size, details_size = terminal._layout_sizes()
    assert main_size == 30
    assert details_size == g.BASE_DETAILS_LAYOUT_SIZE

    # 3 linhas a menos: dá exatamente pra encolher o histórico até o mínimo (9 -> 6)
    # sem tocar na tabela de ativos.
    terminal_smaller = _terminal_with_console_height(42)
    main_size, details_size = terminal_smaller._layout_sizes()
    assert details_size == g.MIN_DETAILS_LAYOUT_SIZE
    assert main_size == 30

    # mais 1 linha a menos: histórico já está no mínimo, agora a tabela cede.
    terminal_tighter = _terminal_with_console_height(41)
    main_size, details_size = terminal_tighter._layout_sizes()
    assert details_size == g.MIN_DETAILS_LAYOUT_SIZE
    assert main_size == 29


def test_layout_never_shrinks_details_below_minimum(monkeypatch):
    _set_asset_count(monkeypatch, 100)
    terminal = _terminal_with_console_height(50)
    main_size, details_size = terminal._layout_sizes()
    assert details_size == g.MIN_DETAILS_LAYOUT_SIZE
    assert main_size == 50 - 3 - 3 - g.MIN_DETAILS_LAYOUT_SIZE


def test_layout_never_shrinks_main_table_below_minimum_on_tiny_terminal(monkeypatch):
    _set_asset_count(monkeypatch, 100)
    terminal = _terminal_with_console_height(10)
    main_size, details_size = terminal._layout_sizes()
    assert details_size == g.MIN_DETAILS_LAYOUT_SIZE
    assert main_size == g.MIN_MAIN_LAYOUT_SIZE


def test_layout_falls_back_gracefully_when_console_height_unavailable(monkeypatch):
    _set_asset_count(monkeypatch, 5)
    terminal = g.GorilaTraderTerminal.__new__(g.GorilaTraderTerminal)

    class BrokenConsole:
        @property
        def size(self):
            raise RuntimeError("no tty")

    terminal.console = BrokenConsole()
    main_size, details_size = terminal._layout_sizes()
    assert (main_size, details_size) == (g.BASE_MAIN_LAYOUT_SIZE, g.BASE_DETAILS_LAYOUT_SIZE)
