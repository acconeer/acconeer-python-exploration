FROM ubuntu:18.04

RUN apt-get update
RUN apt-get install -y python3 python3-pip
RUN apt-get install -y libgl1-mesa-glx
RUN apt-get install -y libfontconfig1

RUN python3 -m pip install flake8 pytest pytest-qt

COPY requirements.txt /tmp/
RUN python3 -m pip install -r /tmp/requirements.txt

ENV QT_QPA_PLATFORM offscreen

RUN mkdir /home/jenkins
RUN groupadd -g 1000 jenkins
RUN useradd -r -u 1000 -g jenkins -d /home/jenkins jenkins
RUN chown jenkins:jenkins /home/jenkins
USER jenkins
WORKDIR /home/jenkins
