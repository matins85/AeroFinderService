# Dockerfile
FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    CHROME_BIN=/usr/bin/google-chrome \
    CHROMEDRIVER_PATH=/usr/bin/chromedriver \
    LANG=en_NG.UTF-8 \
    LANGUAGE=en_NG:en \
    LC_ALL=en_NG.UTF-8 \
    TZ=Africa/Lagos

WORKDIR /code

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    postgresql-client \
    libpq-dev \
    netcat-openbsd \
    locales \
    tzdata \
    unzip \
    wget \
    curl \
    gnupg \
    libnss3 \
    libxss1 \
    libasound2 \
    libx11-xcb1 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxi6 \
    libxtst6 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libdrm2 \
    libgbm1 \
    libxrandr2 \
    libwayland-client0 \
    fonts-liberation \
    libappindicator3-1 \
    xdg-utils \
    && echo "en_NG.UTF-8 UTF-8" > /etc/locale.gen \
    && locale-gen en_NG.UTF-8 \
    && update-locale LANG=en_NG.UTF-8 \
    && ln -sf /usr/share/zoneinfo/Africa/Lagos /etc/localtime \
    && dpkg-reconfigure -f noninteractive tzdata \
    && wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && apt install -y --no-install-recommends ./google-chrome-stable_current_amd64.deb \
    && rm -f google-chrome-stable_current_amd64.deb \
    && wget https://storage.googleapis.com/chrome-for-testing-public/137.0.7151.68/linux64/chromedriver-linux64.zip \
    && unzip -j chromedriver-linux64.zip -d /usr/bin/ \
    && chmod +x /usr/bin/chromedriver \
    && rm chromedriver-linux64.zip \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /code

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy entrypoint BEFORE switching to non-root user
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh && chown appuser:appuser /entrypoint.sh

# Copy project files
COPY --chown=appuser:appuser . .

# Switch to non-root user
USER appuser

# Set entrypoint
ENTRYPOINT ["/entrypoint.sh"]

# Run with Daphne (ASGI support)
CMD ["daphne", "-b", "0.0.0.0", "-p", "8003", "aerofinder.asgi:application"]
