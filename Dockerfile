FROM ubuntu:18.04

RUN apt-get update
RUN apt-get install -y python3 python3-pip

RUN python3 -m pip install flake8
