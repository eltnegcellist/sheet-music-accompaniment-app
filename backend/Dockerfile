# Audiveris (OMR) needs a JRE; we layer Python on top of the JDK image.
FROM eclipse-temurin:17-jdk-jammy

ARG AUDIVERIS_VERSION=5.3.1
ENV AUDIVERIS_HOME=/opt/audiveris \
    DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 python3-pip python3-venv \
      tesseract-ocr libtesseract-dev \
      curl unzip ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Audiveris ships an installer zip on GitHub Releases.
# Pinning the version keeps builds reproducible. If the URL changes,
# update AUDIVERIS_VERSION above.
RUN mkdir -p ${AUDIVERIS_HOME} \
    && curl -L -o /tmp/audiveris.zip \
       "https://github.com/Audiveris/audiveris/releases/download/${AUDIVERIS_VERSION}/Audiveris-${AUDIVERIS_VERSION}.zip" \
    && unzip /tmp/audiveris.zip -d ${AUDIVERIS_HOME} \
    && rm /tmp/audiveris.zip

WORKDIR /app

COPY pyproject.toml ./
RUN python3 -m pip install --no-cache-dir --break-system-packages -e .

COPY app ./app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
