FROM ubuntu:18.04

RUN apt-get update
RUN apt-get install -y python3.6 python3.6-distutils libgl1-mesa-glx libfontconfig1 graphviz git wget

RUN wget https://bootstrap.pypa.io/get-pip.py
RUN python3.6 get-pip.py

RUN python3.6 -m pip install pytest pytest-qt pytest-timeout tox sphinx sphinx_rtd_theme

COPY requirements.txt /tmp/
RUN python3.6 -m pip install -r /tmp/requirements.txt

RUN ln -s /usr/bin/python3.6 /usr/local/bin/python3

ENV QT_QPA_PLATFORM offscreen

RUN mkdir /home/jenkins
RUN groupadd -g 1000 jenkins
RUN useradd -r -u 1000 -g jenkins -d /home/jenkins jenkins
RUN chown jenkins:jenkins /home/jenkins
USER jenkins
WORKDIR /home/jenkins
