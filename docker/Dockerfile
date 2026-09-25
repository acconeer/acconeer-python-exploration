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

COPY --from=uv_build_stage /uv /bin/uv

# Installed system-wide on the system Python, so any user can run them.
# ARG keeps these settings out of the final image.
ARG UV_TOOL_DIR=/opt/uv-tools
ARG UV_TOOL_BIN_DIR=/usr/local/bin
ARG UV_PYTHON_PREFERENCE=only-system
ARG UV_NO_CACHE=1

# A tool release can change how CI builds, tests or publishes, so the pins
# are exact. The date freezes what the tools' own ranges leave open.
ARG UV_EXCLUDE_NEWER=2026-09-25T00:00:00Z
RUN uv tool install "hatch==1.18.1" \
    && uv tool install "twine==7.0.0"

# CI runs the container as an arbitrary uid, which has no home here.
ENV HOME=/home/ci
# Writable by any uid, as is a new uv cache volume, which copies the mode of
# its mount point.
RUN mkdir -m 1777 /home/ci /home/ci/.cache /home/ci/.cache/uv
