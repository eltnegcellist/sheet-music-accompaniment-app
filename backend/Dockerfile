# Audiveris (OMR) ships its own bundled JRE inside the .deb, but the
# eclipse-temurin base gives us a sane JDK for any future tooling and matches
# Audiveris's tested platform.
FROM eclipse-temurin:17-jdk-jammy

# Audiveris >=5.7 publishes Ubuntu .deb packages built with jpackage.
# See https://github.com/Audiveris/audiveris/releases — bump as needed.
ARG AUDIVERIS_VERSION=5.10.2
ENV AUDIVERIS_HOME=/opt/Audiveris \
    PATH=/opt/Audiveris/bin:${PATH} \
    DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# System packages: Python runtime + Tesseract (Audiveris uses it for text OCR).
# `apt-get install ./file.deb` resolves the .deb's transitive dependencies
# automatically, which is why we install it via apt rather than dpkg.
RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 python3-pip python3-venv \
      tesseract-ocr libtesseract-dev \
      curl ca-certificates \
    && curl -fL -o /tmp/audiveris.deb \
       "https://github.com/Audiveris/audiveris/releases/download/${AUDIVERIS_VERSION}/Audiveris-${AUDIVERIS_VERSION}-ubuntu22.04-x86_64.deb" \
    # The .deb's postinst calls xdg-desktop-menu to register a GUI launcher,
    # which fails on a headless image because /usr/share/applications doesn't
    # exist. Pre-create the dirs it expects so install completes cleanly.
    && mkdir -p /usr/share/applications /usr/share/desktop-directories \
                /usr/share/icons/hicolor \
                /usr/share/mime/packages \
    && apt-get install -y --no-install-recommends /tmp/audiveris.deb \
    && rm /tmp/audiveris.deb \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml ./
RUN python3 -m pip install --no-cache-dir -e .

COPY app ./app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
