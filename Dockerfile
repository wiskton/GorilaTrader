# GorilaTrader - imagem para rodar o dashboard web (--serve) 24/7 num servidor/VPS.
# O modo terminal (apito/voz) depende de aplay/paplay/spd-say do host e não faz
# sentido dentro de um container headless - use --serve aqui.

FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt fastapi "uvicorn[standard]"

COPY gorilatrader.py webserver.py ./
COPY web ./web

# config.json, alerts_history.json e gorilatrader.log ficam em /data (monte um
# volume nesse caminho para persistir configuração/histórico entre restarts).
ENV GORILATRADER_DATA_DIR=/data
RUN mkdir -p /data

EXPOSE 8000

CMD ["python3", "gorilatrader.py", "--serve", "--host", "0.0.0.0", "--port", "8000"]
