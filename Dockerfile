# Model rembg được nướng sẵn vào image: môi trường air-gapped chạy được, và
# request đầu tiên không phải gánh vài chục MB tải về (đủ lâu để timeout ở proxy).
FROM python:3.12-slim AS base

# opencv-python cần libGL/libglib ngay cả ở bản headless-adjacent.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN pip install --no-cache-dir .

# Nướng model vào image — bước này cần mạng lúc BUILD, không cần lúc chạy.
ENV U2NET_HOME=/opt/u2net
RUN python -c "from qc_scanner.rembg_session import warmup; warmup()"

EXPOSE 5000
ENV QC_SCANNER_WORK_HEIGHT=500

# Bind 0.0.0.0 là đúng bên trong container (network namespace riêng); việc phơi
# ra ngoài hay không do -p của docker run quyết định. Server KHÔNG có xác thực.
CMD ["qc-scanner-server", "-a", "0.0.0.0", "-p", "5000"]
