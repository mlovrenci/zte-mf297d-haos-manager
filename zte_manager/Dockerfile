FROM ghcr.io/home-assistant/base-python:3.12-alpine3.24
ARG BUILD_VERSION=0.6.1
ARG BUILD_ARCH=amd64
LABEL io.hass.version="${BUILD_VERSION}" \
      io.hass.type="app" \
      io.hass.arch="${BUILD_ARCH}"
WORKDIR /app
COPY src/ /app/
EXPOSE 8099
# S6 overlays the Supervisor API token in /run/s6/container_environment.
# with-contenv makes it visible to Python without granting extra API roles.
CMD ["/command/with-contenv", "python", "-u", "/app/main.py"]
