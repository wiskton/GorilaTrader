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

---

## 🚧 Próximos Passos

### Curto prazo
- [ ] Suíte de testes automatizados para o motor de scoring (`CryptoAnalyzer`) — cada fator da matriz coberto por um teste unitário
- [ ] Arquivo de configuração (YAML/JSON) para escolher os ativos monitorados sem editar o código
- [ ] Pesos dos indicadores configuráveis (permitir ajustar a matriz de confluência sem alterar o código-fonte)
- [ ] Persistir o histórico de alertas entre sessões (SQLite ou JSON), hoje ele reseta a cada execução

### Médio prazo
- [ ] Modo de backtest: rodar a matriz de decisão contra dados históricos e medir taxa de acerto/retorno por sinal
- [ ] Notificações externas opcionais (Telegram/Discord/webhook) além do apito no terminal
- [ ] Filtro de confirmação multi-timeframe (ex.: viés de 4h/1D para filtrar sinais de 1h contra a tendência maior)
- [ ] Empacotamento via Docker para facilitar execução em servidores/VPS (monitoramento 24/7 headless)

### Longo prazo / explorações
- [ ] Dashboard web opcional (mesma engine, visualização no navegador)
- [ ] Suporte a mais exchanges como fonte de dados (OKX, Kraken)
- [ ] Modo "papel" (paper trading) simulando execução das entradas sugeridas para acompanhar performance real da estratégia

---

## Fora de escopo (por ora)

- Execução automática de ordens (o projeto é um monitor/assistente de decisão, não um bot de execução)
- Suporte a Windows/macOS nativo para os alertas sonoros (hoje depende de `aplay`/`paplay`/`spd-say` do Linux)
