FROM ghcr.io/home-assistant/base-python:3.12-alpine3.24
ARG BUILD_VERSION=0.4.6
ARG BUILD_ARCH=amd64
LABEL io.hass.version="${BUILD_VERSION}" \
      io.hass.type="app" \
      io.hass.arch="${BUILD_ARCH}"
WORKDIR /app
COPY src/ /app/
EXPOSE 8099
CMD ["python", "-u", "/app/main.py"]