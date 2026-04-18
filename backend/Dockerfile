# Audiveris (OMR) ships its own bundled JRE inside the .deb, but the
# eclipse-temurin base gives us a sane JDK for any future tooling and matches
# Audiveris's tested platform.
FROM eclipse-temurin:17-jdk-jammy

# Audiveris >=5.7 publishes Ubuntu .deb packages built with jpackage.
# See https://github.com/Audiveris/audiveris/releases — bump as needed.
ARG AUDIVERIS_VERSION=5.10.2
ENV AUDIVERIS_HOME=/opt/audiveris \
    PATH=/opt/audiveris/bin:${PATH} \
    DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# System packages: Python runtime + Tesseract (Audiveris uses it for text OCR).
# `apt-get install ./file.deb` resolves the .deb's transitive dependencies
# automatically, which is why we install it via apt rather than dpkg.
#
# Audiveris's postinst only calls `xdg-desktop-menu install ...desktop` and
# `xdg-mime install ...MimeInfo.xml`. Both register GUI integrations we don't
# need in a headless container, and both fail on minimal images because the
# system dirs they write to don't exist. Stubbing the two commands with
# no-op shims in /usr/local/bin (which precedes /usr/bin in PATH) sidesteps
# the whole problem without chasing which dirs each release's postinst needs.
RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 python3-pip python3-venv \
      tesseract-ocr libtesseract-dev \
      curl ca-certificates \
    && curl -fL -o /tmp/audiveris.deb \
       "https://github.com/Audiveris/audiveris/releases/download/${AUDIVERIS_VERSION}/Audiveris-${AUDIVERIS_VERSION}-ubuntu22.04-x86_64.deb" \
    && printf '#!/bin/sh\nexit 0\n' > /usr/local/bin/xdg-desktop-menu \
    && printf '#!/bin/sh\nexit 0\n' > /usr/local/bin/xdg-mime \
    && chmod +x /usr/local/bin/xdg-desktop-menu /usr/local/bin/xdg-mime \
    && apt-get install -y --no-install-recommends /tmp/audiveris.deb \
    && rm /usr/local/bin/xdg-desktop-menu /usr/local/bin/xdg-mime \
    && rm /tmp/audiveris.deb \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml ./
RUN python3 -m pip install --no-cache-dir -e .

COPY app ./app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
