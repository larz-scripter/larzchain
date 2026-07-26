# LarzChain node — zero runtime dependencies, so this image is tiny.
FROM python:3.12-slim
WORKDIR /app
COPY larzchain/ ./larzchain/
COPY pyproject.toml README.md ./
VOLUME /data
EXPOSE 9333
# default: a persistent node that bootstraps from the seeds and stays synced.
ENTRYPOINT ["python", "-m", "larzchain"]
CMD ["node", "--port", "9333", "--persist", "/data/chain.json"]
