FROM debian:bookworm-slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends imagemagick fonts-noto-cjk \
    && find /var/lib/apt/lists -type f -delete
ENTRYPOINT ["/usr/bin/convert"]
