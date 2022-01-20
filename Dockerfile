FROM ubuntu:20.04

ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    git \
    graphviz \
    libfontconfig1 \
    libgl1-mesa-glx \
    python3-dev \
    python3-pip \
    wget \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-dev.txt /tmp/
RUN python3 -m pip install -r /tmp/requirements-dev.txt

COPY requirements.txt /tmp/
RUN python3 -m pip install -r /tmp/requirements.txt

ENV QT_QPA_PLATFORM offscreen

RUN mkdir /home/jenkins
RUN groupadd -g 1000 jenkins
RUN useradd -r -u 1000 -g jenkins -d /home/jenkins jenkins
RUN chown jenkins:jenkins /home/jenkins
USER jenkins
WORKDIR /home/jenkins
