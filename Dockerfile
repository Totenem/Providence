FROM python:3.12-slim-bookworm AS runtime-base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PROVIDENCE_DATA_DIR=/data \
    PROVIDENCE_MODEL_DIR=/opt/providence-model \
    PROVIDENCE_CONTAINER=1 \
    HF_HUB_DISABLE_TELEMETRY=1 \
    DISPLAY=:99 \
    QT_X11_NO_MITSHM=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb x11vnc novnc websockify openbox \
    libegl1 libgl1 libxkbcommon0 libxkbcommon-x11-0 libdbus-1-3 \
    libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 \
    libxcb-render-util0 libxcb-xinerama0 libxcb-randr0 fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
RUN python -m venv /opt/venv \
    && pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
COPY pyproject.toml /app/
ENV HF_HUB_DISABLE_XET=1
RUN python -c "import subprocess,tomllib; subprocess.check_call(['pip','install','--no-cache-dir',*tomllib.load(open('pyproject.toml','rb'))['project']['dependencies']])"
COPY docker/download_model.py /app/docker/download_model.py
RUN python /app/docker/download_model.py \
    && HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python -c "from transformers import BertModel,BertTokenizerFast; BertModel.from_pretrained('/opt/providence-model',local_files_only=True); BertTokenizerFast.from_pretrained('/opt/providence-model',local_files_only=True); print('Offline model verified')"
ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
RUN apt-get update && apt-get install -y --no-install-recommends libxcb-shape0 x11-utils \
    && rm -rf /var/lib/apt/lists/*
COPY providence /app/providence
RUN pip install --no-cache-dir --no-deps .

FROM runtime-base AS test
RUN pip install --no-cache-dir 'pytest>=8,<10'
COPY tests /app/tests
ENV QT_QPA_PLATFORM=offscreen
CMD ["python", "-m", "pytest", "-q"]

FROM runtime-base AS desktop
RUN useradd --create-home --uid 1000 providence \
    && mkdir -p /data /documents && chown providence:providence /data /documents
COPY docker/entrypoint.sh /app/docker/entrypoint.sh
RUN chmod +x /app/docker/entrypoint.sh
USER providence
EXPOSE 6080
HEALTHCHECK --interval=10s --timeout=3s --start-period=30s \
    CMD python -c "import socket,urllib.request; urllib.request.urlopen('http://127.0.0.1:6080/vnc.html', timeout=2); s=socket.create_connection(('127.0.0.1',5900),timeout=2); assert s.recv(12).startswith(b'RFB '); s.close()" || exit 1
ENTRYPOINT ["/app/docker/entrypoint.sh"]
