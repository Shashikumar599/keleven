# The web app (app/server.py) for hosting. Build context is the repository root; .dockerignore keeps data, runs and docs out.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv

COPY requirements-app.txt .
RUN pip install -r requirements-app.txt

COPY app app
COPY common common
COPY retrieval retrieval
COPY generation generation

# Owner decision (2026-10-11): all media stays, including the theme music. Build with --build-arg INCLUDE_THEME_AUDIO=0 to
# leave the music out (the page then hides its sound button).
ARG INCLUDE_THEME_AUDIO=1
RUN if [ "$INCLUDE_THEME_AUDIO" != "1" ]; then rm -f app/static/audio/office-theme.mp3; fi

# Public deployment: visitors get excerpts and rate limits (app/public.py). Secrets and database URLs come from the environment.
ENV PUBLIC_MODE=1
EXPOSE 8080
CMD ["sh", "-c", "uvicorn app.server:app --host 0.0.0.0 --port ${PORT:-8080}"]
