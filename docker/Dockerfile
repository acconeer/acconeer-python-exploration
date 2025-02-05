FROM ubuntu:24.04

RUN userdel -r ubuntu

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
    libgl1 \
    libglx-mesa0 \
    libtsan0 \
    libubsan1 \
    libxkbcommon0 \
    make \
    ninja-build \
    python3-full \
    pipx \
    texlive-fonts-recommended \
    texlive-latex-extra \
    texlive-latex-recommended \
    texlive-plain-generic \
    texlive-publishers \
    wget \
    && rm -rf /var/lib/apt/lists/*

ENV QT_QPA_PLATFORM offscreen

RUN groupadd -g 1000 jenkins \
    && useradd -rm -d /home/jenkins -u 1000 -g jenkins jenkins

USER jenkins

ENV PATH="$PATH:/home/jenkins/.local/bin"
RUN pipx install "hatch>=1.13.0" "twine==6.0.1"

RUN mkdir -p /home/jenkins/.cache/pip
RUN mkdir -p /home/jenkins/.cache/uv

WORKDIR /home/jenkins
