FROM ubuntu:20.04

ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update
RUN apt-get upgrade -y
RUN apt-get install -y python3-dev python3-pip libgl1-mesa-glx libfontconfig1 graphviz git wget

RUN python3 -m pip install pytest pytest-mock pytest-qt pytest-timeout requests sphinx sphinx_rtd_theme tox

COPY requirements.txt /tmp/
RUN python3 -m pip install -r /tmp/requirements.txt

ENV QT_QPA_PLATFORM offscreen

RUN mkdir /home/jenkins
RUN groupadd -g 1000 jenkins
RUN useradd -r -u 1000 -g jenkins -d /home/jenkins jenkins
RUN chown jenkins:jenkins /home/jenkins
USER jenkins
WORKDIR /home/jenkins
