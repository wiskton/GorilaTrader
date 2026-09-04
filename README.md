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
- **Filtro Anti-Spam**: O sistema só apita quando ocorre uma **nova transição de sinal** para evitar repetições desnecessárias.

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

## 📂 Estrutura do Projeto

```
GorilaTrader/
├── gorilatrader.py      # Motor de análise + dashboard no terminal (Rich)
├── run.sh               # Script de inicialização (abre terminal se clicado fora de um)
├── requirements.txt     # Dependências Python
├── gorilatrader.png     # Ícone pixel art do app
├── ROADMAP.md            # Próximos passos planejados
└── README.md
```

---

## 🗺️ Roadmap

Confira o [ROADMAP.md](ROADMAP.md) para ver o que já foi entregue e o que está planejado a seguir.

---

*Nota de Gestão de Risco: O mercado de criptomoedas opera 24/7 com alta volatilidade. Nunca arrisque mais de 1% a 2% do seu capital total por operação. Este projeto é uma ferramenta de apoio à decisão e não constitui recomendação de investimento.*
