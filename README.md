# Acconeer Exploration Tool

[![Supported Python versions](https://img.shields.io/pypi/pyversions/acconeer-exptool.svg?logo=python&logoColor=FFE873)](https://pypi.org/project/acconeer-exptool/)
[![PyPI version](https://img.shields.io/pypi/v/acconeer-exptool.svg?logo=pypi&logoColor=FFE873)](https://pypi.org/project/acconeer-exptool/)
[![PyPI downloads](https://img.shields.io/pypi/dm/acconeer-exptool.svg)](https://pypistats.org/packages/acconeer-exptool)

[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Documentation Status](https://readthedocs.com/projects/acconeer-acconeer-python-exploration/badge/?version=latest)](https://docs.acconeer.com/en/latest/?badge=latest)

_**Explore the Next Sense**_ with Acconeer Exploration Tool! Use one of our [evaluation kits](https://www.acconeer.com/products) together with our Python examples and start exploring the world of Acconeer's radar sensor technology. The Python scripts and the Application in this repository will help you to easily stream the radar sensor's data to your local machine to start radar sensor evaluation and/or algorithm development for your application.

To run the Python exploration scripts, you will need an [evaluation kit](https://www.acconeer.com/products) running the included Exploration or Module server, both of which are supplied with the [Acconeer SDK and Module SW](https://developer.acconeer.com/) image.

This release is developed for [Acconeer SDK and Module SW](https://developer.acconeer.com/)
**A111-v2.14.2**
and
**A121-v1.0.0**.
Running this version is strongly recommended, as we continuously fix bugs and add features.

<p align="center">
  <img alt="The application in action" src="https://raw.githubusercontent.com/acconeer/acconeer-python-exploration/8f633e02abac99ffec6fefec4339d13bc5c18388/docs/_static/gui.png" width=85%>
</p>

## Quickstart for Windows

There is a portable version of the Acconeer Exploration Tool for Windows:

* [Download](https://developer.acconeer.com/download/portable_exploration_tool-zip/) the zip file and extract
* Double click the `update.bat` file and wait for the installation to finish, which might take a couple of minutes
* Double click the `run_app.bat`

For an in-depth evaluation, we recommend a full installation as described below.

## Documentation

Documentation is available at [docs.acconeer.com](https://docs.acconeer.com),
where you can also find the [FAQ](https://docs.acconeer.com/en/latest/exploration_tool/faq.html).

## News

* v6.0.0 released. See the [Changelog](https://docs.acconeer.com/en/latest/changelog.html).

## Setting up your evaluation kit

* [XC120 + XE121 (A121)](https://docs.acconeer.com/en/latest/exploration_tool/evk_setup/xc120_xe121.html)
* [Raspberry Pi (A111 on XC111+XR111 or XC112+XR112)](https://docs.acconeer.com/en/latest/exploration_tool/evk_setup/raspberry_a111.html)
* [XM112](https://docs.acconeer.com/en/latest/exploration_tool/evk_setup/xm112.html)
* [XM122](https://docs.acconeer.com/en/latest/exploration_tool/evk_setup/xm122.html)
* [XM132](https://docs.acconeer.com/en/latest/exploration_tool/evk_setup/xm132.html)

For additional resources, head over to the [Acconeer developer page](https://developer.acconeer.com/). There you will find both a getting started guide and a video showing you how to set up your evaluation kit. There you will also find the SDK download.

## Setting up your local machine

### Requirements

Python 3.7 or newer. Older versions have limited or no support.

Tested on:

* Python 3 (developed and tested on 3.7, 3.8, 3.9, 3.10 and 3.11)
* Windows 10
* Ubuntu 20.04

### Setup

#### Installing the `acconeer-exptool` package

Install from PyPI:
```
python -m pip install --upgrade acconeer-exptool[app]
```
> *Depending on your environment, you might have to replace `python` with `python3` or `py`.*

For other options, have a look at
[docs.acconeer.com](https://docs.acconeer.com/en/latest/exploration_tool/installation_and_setup.html).

#### Windows COM port drivers

If no COM port is recognized when plugging in a module, you might need to install a driver.
See information about your specific module at
[docs.acconeer.com](https://docs.acconeer.com/en/latest/exploration_tool/installation_and_setup.html#windows-setup)


#### Linux setup

After installing the `acconeer-exptool` package, you can run

```
python -m acconeer.exptool.setup
```
> *Depending on your environment, you might have to replace `python` with `python3` or `py`.*

which interactively configures your machine and downloads needed dependencies.
This is done in order for your machine to work at its best with Exploration tool.
`acconeer.exptool.setup` performs the steps described in the
[Linux setup section on docs.acconeer.com](https://docs.acconeer.com/en/latest/exploration_tool/installation_and_setup.html#linux-setup).


## Application

Using the application is the easiest way to start exploring Acconeer's radar sensor and our application examples:
```
python -m acconeer.exptool.app
```
> *Depending on your environment, you might have to replace `python` with `python3` or `py`.*

In the top right box of the application, named _Connection_, select the interface you wish to use
- SPI: auto-detects an XM112 connected to USB2 (USB1 is also needed for power)
- Socket: specify the IP address of your Raspberry Pi running the streaming server
- Serial: specify the serial port that is assigned to the sensor

Connections via *Serial* have the option of choosing a *Protocol*. The choices are
**Module** and **Exploration**, where the protocol should match the server installed
on the module (*Module server* or *Exploration server*, respectively). Choosing the wrong
protocol will show an error.

After pressing _Connect_, a connection should be established.
In the box below labelled _Scan controls_, select the service or processing example you want to test.
Now you may tune the sensor and processing settings to your specific setup.
Once you press _Start measurement_, the application will start fetching data from the sensor and plotting the results.
After pressing _Stop_, you can save (and later load data) or just replay the data stored in the buffer.

### The ML interface *(no longer supported)*

Support for the Machine Learning interface in Exploration Tool has been dropped.

If you still need to use it, it is possible to use an old version of Exploration Tool.

From the `acconeer-python-exploration` directory:

```
git checkout v3
```

And follow the instructions in an old version of this document (`README.md`).

Note that this version of Exploration Tool will not be actively supported. Compatibility with new
RSS versions **is not guaranteed** .

## Running an example script on your local machine

If you prefer using the command line for testing and evaluation of our examples you can use the following instructions.

XC111+XR111 or XC112+XR112 (mounted on a Raspberry Pi):

```
python examples/a111/basic.py -s <your Raspberry Pi IP address>
```

XM112+XB112 via SPI over USB:

```
python examples/a111/basic.py -spi
```

Any module via UART over USB, attempting to auto-detect the serial port:

```
python examples/a111/basic.py -u
```

Any module via UART over USB, using a specific serial port:

```
python examples/a111/basic.py -u <the serial port, for example COM3>
```

> *Depending on your environment, you might have to replace `python` with `python3` or `py`.*

Choosing which sensor(s) to be used can be done by adding the argument `--sensor <id 1> [id 2] ...`. The default is the sensor on port 1. This is not applicable for the modules.

Scripts can be terminated by pressing Ctrl-C in the terminal.

## Disclaimer

Here you find the [disclaimer](https://docs.acconeer.com/en/latest/disclaimer.html).

## FAQ and common issues

See the [FAQ](https://docs.acconeer.com/en/latest/exploration_tool/faq.html) on the Acconeer documentation pages.
