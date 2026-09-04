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
- [x] `run-web.sh` + atalho **GorilaTrader Web** no menu de aplicativos (sobe o servidor e abre o navegador automaticamente)
- [x] `install-desktop.sh` + templates em `desktop/` - instala os atalhos (terminal e web) resolvendo os caminhos automaticamente, funciona em qualquer máquina/usuário sem editar nada à mão

## ✅ v1.3 — Testes Automatizados e WebSocket (entregue)

- [x] Suíte de testes automatizados (`tests/`, pytest) para o motor de scoring - os 15 fatores da matriz de confluência testados isoladamente (score exato + texto da razão) via cenários sintéticos calibrados, mais testes de integração (classificação de sinal, direção de SL/TP, regressão da EMA200), config, Telegram e persistência do histórico - 57 testes no total
- [x] `CryptoAnalyzer.analyze_dataframe` aceita DataFrame direto (sem rede), o que tornou os testes possíveis
- [x] `requirements-dev.txt` + `pytest.ini`
- [x] Dashboard web trocou o polling (20s) por **WebSocket** (`/ws/{ativo}`) - o servidor empurra gráfico + snapshot periodicamente, com reconexão automática no frontend se a conexão cair
- [x] `--serve` agora roda um monitor de alertas em segundo plano (mesma lógica de `check_and_alert`/`check_extreme_alerts` do terminal) - antes, alertas (apito + Telegram) só disparavam com o dashboard do terminal aberto; agora disparam também usando só o dashboard web
- [x] Status de posição no canal de Bollinger (`bollinger_status`: Dentro do Canal / Rompeu Superior / Rompeu Inferior) - nova coluna no terminal, linha no relatório detalhado, e campo na barra lateral do dashboard web

---

## ✅ v1.4 — Docker (entregue)

- [x] `Dockerfile` + `docker-compose.yml` + `.dockerignore` - imagem roda o dashboard web (`--serve --host 0.0.0.0`), testada com build e run reais
- [x] `GORILATRADER_DATA_DIR` (env var) redireciona `config.json`/`alerts_history.json`/`gorilatrader.log` para um diretório configurável (`/data` na imagem) - permite montar um volume e persistir estado entre restarts/rebuilds, sem editar código
- [x] Credenciais do Telegram via `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` no ambiente do container (sem precisar de `config.json` montado)

---

## ✅ v1.5 — Backtest (entregue)

- [x] `backtest.py`: motor de backtest sem look-ahead - cada sinal só enxerga candles até aquele ponto (`df.iloc[:i+1]`), reaproveitando `CryptoAnalyzer.analyze_dataframe` direto
- [x] `fetch_extended_klines`: paginação sobre o limite de 1000 candles/request da Binance, para períodos maiores (`--backtest-days`)
- [x] Resolução de trade contra STOP/TP1/TP2 com regra conservadora de desempate (STOP primeiro se ambos tocam na mesma barra) e timeout configurável
- [x] `python3 gorilatrader.py --backtest ATIVO [--backtest-days N]` com relatório de taxa de acerto, R médio e retorno % por direção (COMPRA/VENDA)
- [x] 12 testes cobrindo resolução de trade (SL/TP1/TP2/timeout/desempate) e paginação do histórico - um deles pegou um bug real de sobreposição de trades antes de ir para o ar (o loop principal nunca pulava para depois da resolução da entrada anterior)

## ✅ v1.6 — Confirmação Multi-Timeframe (entregue)

- [x] Novo fator na matriz: viés do candle de **4h** (preço vs. EMA50 desse timeframe) comparado com o viés imediato de 1h (preço vs. EMA21) - reforça o score quando concordam, penaliza quando o sinal de 1h vai contra a tendência maior
- [x] `CryptoAnalyzer.fetch_mtf_klines` com cache de 15 min - o candle de 4h só fecha a cada 4h, então não faz sentido rebuscar a cada ciclo de 1h/20s
- [x] `analyze_dataframe` aceita `mtf_df` opcional (mantém a função pura/testável sem rede); `analyze_asset` busca e injeta automaticamente
- [x] Exibido no relatório detalhado (`--once`) e na barra lateral do dashboard web; novo peso `mtf_confirmation` configurável em `config.json`
- [x] 7 testes cobrindo alinhamento/divergência em ambas direções, ausência de dado de 4h, histórico insuficiente e cache

---

## 🚧 Próximos Passos

### Médio prazo
- [ ] Sombreamento visual entre as bandas (Bollinger/Donchian/Nuvem de Ichimoku) no gráfico web, hoje são só linhas

### Longo prazo / explorações
- [ ] Suporte a mais exchanges como fonte de dados (OKX, Kraken)
- [ ] Modo "papel" (paper trading) simulando execução das entradas sugeridas para acompanhar performance real da estratégia
- [ ] Autenticação simples no dashboard web para uso seguro com `--host 0.0.0.0` fora da rede local

---

## Fora de escopo (por ora)

- Execução automática de ordens (o projeto é um monitor/assistente de decisão, não um bot de execução)
- Suporte a Windows/macOS nativo para os alertas sonoros (hoje depende de `aplay`/`paplay`/`spd-say` do Linux)
