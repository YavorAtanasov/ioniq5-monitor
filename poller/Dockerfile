FROM python:3.12-slim

WORKDIR /app

# Without this, Python fully buffers stdout when not attached to a terminal
# (always true inside Docker) - print() output can sit in a buffer
# indefinitely instead of reaching `docker compose logs`, especially for a
# long-running process like this that never exits on its own.
ENV PYTHONUNBUFFERED=1

# piwheels hosts prebuilt ARM wheels - without this, pip has to compile some
# dependencies from source on the Pi's CPU, which is slow and can time out
# on lower-end models. Harmless on amd64 too: pip just won't find matches
# there and falls through to PyPI as normal.
RUN pip config set global.extra-index-url https://www.piwheels.org/simple

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py ./

RUN mkdir -p /app/data

CMD ["python", "-u", "main.py"]
