ARG UV_VERSION=0.9.26
FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv_build_stage

FROM ubuntu:24.04

RUN userdel -r ubuntu

ARG DEBIAN_FRONTEND=noninteractive

COPY --from=uv_build_stage /uv /bin/uv

RUN apt-get update -qq \
    && apt-get install software-properties-common -qq \
    && apt-get install --no-install-recommends -qq \
    build-essential \
    git \
    graphviz \
    latexmk \
    libusb-1.0-0 \
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
    texlive-fonts-recommended \
    texlive-latex-extra \
    texlive-latex-recommended \
    texlive-plain-generic \
    texlive-publishers \
    wget \
    && rm -rf /var/lib/apt/lists/*

ENV QT_QPA_PLATFORM=offscreen

RUN groupadd -g 1000 jenkins \
    && useradd -rm -d /home/jenkins -u 1000 -g jenkins jenkins

USER jenkins

ENV PATH="$PATH:/home/jenkins/.local/bin"
# The "--exclude-newer" is due to an issue that come from
# virtualenv==21.0.0 + the hatch version pin.
# This should be revisited in the future.
RUN uv tool install --exclude-newer 2026-02-24T00:00:00Z "hatch>=1.13.0,<1.16.0"
RUN uv tool install "twine==6.0.1"

RUN mkdir -p /home/jenkins/.cache/pip
RUN mkdir -p /home/jenkins/.cache/uv

WORKDIR /home/jenkins
