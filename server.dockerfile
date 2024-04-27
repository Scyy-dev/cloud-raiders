FROM python:3.8

RUN curl -sSLk https://install.python-poetry.org/ | POETRY_HOME=/opt/poetry python && \
    cd /usr/local/bin && \
    ln -s /opt/poetry/bin/poetry && \
    poetry config virtualenvs.create false

COPY ./server/scripts/start.sh /start.sh
RUN chmod +x /start.sh

COPY ./server/pyproject.toml /server/poetry.lock* /server/

COPY /server/app /server/app


