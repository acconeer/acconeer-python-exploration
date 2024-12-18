FROM ubuntu:20.04

ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update -qq \
    && apt-get install software-properties-common -qq \
    && apt-get install --no-install-recommends -qq \
        build-essential \
        git \
        graphviz \
        latexmk \
        libasan5 \
        libdbus-1-3 \
        libegl1 \
        libenchant-2-2 \
        libfontconfig1 \
        libgl1-mesa-glx \
        libtsan0 \
        libubsan1 \
        libxkbcommon0 \
        make \
        ninja-build \
        python3 \
        python3-distutils \
        texlive-fonts-recommended \
        texlive-latex-extra \
        texlive-latex-recommended \
        texlive-plain-generic \
        texlive-publishers \
        wget \
    && rm -rf /var/lib/apt/lists/* \
    && wget https://bootstrap.pypa.io/get-pip.py \
        && python3 get-pip.py \
        && python3 -m pip install --no-cache-dir \
            "hatch>=1.10.0" \
            "pip>=21.3" \
            "requests>=2.0,<3" \
            "twine==5.1.1"

ENV QT_QPA_PLATFORM offscreen

RUN groupadd -g 1000 jenkins \
    && useradd -rm -d /home/jenkins -u 1000 -g jenkins jenkins

USER jenkins

RUN mkdir -p /home/jenkins/.cache/pip
RUN mkdir -p /home/jenkins/.cache/uv

WORKDIR /home/jenkins
