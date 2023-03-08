FROM ubuntu:20.04

ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update -qq \
    && apt-get install software-properties-common -qq \
    && add-apt-repository ppa:deadsnakes/ppa -y \
    && apt-get update -qq \
    && apt-get install --no-install-recommends -qq \
        git \
        graphviz \
        latexmk \
        libasan5 \
        libdbus-1-3 \
        libegl1 \
        libfontconfig1 \
        libgl1-mesa-glx \
        libtsan0 \
        libubsan1 \
        libxkbcommon0 \
        make \
        ninja-build \
        python3.7-dev \
        python3.8-dev \
        python3.9-dev \
        python3.10-dev \
        python3.11-dev \
        python3.7-distutils \
        python3.8-distutils \
        python3.9-distutils \
        python3.10-distutils \
        python3.11-distutils \
        texlive-fonts-recommended \
        texlive-latex-extra \
        texlive-latex-recommended \
        texlive-plain-generic \
        texlive-publishers \
        wget \
        && rm -rf /var/lib/apt/lists/* \
    && wget https://bootstrap.pypa.io/get-pip.py \
        && python3.7 get-pip.py \
        && python3.8 get-pip.py \
        && python3.9 get-pip.py \
        && python3.10 get-pip.py \
        && python3.11 get-pip.py

COPY requirements-dev.txt /tmp/

RUN python3.7 -m pip install --no-cache-dir -r /tmp/requirements-dev.txt \
    && python3.8 -m pip install --no-cache-dir -r /tmp/requirements-dev.txt \
    && python3.9 -m pip install --no-cache-dir -r /tmp/requirements-dev.txt \
    && python3.10 -m pip install --no-cache-dir -r /tmp/requirements-dev.txt \
    && python3.11 -m pip install --no-cache-dir -r /tmp/requirements-dev.txt

ENV QT_QPA_PLATFORM offscreen

RUN groupadd -g 1000 jenkins \
    && useradd -rm -d /home/jenkins -u 1000 -g jenkins jenkins

USER jenkins

RUN mkdir -p /home/jenkins/.cache/pip

WORKDIR /home/jenkins
