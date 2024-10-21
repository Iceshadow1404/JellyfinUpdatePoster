FROM python:3.12-slim

RUN apt-get update && apt-get install -y dos2unix

WORKDIR /mount

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY entrypoint.sh /usr/local/bin/entrypoint.sh

RUN dos2unix /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh


COPY . /app

EXPOSE 8000

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
