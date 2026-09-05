# 🦍 GorilaTrader

**GorilaTrader** is a terminal-based quantitative analysis tool for monitoring Bitcoin, Ethereum, Solana, Pepe, and Hyperliquid on the 1-hour chart. It combines EMA trend structure, RSI, MACD, Bollinger Bands, ATR-based risk management, Donchian channel breakouts, OBV volume flow, and the Ichimoku Cloud into a single confluence score, then fires synthesized audio alerts the moment a BUY or SELL signal triggers — right from your terminal. No browser, no bloat.

📄 Full documentation below is in **Portuguese** (the project's primary language). See [ROADMAP.md](ROADMAP.md) for what's planned next.

---

# Monitor Quantitativo Cripto (Gráfico de 1H)

**GorilaTrader** é um sistema de análise técnica quantitativa desenvolvido para monitorar o gráfico de **1 hora (1h)** dos principais ativos cripto:
- ₿ **Bitcoin (BTC)**
- ⟠ **Ethereum (ETH)**
- ◎ **Solana (SOL)**
- 🐸 **Pepe (PEPE)**
- ⚡ **Hyperliquid (HYPE)**

O programa roda diretamente no terminal com dashboard dinâmico em tempo real e **emite apitos sonoros automáticos** sempre que um sinal de **COMPRA** ou **VENDA** é detectado.

---

## 🎯 Estratégia Técnica no Gráfico de 1 Hora

No gráfico de 1h, o GorilaTrader utiliza uma matriz de confluência estatística multivariada que combina:

1. **Estrutura de Tendência (EMAs)**:
   - `EMA 9` (Curto prazo)
   - `EMA 21` (Tendência imediata)
   - `EMA 50` (Tendência intermediária)
   - `EMA 200` (Tendência primária institucional)
   - *Sinal Altista:* Preço > EMA 9 > EMA 21 > EMA 50
   - *Sinal Baixista:* Preço < EMA 9 < EMA 21 < EMA 50

2. **Oscilador de Momento (RSI 14 com Wilder Smoothing)**:
   - Identifica sobrecompra (>70), sobrevenda (<30) e zona de expansão de momentum (50 a 65).
   - Detecta rompimento do eixo neutro (50) e saídas de exaustão.

3. **Convergência/Divergência de Médias (MACD 12, 26, 9)**:
   - Monitora cruzamentos da linha MACD sobre a linha de sinal.
   - Analisa expansão e desaceleração do histograma.

4. **Volatilidade (Bandas de Bollinger 20, 2)**:
   - Identifica squeezes de volatilidade e reversões nas bandas extremas.
   - Classifica a posição do preço em relação ao canal: **Dentro do Canal**, **Rompeu Superior** ou **Rompeu Inferior** (fechamento além da banda, não apenas toque) - exibido no dashboard junto com a distância em desvios-padrão (σ) da média.

5. **Rompimento de Canal (Donchian 20)**:
   - Compara o preço com a máxima/mínima dos 20 períodos anteriores (excluindo a barra atual).
   - Um fechamento acima da máxima anterior ou abaixo da mínima anterior é tratado como rompimento fresco.

6. **Fluxo de Volume (OBV - On-Balance Volume)**:
   - Compara o volume acumulado (OBV) com o preço 10 períodos atrás para confirmar tendência ou flagrar divergência oculta (ex.: preço sobe mas OBV cai = fraqueza escondida).
   - Complementa o filtro de pico de volume relativo (>1.5x a média), que também compõe a matriz.

7. **Ichimoku Kinko Hyo (Tenkan 9, Kijun 26, Senkou Span A/B 52)**:
   - Posição do preço em relação à Nuvem (Kumo): acima = viés estrutural de alta, abaixo = viés de baixa, dentro = mercado indefinido.
   - Cruzamento Tenkan-sen / Kijun-sen (TK Cross) como gatilho de entrada.

8. **Confirmação Multi-Timeframe (4h)**:
   - Compara o viés imediato de 1h (preço vs. EMA21) com a tendência do candle de 4h (preço vs. EMA50 desse timeframe).
   - Reforça o score quando os dois concordam; penaliza um sinal de 1h que vai contra a tendência maior.
   - O candle de 4h é buscado com cache de 15 min (não faz sentido rebuscar a cada atualização de 1h/20s - o candle de 4h só fecha a cada 4 horas).

9. **Gerenciamento de Risco Dinâmico (ATR 14)**:
   - Todo sinal fornece automaticamente:
     - **Preço de Entrada**
     - **Stop Loss (SL)**: `Preço - (1.5 * ATR)` na compra / `Preço + (1.5 * ATR)` na venda
     - **Take Profit 1 (TP1)**: Relação Risco:Retorno de ~1:1.33
     - **Take Profit 2 (TP2)**: Relação Risco:Retorno de ~1:2.33

O score final varia de **-100 a +100** e classifica o sinal (veja a tabela mais abaixo). Fontes de dados por ativo (configurável em `config.json`): Binance (spot/futures, com fallback automático para Bybit em caso de falha de rede), OKX ou Kraken.

---

## 🔊 Sistema de Alertas Sonoros (Apitos)

- **🟢 Sinal de COMPRA / FORTE COMPRA**: Toca um apito melódico ascendente animado (tríade musical C5 ➔ E5 ➔ G5) + sinal do terminal `\a`.
- **🔴 Sinal de VENDA / FORTE VENDA**: Toca um apito descendente incisivo de alerta (A5 ➔ F5 ➔ D5) + sinal do terminal `\a`.
- **⚠ RSI Estourado**: dispara um aviso próprio (independente do score) sempre que o RSI(14) ultrapassa **80** (sobrecompra extrema) ou cai abaixo de **20** (sobrevenda extrema).
- **⚠ Rompimento Forte de Bollinger**: dispara quando o preço fecha a **2.5 desvios-padrão ou mais** da média móvel de 20 períodos (muito além do simples toque na banda que já entra no score) - indica um movimento estatisticamente extremo/exaustão.
- **Filtro Anti-Spam**: cada tipo de alerta só dispara novamente quando o estado muda (ex.: some da sobrecompra e volta a entrar) - sem repetição a cada ciclo enquanto a condição persiste.
- **Histórico Persistente**: os últimos 200 alertas ficam salvos em `alerts_history.json` e sobrevivem a reinícios do programa (arquivo local, não versionado).

---

## 📨 Notificações no Telegram

O Telegram é o canal "seletivo" - feito pra avisar só o que importa, sem virar spam no grupo:

- **Entrada (COMPRA/VENDA)**: só vai pro Telegram quando o sinal é de mais confiança (**FORTE COMPRA**/**FORTE VENDA**). Sinal fraco (COMPRA/VENDA sem FORTE) continua tocando o apito e entrando no histórico do dashboard normalmente - só não dispara o Telegram.
- **Conclusão da operação**: quando uma posição do [Modo Papel](#-modo-papel-paper-trading) aberta por um sinal FORTE encerra (Stop Loss ou Take Profit), o Telegram avisa o resultado (`🛑 STOP` ou `✅ TAKE PROFIT`, com o R e o retorno %).
- **Alertas de rompimento** (RSI estourado >80/<20, rompimento forte de Bollinger >= 2.5σ): continuam indo sempre, independente do filtro acima - são avisos técnicos, não sinais de entrada/saída.

Funciona **tanto rodando o dashboard no terminal quanto o dashboard web** (`--serve` roda um monitor de alertas em segundo plano, independente da interface usada para visualizar).

1. Crie um bot com o [@BotFather](https://t.me/BotFather) e copie o token.
2. Descubra o `chat_id` (fale com o bot e use o [@userinfobot](https://t.me/userinfobot), ou acesse `https://api.telegram.org/bot<TOKEN>/getUpdates` depois de mandar uma mensagem ao bot).
3. Configure as credenciais por variável de ambiente (recomendado, evita segredo em arquivo):
   ```bash
   export TELEGRAM_BOT_TOKEN="123456:ABC-DEF..."
   export TELEGRAM_CHAT_ID="987654321"
   ```
   ...ou copie `config.example.json` para `config.json` e preencha a seção `"telegram"` (esse arquivo já está no `.gitignore`, nunca é versionado).
4. Teste com:
   ```bash
   python3 gorilatrader.py --test-telegram
   ```

Se as credenciais não estiverem configuradas, o programa funciona normalmente e apenas não envia nada ao Telegram (sem erro). Use `--no-telegram` para desativar mesmo com credenciais configuradas.

---

## ⚙️ Configuração (Ativos e Pesos da Matriz)

Por padrão o GorilaTrader já vem configurado com BTC/ETH/SOL/PEPE/HYPE e os pesos descritos na seção de estratégia. Para customizar sem editar o código:

```bash
cp config.example.json config.json
```

Edite `config.json` (ignorado pelo git) para:
- **`assets`**: trocar os ativos monitorados e a exchange usada como fonte de dados de cada um - `exchange` aceita `binance_spot`, `binance_futures` (ambos com fallback automático para Bybit), `okx` ou `kraken`. O formato do `symbol` muda por exchange: `BTCUSDT` (Binance/Bybit), `BTC-USDT` (OKX, com hífen) ou `XBTUSDT` (Kraken, BTC vira XBT) - veja os exemplos comentados em `config.example.json`.
- **`weights`**: ajustar a pontuação de cada fator da matriz de confluência (ex.: aumentar o peso do Ichimoku, reduzir o de RSI).
- **`telegram`**: credenciais do bot (alternativa às variáveis de ambiente).
- **`paper_trading`**: liga/desliga o modo papel (`enabled`) e o tempo máximo de uma posição simulada aberta (`max_holding_hours`) - veja a seção [📝 Modo Papel](#-modo-papel-paper-trading) abaixo.

Qualquer chave omitida usa o valor padrão - não é preciso repetir tudo, só o que quiser mudar.

### Escolher as criptos na hora, sem editar `config.json`

Pra trocar os ativos rapidinho (sem mexer em arquivo), o terminal também aceita:

```bash
# Prompt interativo: ao abrir o terminal, ele pergunta o que acompanhar (Enter = usa o config.json)
python3 gorilatrader.py

# Ou direto por flag, pulando o prompt (funciona em qualquer modo, inclusive --serve/--backtest):
python3 gorilatrader.py --assets BTC,ETH,DOGE
```

Um ticker que já está no `config.json`/nos padrões (ex.: `BTC`) reaproveita nome, ícone, exchange e casas decimais já curados. Um ticker novo (ex.: `DOGE`) assume automaticamente o par `TICKERUSDT` na Binance spot e detecta as casas decimais de exibição pelo preço atual (preços bem pequenos, tipo PEPE, ganham mais casas pra não arredondar tudo pra zero). Se o par não existir na Binance, o programa avisa e segue mesmo assim (aquele ativo aparece como "Erro de conexão" no dashboard). O prompt só aparece em terminal interativo - `--serve`, `--backtest`, `--paper-report`, `--reset-paper-trading`, `--test-telegram` e `--test-sound` nunca travam esperando input.

Não tem limite de quantidade - a tabela do terminal cresce automaticamente com o número de ativos (1 linha a mais por ativo) e se ajusta à altura do terminal disponível, então dá pra acompanhar dezenas ou centenas de criptos de uma vez (`--assets BTC,ETH,SOL,...`), não só as 5 do padrão. Num terminal pequeno demais pra caber tudo, o histórico de alertas cede espaço primeiro; a tabela de ativos só é comprimida como último recurso.

---

## 📦 Instalação

Requer Python 3.9+ e (no Linux) `aplay` ou `paplay` para tocar os apitos.

```bash
git clone git@github.com:wiskton/GorilaTrader.git
cd GorilaTrader
pip install -r requirements.txt
```

## 🛠 Como Executar

### 1. Iniciar o Monitor em Tempo Real (Padrão com Apito)
```bash
./run.sh
# ou:
python3 gorilatrader.py
```

### 2. Análise Instantânea do Momento Atual (Snapshot)
Gera o diagnóstico completo de todos os ativos imediatamente e encerra:
```bash
python3 gorilatrader.py --once
```

### 3. Ajustar o Intervalo de Atualização
```bash
python3 gorilatrader.py --interval 15   # Atualiza a cada 15 segundos
```

### 4. Testar o Som dos Apitos
```bash
python3 gorilatrader.py --test-sound
```

### 5. Ativar Locução por Voz Sintética
Além do apito sonoro, o sistema fala em português o ativo e o sinal:
```bash
python3 gorilatrader.py --voice
```

### 6. Testar a Integração com o Telegram
```bash
python3 gorilatrader.py --test-telegram
```

### 7. Dashboard Web (gráfico profissional estilo TradingView)
```bash
python3 gorilatrader.py --serve
# abre em http://127.0.0.1:8000
```
Sobe um servidor local com um gráfico de candles em tempo real ([Lightweight Charts](https://github.com/tradingview/lightweight-charts), open-source da própria TradingView) com overlays configuráveis (EMA9/14/21/50/200, Bandas de Bollinger, Canal Donchian, Nuvem de Ichimoku - as três últimas com a área entre as bandas sombreada, via uma primitiva de desenho customizada já que o Lightweight Charts v4 não tem série nativa de "preenchimento entre duas linhas") e um painel de oscilador (RSI/MACD/OBV) sincronizado. A barra lateral mostra sinal, score, Stop Loss/Take Profits e os fatores técnicos do ativo selecionado. A atualização é via **WebSocket** (`/ws/{ativo}`) - o servidor empurra gráfico + snapshot a cada ~20s sem o navegador precisar ficar re-consultando a API, com reconexão automática se a conexão cair. Use `--port` para trocar a porta e `--host 0.0.0.0` para acessar de outro dispositivo na rede.

**⏱ Seletor de timeframe**: botões acima do gráfico trocam entre `3m`/`5m`/`15m`/`1h`/`4h`/`1D`/`1S`/`1M` - troca só a visualização do gráfico (candles/indicadores), o sinal/score da barra lateral continua sempre calculado no gráfico de 1h (é a identidade do projeto). Trocar de ativo ou de timeframe reenquadra o gráfico uma vez; as atualizações periódicas seguintes do WebSocket (a cada ~20s) só atualizam os dados **sem** resetar seu zoom/posição na tela.

**Cores das EMAs**: EMA9 azul claro, EMA14 verde claro, EMA21 amarelo, EMA50 laranja, EMA200 branco. **Ichimoku**: Tenkan (primeira média) verde, Kijun (segunda média) amarelo. O volume vem com uma **média móvel de 21 períodos em amarelo** sobreposta às barras, e as **Bandas de Bollinger** agora mostram a média do meio (SMA 20) além das bandas superior/inferior.

A aba do navegador usa o mesmo ícone pixel art do atalho de desktop (`gorilatrader.png`, servido em `/favicon.png`, sem precisar de login).

**⭐ Favoritos na barra lateral**: digite qualquer ticker (ex.: `DOGE`) na caixa "Favoritos" e clique em "+" - o servidor resolve o símbolo (par USDT na Binance, decimais detectados pelo preço, mesmo mecanismo do `--assets` do terminal) e adiciona à lista. Clique num favorito pra trocar o gráfico pra ele.

Diferente da v2.0, a lista de favoritos agora é **única e compartilhada do servidor** (persistida em `web_favorites.json`, não mais por navegador) - e favoritar um ticker o registra de verdade como ativo monitorado: a partir do próximo ciclo ele passa a tocar apito, mandar Telegram (se o sinal for FORTE) e abrir posição no modo papel, exatamente como um ativo do `config.json`. Desfavoritar para de monitorar (exceto os ativos que já vêm de `config.json`, esses nunca saem por aqui). Um ticker que não existe na Binance mostra um aviso e não é adicionado.

⚠️ Se uma posição do modo papel estiver aberta num favorito no momento de desfavoritá-lo, ela fica parada (sem novas atualizações) até o ativo ser favoritado de novo - não fecha automaticamente.

**📝 Modo Papel no dashboard**: o botão "📝 Modo Papel" no cabeçalho abre um painel com a mesma performance do `--paper-report` do terminal (taxa de acerto, R médio, retorno % por direção, posições abertas e últimas entradas fechadas) - lê do mesmo motor que roda em segundo plano no `--serve` (`/api/paper-trading`).

**🔒 Autenticação (recomendado com `--host 0.0.0.0`)**: desativada por padrão (uso local, `127.0.0.1`). Pra expor o dashboard na rede com segurança, configure uma senha:
```bash
export GORILATRADER_WEB_PASSWORD="sua-senha"
# ...ou copie config.example.json pra config.json e preencha "web_auth.password"
python3 gorilatrader.py --serve --host 0.0.0.0
```
Com a senha configurada, `/`, a API e o WebSocket passam a exigir login (`/login`) - a sessão fica num cookie assinado (HMAC, sem dependência nova) válido por 30 dias; `/logout` (botão "🚪 Sair" no cabeçalho) encerra. Sem senha configurada e com `--host` diferente de `127.0.0.1`, o terminal avisa que o dashboard está exposto sem proteção.

Ou clique no atalho **GorilaTrader Web** no menu de aplicativos (veja abaixo) - ele sobe o servidor e já abre o navegador automaticamente:
```bash
./run-web.sh
```

---

## 🖱️ Atalhos no Menu de Aplicativos (Linux)

O projeto pode instalar dois atalhos no menu de aplicativos (testado no Pop!_OS/COSMIC, funciona em qualquer desktop freedesktop.org-compatible):
- **GorilaTrader** - abre o dashboard no terminal (`run.sh`).
- **GorilaTrader Web** - sobe o dashboard web e abre o navegador (`run-web.sh`).

```bash
./install-desktop.sh
```
O script resolve os caminhos automaticamente a partir de onde o projeto foi clonado - não precisa editar nada manualmente, mesmo se você mover a pasta depois (é só rodar de novo).

---

## 📊 Classificação dos Sinais

| Sinal | Score Confluência | Ação Recomendada |
|---|:---:|---|
| 🟢 **FORTE COMPRA** | `>= +50` | Alta confluência de médias, MACD e RSI. Excelente relação R:R para entrada. |
| 🟢 **COMPRA** | `+25` a `+49` | Tendência favorável de alta. Entrada recomendada com Stop Loss posicionado. |
| ⚪ **AGUARDAR / NEUTRO** | `-24` a `+24` | Mercado lateral ou em consolidação. Aguardar definição de rompimento. |
| 🔴 **VENDA** | `-25` a `-49` | Perda de suportes e momentum negativo. Realizar lucros ou buscar posições vendidas. |
| 🔴 **FORTE VENDA** | `<= -50` | Forte pressão vendedora. Recomenda-se sair de compras ou operar short. |

---

## 🧪 Testes Automatizados

O motor de scoring (`CryptoAnalyzer.analyze_dataframe`) tem uma suíte de testes que isola cada um dos 15 fatores da matriz de confluência (zera todos os pesos exceto o fator sob teste, com um cenário sintético calibrado para disparar exatamente aquela condição) - além de testes de integração (classificação de sinal, direção de SL/TP, uma regressão para o bug histórico da EMA200), config, Telegram e persistência do histórico.

```bash
pip install -r requirements-dev.txt
pytest                 # roda toda a suíte (tests/)
pytest -v tests/test_scoring_matrix.py   # só a matriz de confluência, com nomes de cada caso
```

---

## 📈 Backtest

Roda a matriz de decisão contra histórico real (Binance) para medir se ela teria funcionado, sem nenhum vazamento de dados futuros - em cada barra, o sinal só enxerga candles até aquele ponto; a posição é resolvida depois olhando os candles seguintes de verdade (ver docstring de `backtest.py` para a metodologia completa, incluindo a regra conservadora de desempate quando Stop e alvo são tocados na mesma barra).

```bash
python3 gorilatrader.py --backtest BTC
python3 gorilatrader.py --backtest ETH --backtest-days 90
```

Mostra taxa de acerto, R médio (retorno normalizado pelo risco) e retorno % por direção (COMPRA/VENDA), além da lista das últimas entradas com preço/resultado. Útil para comparar diferentes `weights` em `config.json` antes de usar em conta real - o backtest já lê os pesos configurados.

⚠️ É uma ferramenta de análise histórica, não uma promessa de resultado futuro - custos de execução (spread, slippage, taxas) não são simulados.

---

## 📝 Modo Papel (Paper Trading)

Diferente do backtest (que roda sobre histórico já fechado), o modo papel acompanha os sinais **ao vivo**: sempre que o sinal de um ativo muda para COMPRA/VENDA (mesma regra anti-spam dos apitos), abre uma posição simulada no preço do momento com o SL/TP1/TP2 exibidos naquele instante, e fecha depois em STOP, TP2 ou timeout por tempo - sem enviar nenhuma ordem real a lugar nenhum. É a forma de acompanhar a performance real da estratégia com o tempo, rodando tanto no terminal quanto no `--serve` (dashboard web).

Vem **ativado por padrão**. Estado persistido em `paper_trades.json` (local, não versionado), sobrevive a reinícios.

```bash
python3 gorilatrader.py --paper-report          # relatório de performance (posições abertas + fechadas) e encerra
python3 gorilatrader.py --no-paper-trading      # desativa nesta execução do terminal
python3 gorilatrader.py --reset-paper-trading   # apaga o histórico do modo papel e encerra
```

⚠️ Limitação conhecida: a checagem de SL/TP acontece a cada ciclo de atualização (ex.: a cada 20-60s), não em dados de tick - um pavio muito rápido entre duas checagens pode não ser capturado.

---

## 🐳 Docker (monitoramento 24/7 num servidor/VPS)

A imagem roda o **dashboard web** (`--serve`, que também dispara os alertas) - o modo terminal com apito/voz depende de dispositivos de áudio do host e não faz sentido num container headless.

```bash
docker build -t gorilatrader .
docker run -d -p 8000:8000 \
  -e TELEGRAM_BOT_TOKEN="123456:ABC..." \
  -e TELEGRAM_CHAT_ID="@seu_canal" \
  -v gorilatrader-data:/data \
  --name gorilatrader gorilatrader
```

Ou com Docker Compose (lê `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` de um arquivo `.env` na mesma pasta, se existir):
```bash
docker compose up -d
```

O volume em `/data` (controlado por `GORILATRADER_DATA_DIR`) persiste `config.json`, `alerts_history.json`, `paper_trades.json`, `web_favorites.json` e `gorilatrader.log` entre restarts/rebuilds - sem ele, o histórico (incluindo modo papel e favoritos do dashboard web) reseta a cada `docker compose up`.

---

## 📂 Estrutura do Projeto

```
GorilaTrader/
├── gorilatrader.py         # Motor de análise + dashboard no terminal (Rich)
├── webserver.py            # Backend do dashboard web (FastAPI + WebSocket) - reaproveita o motor acima
├── web/index.html          # Frontend do dashboard web (Lightweight Charts, sem build step)
├── backtest.py             # Motor de backtest (--backtest) sobre histórico real da Binance
├── paper_trading.py        # Motor do modo papel (--paper-report) - simula execução dos sinais ao vivo
├── tests/                  # Suíte pytest (matriz de confluência, backtest, modo papel, dashboard web, layout do terminal, config, Telegram, histórico)
├── Dockerfile / docker-compose.yml / .dockerignore  # Empacotamento para servidor/VPS
├── run.sh                  # Inicia o dashboard no terminal (abre terminal se clicado fora de um)
├── run-web.sh              # Inicia o dashboard web e abre o navegador
├── install-desktop.sh      # Instala os atalhos no menu de aplicativos
├── desktop/                # Templates dos atalhos .desktop (usados pelo install-desktop.sh)
├── requirements.txt        # Dependências Python
├── requirements-dev.txt    # + pytest, só para desenvolvimento
├── config.example.json     # Modelo de configuração (copie para config.json)
├── gorilatrader.png        # Ícone pixel art do app
├── ROADMAP.md               # Próximos passos planejados
└── README.md

# Gerados em tempo de execução (ignorados pelo git):
# config.json, alerts_history.json, paper_trades.json, web_favorites.json, gorilatrader.log
```

---

## 🗺️ Roadmap

Confira o [ROADMAP.md](ROADMAP.md) para ver o que já foi entregue e o que está planejado a seguir.

---

*Nota de Gestão de Risco: O mercado de criptomoedas opera 24/7 com alta volatilidade. Nunca arrisque mais de 1% a 2% do seu capital total por operação. Este projeto é uma ferramenta de apoio à decisão e não constitui recomendação de investimento.*
