FROM python:3.8

WORKDIR /app
ENV PYTHONUNBUFFERED=1

COPY requirements.txt ./
RUN pip install -r ./requirements.txt
RUN export PYTHONPATH="${PYTHONPATH}:./"
RUN apt-get update

COPY . ./
