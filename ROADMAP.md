# 🗺️ Roadmap — GorilaTrader

Este documento acompanha o que já foi entregue e o que está planejado para as próximas versões. Sugestões e PRs são bem-vindos.

---

## ✅ v1.0 — Base (entregue)

- [x] Dashboard em tempo real no terminal (Rich) para BTC, ETH, SOL, PEPE e HYPE
- [x] Matriz de confluência: EMAs (9/21/50/200), RSI(14), MACD(12,26,9), Bandas de Bollinger(20,2), ATR(14)
- [x] Gerenciamento de risco automático (Stop Loss + 2 Take Profits via ATR)
- [x] Alertas sonoros sintetizados (apito de compra/venda) com filtro anti-spam
- [x] Locução por voz sintética opcional (`--voice`, via `spd-say`)
- [x] Fallback automático Binance → Bybit em caso de falha de rede
- [x] Busca dos 5 ativos em paralelo (`ThreadPoolExecutor`)
- [x] Logging estruturado (`gorilatrader.log`) para falhas de rede/API
- [x] Indicação visual de erro de conexão vs. carregando no dashboard
- [x] Rompimento de Canal (Donchian 20)
- [x] Fluxo de volume via OBV (confirmação e divergência oculta)
- [x] Ichimoku Kinko Hyo (Tenkan/Kijun/Nuvem + TK Cross)
- [x] Ícone pixel art e atalho no menu de aplicativos (Pop!_OS/COSMIC)

## ✅ v1.1 — Configuração, Alertas Extremos e Telegram (entregue)

- [x] Arquivo de configuração (`config.json` / `config.example.json`) para trocar os ativos monitorados sem editar o código
- [x] Pesos dos indicadores configuráveis (cada fator da matriz de confluência ajustável via `config.json`)
- [x] `CryptoAnalyzer.analyze_dataframe()` separado de `analyze_asset()` - motor de decisão desacoplado da busca de rede (base para os testes automatizados do próximo item)
- [x] Persistência do histórico de alertas entre sessões (`alerts_history.json`, últimos 200 registros)
- [x] Alerta dedicado de **RSI Estourado** (>80 sobrecompra / <20 sobrevenda), independente do score
- [x] Alerta dedicado de **Rompimento Forte de Bollinger** (>= 2.5 desvios-padrão da média de 20 períodos)
- [x] Notificações no **Telegram** para todos os avisos (sinais + RSI estourado + Bollinger forte), com `--test-telegram` e `--no-telegram`

## ✅ v1.2 — Dashboard Web estilo TradingView (entregue)

- [x] Backend `webserver.py` (FastAPI) reaproveitando `CryptoAnalyzer` - endpoints `/api/assets`, `/api/chart/{key}` (candles + todas as séries de indicadores) e `/api/snapshot/{key}` (sinal/score/SL-TP/motivos)
- [x] Frontend `web/index.html` com [Lightweight Charts](https://github.com/tradingview/lightweight-charts) (open-source da própria TradingView) - candles + volume, sem build step
- [x] Overlays configuráveis via checkbox: EMA9/21/50/200, Bandas de Bollinger, Canal Donchian, Nuvem de Ichimoku (projetada 26 períodos à frente, como no Ichimoku tradicional)
- [x] Painel de oscilador sincronizado (RSI com linhas de referência 20/30/70/80, MACD histograma+linhas, ou OBV), selecionável por dropdown
- [x] Barra lateral com sinal atual, score, Stop Loss/Take Profits e fatores técnicos, atualizando junto com o gráfico
- [x] `python3 gorilatrader.py --serve [--port 8000] [--host 0.0.0.0]`, dependências opcionais (`fastapi`, `uvicorn`) só exigidas ao usar `--serve`

---

## 🚧 Próximos Passos

### Curto prazo
- [ ] Suíte de testes automatizados para o motor de scoring (`CryptoAnalyzer.analyze_dataframe`) — cada fator da matriz coberto por um teste unitário com DataFrames sintéticos
- [ ] Notificações Discord/webhook genérico, além do Telegram já implementado
- [ ] Trocar o polling do dashboard web (20s) por WebSocket para atualização push em tempo real

### Médio prazo
- [ ] Modo de backtest: rodar a matriz de decisão contra dados históricos e medir taxa de acerto/retorno por sinal
- [ ] Filtro de confirmação multi-timeframe (ex.: viés de 4h/1D para filtrar sinais de 1h contra a tendência maior)
- [ ] Empacotamento via Docker para facilitar execução em servidores/VPS (monitoramento 24/7 headless)
- [ ] Sombreamento visual entre as bandas (Bollinger/Donchian/Nuvem de Ichimoku) no gráfico web, hoje são só linhas

### Longo prazo / explorações
- [ ] Suporte a mais exchanges como fonte de dados (OKX, Kraken)
- [ ] Modo "papel" (paper trading) simulando execução das entradas sugeridas para acompanhar performance real da estratégia
- [ ] Autenticação simples no dashboard web para uso seguro com `--host 0.0.0.0` fora da rede local

---

## Fora de escopo (por ora)

- Execução automática de ordens (o projeto é um monitor/assistente de decisão, não um bot de execução)
- Suporte a Windows/macOS nativo para os alertas sonoros (hoje depende de `aplay`/`paplay`/`spd-say` do Linux)
