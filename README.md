# AeroFinderServer Backend Deployment & Environment Documentation

## Deployment to Webdock with Docker

**Prerequisites:**
- Webdock server (Ubuntu recommended)
- Docker installed on your server
- Project files uploaded to the server

### Steps:

1. **Upload Project Files**
   - Use `scp`, `rsync`, or Webdock’s file manager to upload your backend project to the server.

2. **Set Up Environment Variables**
   - Copy `env.example` to `.env` and edit with your values:
     ```sh
     cp env.example .env
     nano .env
     ```
   - Set secure values for `DJANGO_SECRET_KEY`, `CAPCHA_KEY`, database credentials, etc.

3. **Build the Docker Image**
   ```sh
   docker build -t aerofinder-backend .
   ```

4. **Run the Docker Container**
   ```sh
   docker run -d --env-file .env -p 8000:8000 --name aerofinder-backend aerofinder-backend
   ```
   - This runs the backend on port 8000. Adjust as needed.

5. **(Optional) Use Docker Compose**
   - If you have a `docker-compose.yml`, start with:
     ```sh
     docker compose up -d
     ```

6. **Set Up a Reverse Proxy (Recommended)**
   - Use Nginx or Caddy to forward traffic from port 80/443 to your Docker container’s port 8000.
   - Example Nginx config:
     ```
     server {
         listen 80;
         server_name your-domain.com;

         location / {
             proxy_pass http://localhost:8000;
             proxy_set_header Host $host;
             proxy_set_header X-Real-IP $remote_addr;
             proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
             proxy_set_header X-Forwarded-Proto $scheme;
         }
     }
     ```

7. **Check Logs and Status**
   ```sh
   docker logs -f aerofinder-backend
   docker ps
   ```

**For updates:**  
Pull new code, rebuild, and restart:
```sh
docker stop aerofinder-backend
docker rm aerofinder-backend
docker build -t aerofinder-backend .
docker run -d --env-file .env -p 8000:8000 --name aerofinder-backend aerofinder-backend
```

---

## Environment Variables

**File:** `env.example` (copy and rename to `.env` for use)

```
# Django Settings
DJANGO_SECRET_KEY=your-super-secret-key-change-this-in-production
DEBUG=False
ALLOWED_HOST_ONE=0.0.0.0
ALLOWED_HOST_TWO=127.0.0.1
ALLOWED_HOST_THREE=localhost
ALLOWED_HOST_FOUR=9dd6-129-222-205-166.ngrok-free.app
# Database (if using external database)
# DATABASE_URL=postgresql://user:password@host:port/dbname

# CAPTCHA API Key
CAPCHA_KEY=your-2captcha-api-key

# Chrome/ChromeDriver paths (set in Dockerfile)
CHROME_BIN=/usr/bin/google-chrome
CHROMEDRIVER_PATH=/usr/local/bin/chromedriver

FRONT_END_ONE=http://localhost:8080
FRONT_END_TWO=http://localhost:8081
FRONTEND_URL=http://localhost:8080

# Redis (optional)
REDIS_URL=redis://redis:6379/0

# Logging
LOG_LEVEL=INFO

```

**Other possible variables (from Fly.io config, if relevant):**
- `ALLOWED_HOST_FOUR`, `ALLOWED_HOST_ONE`, `ALLOWED_HOST_THREE`, `ALLOWED_HOST_TWO`
- `CAPCHA_KEY`
- `CHROMEDRIVER_PATH`
- `CHROME_BIN`
- `DEBUG`
- `ENVIRONMENT`
- `FRONTEND_URL`, `FRONT_END_ONE`, `FRONT_END_TWO`
- `PORT`
- `SECRET_KEY` 

## Important: Setting up CAPTCHA API Key

- You must create a CAPTCHA API key (CAPCHA_KEY) from [2captcha.com](https://2captcha.com/).
- After creating your account and generating the API key, make sure to load a minimum of $3 credit to ensure the service works reliably.
- Add your API key to the `.env` file as the value for `CAPCHA_KEY`. 

# Tech Stack

- **Framework:** Django (ASGI/WSGI)
- **Language:** Python 3.9+
- **Web Server:** Daphne (ASGI)
- **Database:** (Configurable, e.g., PostgreSQL)
- **Task Queue/Cache:** Redis (optional)
- **Containerization:** Docker
- **Deployment:** Fly.io, Webdock
- **Browser Automation:** Chrome, ChromeDriver
- **CAPTCHA Solving:** 2captcha.com 