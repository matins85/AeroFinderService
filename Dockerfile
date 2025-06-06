ARG PYTHON_VERSION=3.9-slim

FROM python:${PYTHON_VERSION}

# System env settings
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CHROME_BIN=/usr/bin/google-chrome \
    CHROMEDRIVER_PATH=/usr/bin/chromedriver

# Create app directory
WORKDIR /code

# Install Chrome dependencies and ChromeDriver
RUN apt-get update && apt-get install -y \
    unzip wget curl gnupg \
    libnss3 libxss1 libasound2 libx11-xcb1 libxcomposite1 libxcursor1 \
    libxdamage1 libxi6 libxtst6 libatk-bridge2.0-0 libgtk-3-0 \
    libdrm2 libgbm1 libxrandr2 libxss1 libwayland-client0 \
    fonts-liberation libappindicator3-1 xdg-utils \
    && wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && apt install -y ./google-chrome-stable_current_amd64.deb \
    && rm -f google-chrome-stable_current_amd64.deb \
    && wget https://storage.googleapis.com/chrome-for-testing-public/137.0.7151.68/linux64/chromedriver-linux64.zip \
    && unzip -j chromedriver-linux64.zip -d /usr/bin/ \
    && chmod +x /usr/bin/chromedriver \
    && rm chromedriver-linux64.zip \
    && apt-get clean


# Install pipenv & dependencies
RUN pip install pipenv
COPY Pipfile Pipfile.lock ./
RUN pipenv install --deploy --system

# Copy project files
COPY . .

# Set SECRET_KEY via ENV or fallback
ENV SECRET_KEY="A2tYPIR2upcwIb7gpPHKywVTTUNnYGI3B614LxEBU3Y8d4W6gK"

EXPOSE 8000

# Run with Daphne (ASGI support)
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "aerofinder.asgi:application"]
