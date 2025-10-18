FROM python:3.10-slim-buster

WORKDIR /app

ENV TZ=Asia/Taipei

COPY . /app

RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "main.py"]
