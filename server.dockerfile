FROM python:3.12

RUN curl -sSLk https://install.python-poetry.org/ | POETRY_HOME=/opt/poetry python && \
    cd /usr/local/bin && \
    ln -s /opt/poetry/bin/poetry && \
    poetry config virtualenvs.create false

COPY ./server/scripts/start.sh /start.sh
RUN chmod +x /start.sh

COPY ./server/pyproject.toml ./server/poetry.lock* /app/
COPY ./server/app/ /app/app/

WORKDIR /app/
RUN bash -c "poetry install --no-root --no-dev"

ENV PYTHONPATH=/app 

EXPOSE 80

CMD [ "/start.sh" ]
