FROM python:3.7.4-alpine3.9
RUN apk --update add build-base bash jpeg-dev zlib-dev python3-dev
ENV PYTHONUNBUFFERED 1
ENV DEMO_DB_NAME /db.sqlite3
RUN mkdir -p /app
WORKDIR /app/
COPY . .

RUN pip install "Pillow>=6.1.0"
RUN pip install -e .
RUN demo/manage.py migrate --no-input && \
    demo/manage.py import_sports tests/quidditch.json


EXPOSE 80
RUN echo Load at http://localhost:8080
CMD ["demo/manage.py", "runserver", "0:80"]
