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

# idlaser is installed at build time from the in-tree git submodule at
# backend/external/idlaser (S005). Kept out of requirements.txt because
# the path is repo-relative and idlaser is not on PyPI. COPY first so
# the pip install layer caches independently of unrelated source changes.
# See CLAUDE.md "ID-Laser draft pipeline".
COPY ./external/idlaser ./external/idlaser
RUN pip install --no-cache-dir -e ./external/idlaser

# Application code
COPY . .

# Create uploads directory
RUN mkdir -p /app/uploads

EXPOSE 8000

CMD ["bash", "entrypoint.sh"]
