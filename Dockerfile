FROM python:3.12-slim AS builder

WORKDIR /build
COPY pyproject.toml README.md ./
COPY src ./src
COPY cli ./cli
RUN pip wheel --no-deps --wheel-dir wheels .

FROM python:3.12-slim

LABEL org.opencontainers.image.title="CloudDeploy"
LABEL org.opencontainers.image.description="Multi-cloud application deployment CLI"
LABEL org.opencontainers.image.version="1.4.0"

RUN useradd --create-home --shell /bin/bash deploy
COPY --from=builder /build/wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels

USER deploy
WORKDIR /home/deploy

ENTRYPOINT ["clouddeploy"]
CMD ["--help"]
