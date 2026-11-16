FROM python:3.11-slim AS build

WORKDIR /build
COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m pip install --no-cache-dir build \
    && python -m build --wheel

FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd --system app \
    && useradd --system --gid app --home-dir /app app
WORKDIR /app
COPY --from=build /build/dist/*.whl /tmp/
RUN WHEEL="$(find /tmp -name 'pharmaceutical_batch_data_product_pipeline-*.whl' -print -quit)" \
    && python -m pip install --no-cache-dir "${WHEEL}[gcp]" \
    && rm -f /tmp/*.whl
USER app

ENTRYPOINT ["python", "-m", "pharma_data_product.gcp_job"]

