ARG UV_VERSION=0.9.26
FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv_build_stage

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
COPY --from=uv_build_stage /uv /bin/uv

# A tool release can change how CI builds, tests or publishes, so the pins
# are exact. The date freezes what the tools' own ranges leave open.
ARG UV_EXCLUDE_NEWER=2026-09-25T00:00:00Z
RUN uv tool install "hatch==1.18.1" \
    && uv tool install "twine==7.0.0"

RUN mkdir -p /home/jenkins/.cache/pip
RUN mkdir -p /home/jenkins/.cache/uv

WORKDIR /home/jenkins
