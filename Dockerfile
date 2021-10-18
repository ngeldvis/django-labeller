FROM python:3.8

WORKDIR /app

ENV PYTHONUNBUFFERED=1

RUN apt-get update
RUN apt-get install ffmpeg libsm6 libxext6 git -y

# install requirements
COPY requirements.txt ./
COPY iris-api-client ./iris-api-client
RUN pip install ./iris-api-client
RUN pip install -r ./requirements.txt

RUN export PYTHONPATH="${PYTHONPATH}:./"

COPY . ./
