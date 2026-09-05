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

## ✅ v1.7 — Sombreamento das Bandas no Gráfico Web (entregue)

- [x] `BandFillPrimitive` em `web/index.html`: primitiva de desenho customizada (API oficial de plugins do Lightweight Charts v4.1+, confirmada presente na versão exata pinada) que preenche a área entre duas linhas (upper/lower) por timestamp - o Lightweight Charts não tem série nativa pra isso (baseline só preenche até um valor fixo)
- [x] Aplicado às Bandas de Bollinger, Canal Donchian e Nuvem de Ichimoku (senkou A/B), respeitando os checkboxes de cada overlay e redesenhando ao trocar de ativo ou alternar visibilidade
- [x] ⚠️ Não verificado visualmente num navegador real nesta sessão (sem acesso ao Chrome) - a API usada foi confirmada existente na lib exata carregada, mas vale conferir a aparência final

## ✅ v1.8 — Mais Exchanges e Modo Papel (entregue)

- [x] Suporte a **OKX** e **Kraken** como fonte de dados por ativo (`exchange: "okx"` ou `"kraken"` em `config.json`), além de Binance spot/futures (com fallback pra Bybit) - cada exchange tem seu próprio formato de símbolo (`BTC-USDT` na OKX, `XBTUSDT` na Kraken) e de intervalo (`1H`/`4H` na OKX, minutos na Kraken), documentado em `config.example.json`
- [x] `CryptoAnalyzer.fetch_klines` roteia por `exchange` em vez de assumir Binance+fallback pra tudo - OKX/Kraken retornam `None` e logam o erro em vez de cair num fallback que não faz sentido pra elas
- [x] **Modo Papel** (`paper_trading.py`): acompanha os sinais ao vivo (terminal ou `--serve`) e simula a execução - abre uma posição no preço do momento quando o sinal muda pra COMPRA/VENDA (mesma regra anti-spam dos apitos), fecha em STOP/TP2/timeout comparando com o preço a cada ciclo, sem enviar ordem real a lugar nenhum
- [x] Estado persistido em `paper_trades.json` (mesmo padrão de `alerts_history.json`), sobrevive a reinícios e ao volume do Docker
- [x] `--paper-report` (relatório de performance: taxa de acerto, R médio, retorno % por direção), `--no-paper-trading` (desativa na sessão do terminal) e `--reset-paper-trading` (zera o histórico)
- [x] Nova seção `paper_trading` em `config.json` (`enabled`, `max_holding_hours`) - liga/desliga e ajusta o timeout tanto no terminal quanto no `--serve`
- [x] 21 novos testes (motor de fetch das duas exchanges novas, engine do modo papel: abertura na transição de sinal, uma posição por ativo, resolução STOP/TP2/TP1-parcial/timeout em ambas direções, persistência, resumo) - 97 testes no total

## ✅ v1.9 — Escolha de Ativos na Hora (entregue)

- [x] Prompt interativo ao abrir o terminal (`Prompt.ask` do Rich) perguntando quais criptos acompanhar - Enter mantém os ativos do `config.json`/padrões; só aparece em terminal interativo (`sys.stdin.isatty()`), nunca trava `--serve`, `--backtest`, `--paper-report`, `--reset-paper-trading`, `--test-telegram` ou `--test-sound` esperando input
- [x] Flag `--assets BTC,ETH,DOGE` equivalente por linha de comando, pulando o prompt - funciona em qualquer modo (inclusive `--serve`/`--backtest`), útil pra scripts/atalhos
- [x] `resolve_assets_from_tickers`: ticker já conhecido (nos ativos atuais ou nos padrões embutidos) reaproveita nome/ícone/exchange/decimais já curados; ticker novo assume par `TICKERUSDT` na Binance spot e detecta as casas decimais de exibição pelo preço atual (heurística por ordem de grandeza, mesmo espírito de BTC vs. PEPE) - se o par não existir, avisa e segue mesmo assim
- [x] 🐛 Corrigido de quebra: `format_price`/`fmt_price`/`_format_price` (terminal, backtest, modo papel) e `fmtPrice` (dashboard web) só tratavam 2, 3 ou 8 casas decimais como casos especiais - qualquer outro valor (ex.: as 4 ou 6 casas que a detecção automática podia gerar) caía sempre em 2 casas fixas, arredondando o preço de ativos de valor baixo pra `$0.00`. Generalizado pra usar as casas decimais recebidas diretamente.
- [x] 9 novos testes (heurística de casas decimais, reaproveitamento de ativo conhecido, montagem automática de ativo novo, fallback e aviso quando o símbolo não existe) - 106 testes no total

## ✅ v2.0 — Dashboard Web Expandido e Terminal sem Limite de Ativos (entregue)

- [x] **Modo Papel no dashboard web**: botão "📝 Modo Papel" no cabeçalho abre um painel com a mesma performance do `--paper-report` do terminal (resumo por direção, posições abertas, últimas entradas fechadas) - novo endpoint `/api/paper-trading`, lendo do mesmo motor que já roda em segundo plano no `--serve`
- [x] **Favoritos na barra lateral**: caixa pra digitar qualquer ticker (ex.: `DOGE`) e adicionar à lista - resolvido sob demanda (`/api/resolve/{ticker}`, mesmo mecanismo do `--assets` do terminal) mesmo que não esteja em `config.json`; clique num favorito troca o gráfico pra ele. Lista salva no `localStorage` do navegador (por dispositivo), sobrevive a reinícios do servidor sem precisar editar nada
- [x] `/api/chart/{key}`, `/api/snapshot/{key}` e `/ws/{key}` agora resolvem qualquer ticker sob demanda (não só os de `ASSETS`) via `resolve_asset_config`, com cache em memória pra não repetir a detecção de decimais a cada atualização do WebSocket
- [x] 🐛 Corrigido: um ticker inventado no campo de favoritos nunca causava erro (a resolução do `--assets` do terminal sempre "desiste bonito" caindo pra decimais=2, o que faz sentido lá) - no navegador isso criaria um favorito "fantasma" que nunca carrega dado; `resolve_asset_config` agora valida de verdade e devolve 404 pra ticker que não existe
- [x] **Terminal sem limite de 5 ativos**: o layout do dashboard (Rich `Layout`) tinha altura fixa (calibrada originalmente pra exatamente 5 linhas) - com `--assets`/`config.json` aceitando qualquer quantidade, ativos além do 5º simplesmente eram cortados da tela sem aviso. A tabela agora cresce 1 linha por ativo extra e se ajusta à altura real do terminal (encolhe primeiro o histórico de alertas, só depois a própria tabela) - dá pra acompanhar dezenas ou centenas de criptos de uma vez, limitado só pelo tamanho real da janela do terminal
- [x] Teto de 20 threads simultâneas na busca (`MAX_FETCH_WORKERS`) mesmo com uma lista grande de ativos - evita bater a exchange com uma rajada de requisições de uma vez e levar rate limit (429)
- [x] 19 novos testes (dimensionamento do layout do terminal em vários cenários de altura/quantidade de ativos, resolução de ativos no backend do dashboard web incluindo cache e fallback 404, endpoint de performance do modo papel) - 125 testes no total

## ✅ v2.1 — Telegram Seletivo e Aviso de Conclusão de Operação (entregue)

- [x] 🐛 **Bug real corrigido**: o Telegram usa `parse_mode: "HTML"`, e alguns fatores técnicos têm "<" cru no texto (ex.: "Alinhamento clássico de baixa (Preço < EMA9 < EMA21 < EMA50)") - o Telegram interpretava isso como início de tag e rejeitava a mensagem inteira ("can't parse entities"), então sinais reais nunca chegavam ao Telegram (só falhavam silenciosamente, com um WARNING no log) mesmo com as credenciais certas e o `--test-telegram` funcionando normalmente (mensagem de teste não tem "<"). Todo texto dinâmico da mensagem agora é escapado (`html.escape`) antes de entrar no template - as tags fixas do próprio template (`<b>...</b>`) continuam intactas
- [x] **Telegram seletivo pra sinais de entrada**: só dispara para COMPRA/VENDA quando o sinal é **FORTE** (mais confiança) - sinal fraco continua tocando o apito e entrando no histórico do dashboard normalmente, só não vai pro Telegram. Alertas de rompimento (RSI estourado, Bollinger forte) continuam disparando sempre, independente disso - não são sinais de entrada
- [x] **Aviso de conclusão da operação**: quando uma posição do Modo Papel aberta por um sinal FORTE encerra em Stop Loss ou Take Profit, dispara um aviso (`🛑 STOP` / `✅ TAKE PROFIT`, com R e retorno %) no histórico do dashboard e no Telegram - mesmo filtro de "mais confiança" da entrada (`HIGH_CONFIDENCE_SIGNALS`), consistente nos dois pontos
- [x] 9 novos testes (filtro de confiança pro Telegram em compra/venda fraca/forte, alertas de rompimento continuam incondicionais, aviso de conclusão em STOP/TP2, integração via `refresh()` só pra trades de sinal forte) - 134 testes no total

## ✅ v2.2 — Autenticação no Dashboard Web (entregue)

- [x] Login opcional (desativado por padrão, liga sozinho quando uma senha é configurada via `GORILATRADER_WEB_PASSWORD` ou `web_auth.password` em `config.json`) - protege `/`, toda a API (`/api/*`) e o WebSocket (`/ws/{key}`)
- [x] Sessão via **cookie assinado** (HMAC-SHA256, sem dependência nova) em vez de HTTP Basic Auth - o WebSocket do navegador não permite mandar header `Authorization` no handshake, mas cookies (mesma origem) vão automaticamente, então é o único jeito de autenticar a página e o `/ws/{key}` com o mesmo login. Sessão válida por 30 dias; reiniciar o servidor derruba sessões abertas (segredo gerado por processo)
- [x] `GET/POST /login` (formulário simples, tema escuro consistente com o dashboard) e `POST /logout` (botão "🚪 Sair" no cabeçalho) - página inicial redireciona pro login sem sessão válida
- [x] Aviso visível no terminal ao rodar `--serve --host 0.0.0.0` (ou qualquer host que não seja loopback) sem senha configurada - "exposto sem autenticação, qualquer um na rede pode acessar"
- [x] Nova dependência opcional `python-multipart` (só pro dashboard web, exigida pelo FastAPI pra ler o formulário de login)
- [x] 20 novos testes (assinatura/validação do cookie incluindo adulteração e expiração, `require_auth` em cada rota, fluxo completo de login/logout, WebSocket fecha sem sessão válida) - 154 testes no total

## ✅ v2.3 — Favoritos Entram no Monitor de Alertas (entregue)

- [x] Favoritos deixaram de ser "só visualização por navegador" (`localStorage`) e viraram uma **lista única e compartilhada do servidor**, persistida em `web_favorites.json` - favoritar um ticker o registra de verdade em `ASSETS`, então o monitor de alertas em segundo plano (o mesmo que já rodava pros ativos de `config.json`) passa a tocar apito, mandar Telegram (se o sinal for FORTE) e abrir posição no modo papel pra ele a partir do próximo ciclo
- [x] Novos endpoints `GET /api/favorites` (lista), `POST /api/favorites/{ticker}` (favorita - mesma validação contra ticker inventado do `/api/resolve`) e `DELETE /api/favorites/{ticker}` (desfavorita - para de monitorar)
- [x] Ativos que já vêm de `config.json` nunca saem do monitor por essa rota, mesmo que alguém "desfavorite" - só tickers adicionados como favorito são removidos de `ASSETS` de verdade
- [x] ⚠️ Limitação conhecida e documentada: desfavoritar um ativo com uma posição do modo papel aberta deixa essa posição parada (sem novas atualizações) até ele ser favoritado de novo - não fecha sozinha
- [x] 10 novos testes (favoritar registra em ASSETS e persiste em disco, ticker inválido não muda nenhum estado, desfavoritar remove só o que foi favoritado - nunca um ativo real de config.json, `_load_web_favorites` restaura do disco no início e tolera arquivo ausente/corrompido/com ticker que não resolve mais) - 164 testes no total

## ✅ v2.4 — Seletor de Timeframe e Novos Indicadores no Gráfico Web (entregue)

- [x] **Seletor de timeframe** no gráfico web: botões `3m`/`5m`/`15m`/`1h`/`4h`/`1D`/`1S`/`1M` acima do gráfico - só muda a visualização (candles/indicadores), independente do timeframe principal da análise. `/api/chart/{key}` e `/ws/{key}` aceitam `interval` (400 se não for um dos 8 válidos). *(Nota: na época desta versão o sinal/score da barra lateral era sempre calculado em cima do gráfico de 1h fixo - isso mudou na v2.5, que tornou o timeframe principal da análise configurável.)*
- [x] 🐛 Corrigido: o gráfico chamava `fitContent()` (reenquadra e reseta zoom/posição) a cada push do WebSocket, a cada ~20s - qualquer zoom ou pan que a pessoa tivesse feito era descartado sozinho pouco depois. Agora só reenquadra na primeira carga de um ativo/timeframe; atualizações periódicas seguintes só atualizam os dados, mantendo o que a pessoa deixou na tela
- [x] Nova **EMA 14** no gráfico (fora da matriz de confluência - é só mais um overlay visual, não um fator de pontuação novo)
- [x] Cores das EMAs revisadas: EMA9 azul claro, EMA14 verde claro, EMA21 amarelo, EMA50 laranja, EMA200 branco. Ichimoku: Tenkan (primeira média) verde, Kijun (segunda média) amarelo
- [x] **Volume com média móvel de 21 períodos** (linha amarela sobreposta às barras de volume)
- [x] MACD e Bandas de Bollinger já existiam (MACD no dropdown de osciladores, Bollinger nos overlays) - conferidos e mantidos
- [x] `_OKX_INTERVAL_MAP`/`_KRAKEN_INTERVAL_MAP` expandidos pra cobrir os 8 novos timeframes (Kraken não tem candle nativo de 3min nem de 1 mês - cai pro mais próximo que ela suporta: 5min e 15 dias)
- [x] 5 novos testes (payload inclui EMA14/volume_ma21, `interval` inválido rejeitado com 400, intervalo customizado repassado de verdade pra exchange, mapeamento dos novos timeframes pra OKX e pra Kraken) - 169 testes no total
- [x] Bandas de Bollinger passaram a mostrar também a **média do meio** (SMA 20) - o backend já calculava (`bb_middle`), só faltava o frontend desenhar a linha
- [x] **Favicon** no dashboard web: reaproveita o ícone pixel art do atalho de desktop (`gorilatrader.png`), servido em `/favicon.png` sem exigir login (igual a página de `/login`) - aparece na aba do navegador tanto no dashboard quanto na tela de login
- [x] 1 novo teste (favicon serve o arquivo certo com o content-type certo) - 170 testes no total

## ✅ v2.5 — Timeframe Principal Configurável e Preferências Salvas (entregue)

- [x] **Pergunta uma única vez, não mais a cada execução**: o prompt interativo de ativos (que antes reaparecia em toda execução no terminal) agora só aparece na primeira vez - a resposta é salva em `user_settings.json` (ignorado pelo git, ao lado de `config.json`) e as próximas execuções carregam direto, sem perguntar de novo. `--reconfigure` apaga o que está salvo e volta a perguntar.
- [x] **Timeframe do gráfico principal virou pergunta real** (não só cosmética): a mesma pergunta única agora também cobre qual timeframe acompanhar - `15m`, `1h` (padrão, comportamento anterior), `4h` ou `1d`. A escolha muda de verdade o candle buscado por toda a matriz de confluência (EMAs, RSI, MACD, Bollinger, Donchian, OBV, Ichimoku), tanto no terminal quanto no dashboard web (`--serve`, incluindo o sinal/score da barra lateral e o monitor de alertas em segundo plano)
- [x] **Confirmação multi-timeframe (MTF) proporcional**: o timeframe de confirmação deixou de ser sempre `4h` fixo e passou a acompanhar o timeframe principal escolhido - `15m`→confirma com `1h`, `1h`→confirma com `4h` (igual antes), `4h`→confirma com `1d`, `1d`→confirma com `1w`
- [x] Nova flag `--timeframe` (sobrepõe só na execução atual, sem alterar o que está salvo) e `--reconfigure` (apaga `user_settings.json`)
- [x] Rótulos da interface (coluna `1h %`/`SINAL 1H` da tabela, título do painel, "Timeframe: 1H" do relatório detalhado, "Tendência Maior (4h)", razões técnicas como "Tendência de 4h confirma o viés de 1h") passaram a ser dinâmicos, refletindo o timeframe escolhido em vez de texto fixo
- [x] Cálculo da variação de 24h (`change_24h`) generalizado pra qualquer timeframe (antes assumia sempre 24 candles de 1h = 24h; agora calcula quantos candles do timeframe escolhido cabem em 24h)
- [x] ⚠️ Limitação conhecida e documentada no README: `--backtest` e o `max_holding_hours` do modo papel continuam assumindo candle de 1h internamente, independente do timeframe escolhido aqui - não foram adaptados nesta versão
- [x] Seletor de timeframe do gráfico web (botões acima do candle, v2.4) continua sendo só uma lupa visual independente, sem relação com este timeframe principal da análise

---

## 🚧 Próximos Passos

Nada planejado no momento - sugestões são bem-vindas.

---

## Fora de escopo (por ora)

- Execução automática de ordens (o projeto é um monitor/assistente de decisão, não um bot de execução)
- Suporte a Windows/macOS nativo para os alertas sonoros (hoje depende de `aplay`/`paplay`/`spd-say` do Linux)
