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

# System packages: Python runtime + Tesseract (Audiveris uses it for text OCR)
# and xdg-utils (pulled in anyway by Audiveris; we install it explicitly so
# we can stub its two entry points before Audiveris's postinst runs).
#
# Audiveris's postinst only calls `xdg-desktop-menu install ...desktop` and
# `xdg-mime install ...MimeInfo.xml`. Both register GUI integrations that a
# headless container doesn't use, and both fail on minimal images because
# the system dirs they write to (e.g. /usr/share/applications,
# /usr/share/mime) don't exist. Overwrite the two binaries in /usr/bin with
# no-op shims so the postinst succeeds regardless of which dirs future
# releases touch.
RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 python3-pip python3-venv \
      tesseract-ocr libtesseract-dev \
      curl ca-certificates \
      xdg-utils \
    && curl -fL -o /tmp/audiveris.deb \
       "https://github.com/Audiveris/audiveris/releases/download/${AUDIVERIS_VERSION}/Audiveris-${AUDIVERIS_VERSION}-ubuntu22.04-x86_64.deb" \
    && printf '#!/bin/sh\nexit 0\n' > /usr/bin/xdg-desktop-menu \
    && printf '#!/bin/sh\nexit 0\n' > /usr/bin/xdg-mime \
    && chmod +x /usr/bin/xdg-desktop-menu /usr/bin/xdg-mime \
    && apt-get install -y --no-install-recommends /tmp/audiveris.deb \
    && rm /tmp/audiveris.deb \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml ./
COPY app ./app
RUN python3 -m pip install --no-cache-dir .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
