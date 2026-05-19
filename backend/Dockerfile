FROM python:3.12-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Note: idlaser is installed at container startup (entrypoint.sh:
# `pip install -e /idlaser`) — NOT here. docker-compose bind-mounts
# defined in `volumes:` are runtime-only and are not active during
# `docker-compose build`, so the editable install must happen after
# the mount is in place. idlaser is intentionally absent from
# requirements.txt to keep bare-metal pip runs working. See CLAUDE.md
# "ID-Laser draft pipeline".

# Application code
COPY . .

# Create uploads directory
RUN mkdir -p /app/uploads

EXPOSE 8000

CMD ["bash", "entrypoint.sh"]
