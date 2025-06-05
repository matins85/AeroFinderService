ARG PYTHON_VERSION=3.9-slim

FROM python:${PYTHON_VERSION}

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

RUN mkdir -p /code

WORKDIR /code

RUN pip install pipenv
COPY Pipfile Pipfile.lock /code/
RUN pipenv install --deploy --system
COPY . /code

ENV SECRET_KEY "A2tYPIR2upcwIb7gpPHKywVTTUNnYGI3B614LxEBU3Y8d4W6gK"
RUN python manage.py collectstatic --noinput

EXPOSE 8000

CMD ["daphne","-b","0.0.0.0","-p","8000","aerofinder.asgi"]
