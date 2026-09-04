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

5. **Rompimento de Canal (Donchian 20)**:
   - Compara o preço com a máxima/mínima dos 20 períodos anteriores (excluindo a barra atual).
   - Um fechamento acima da máxima anterior ou abaixo da mínima anterior é tratado como rompimento fresco.

6. **Fluxo de Volume (OBV - On-Balance Volume)**:
   - Compara o volume acumulado (OBV) com o preço 10 períodos atrás para confirmar tendência ou flagrar divergência oculta (ex.: preço sobe mas OBV cai = fraqueza escondida).
   - Complementa o filtro de pico de volume relativo (>1.5x a média), que também compõe a matriz.

7. **Ichimoku Kinko Hyo (Tenkan 9, Kijun 26, Senkou Span A/B 52)**:
   - Posição do preço em relação à Nuvem (Kumo): acima = viés estrutural de alta, abaixo = viés de baixa, dentro = mercado indefinido.
   - Cruzamento Tenkan-sen / Kijun-sen (TK Cross) como gatilho de entrada.

8. **Gerenciamento de Risco Dinâmico (ATR 14)**:
   - Todo sinal fornece automaticamente:
     - **Preço de Entrada**
     - **Stop Loss (SL)**: `Preço - (1.5 * ATR)` na compra / `Preço + (1.5 * ATR)` na venda
     - **Take Profit 1 (TP1)**: Relação Risco:Retorno de ~1:1.33
     - **Take Profit 2 (TP2)**: Relação Risco:Retorno de ~1:2.33

O score final varia de **-100 a +100** e classifica o sinal (veja a tabela mais abaixo). Fontes de dados: Binance (spot/futures) com fallback automático para Bybit em caso de falha de rede.

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

Todos os avisos (sinais de COMPRA/VENDA, RSI estourado e rompimento forte de Bollinger) também podem ser enviados para um chat do Telegram, além do apito local.

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
- **`assets`**: trocar os ativos monitorados (qualquer par `*USDT` da Binance spot ou futures).
- **`weights`**: ajustar a pontuação de cada fator da matriz de confluência (ex.: aumentar o peso do Ichimoku, reduzir o de RSI).
- **`telegram`**: credenciais do bot (alternativa às variáveis de ambiente).

Qualquer chave omitida usa o valor padrão - não é preciso repetir tudo, só o que quiser mudar.

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
Sobe um servidor local com um gráfico de candles em tempo real ([Lightweight Charts](https://github.com/tradingview/lightweight-charts), open-source da própria TradingView) com overlays configuráveis (EMA9/21/50/200, Bandas de Bollinger, Canal Donchian, Nuvem de Ichimoku) e um painel de oscilador (RSI/MACD/OBV) sincronizado. A barra lateral mostra sinal, score, Stop Loss/Take Profits e os fatores técnicos do ativo selecionado. A atualização é via **WebSocket** (`/ws/{ativo}`) - o servidor empurra gráfico + snapshot a cada ~20s sem o navegador precisar ficar re-consultando a API, com reconexão automática se a conexão cair. Use `--port` para trocar a porta e `--host 0.0.0.0` para acessar de outro dispositivo na rede.

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

## 📂 Estrutura do Projeto

```
GorilaTrader/
├── gorilatrader.py         # Motor de análise + dashboard no terminal (Rich)
├── webserver.py            # Backend do dashboard web (FastAPI + WebSocket) - reaproveita o motor acima
├── web/index.html          # Frontend do dashboard web (Lightweight Charts, sem build step)
├── tests/                  # Suíte pytest (matriz de confluência, config, Telegram, histórico)
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
# config.json, alerts_history.json, gorilatrader.log
```

---

## 🗺️ Roadmap

Confira o [ROADMAP.md](ROADMAP.md) para ver o que já foi entregue e o que está planejado a seguir.

---

*Nota de Gestão de Risco: O mercado de criptomoedas opera 24/7 com alta volatilidade. Nunca arrisque mais de 1% a 2% do seu capital total por operação. Este projeto é uma ferramenta de apoio à decisão e não constitui recomendação de investimento.*
