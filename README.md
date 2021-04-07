# Acconeer Exploration Tool

_**Explore the Next Sense**_ with Acconeer's Python Exploration Tool! Use one of our [evaluation kits](https://www.acconeer.com/products) together with our Python examples and start exploring the world of Acconeer's radar sensor technology. The Python scripts and GUI in this repository will help you to easily stream the radar sensor's data to your local machine to start radar sensor evaluation and/or algorithm development for your application.

To run the Python exploration scripts, you will need an [evaluation kit](https://www.acconeer.com/products) running the included Streaming or Module server, which are supplied with the [Acconeer SDK and Module SW](https://developer.acconeer.com/) image.

This release is developed for [Acconeer SDK and Module SW](https://developer.acconeer.com/) **version 2.8.0**.
Running this version is strongly recommended, as we continuously fix bugs and add features.

<p align="center">
  <img alt="The GUI in action" src="docs/_static/gui.png" width=85%>
</p>

## Quickstart for Windows

There is a portable version of the Exploration Tool for Windows:

* [Download](https://developer.acconeer.com/download/portable_exploration_tool-zip/) the zip file and extract
* Double click the `update.bat` file and wait for the installation to finish, which takes a couple of minutes
* Double click the `run_gui.bat`

For an in-depth evaluation we recommend a full installation as described below.

## Documentation

Additional documentation is available [here](https://acconeer-python-exploration.readthedocs.io).

## Setting up your evaluation kit

* [Raspberry Pi (XC111+XR111 or XC112+XR112)](https://acconeer-python-exploration.readthedocs.io/en/latest/evk_setup/raspberry.html)
* [XM112](https://acconeer-python-exploration.readthedocs.io/en/latest/evk_setup/xm112.html)
* [XM122](https://acconeer-python-exploration.readthedocs.io/en/latest/evk_setup/xm122.html)
* [XM132](https://acconeer-python-exploration.readthedocs.io/en/latest/evk_setup/xm132.html)

For general help on getting started head over to the [Acconeer developer page](https://developer.acconeer.com/). There you will find both a getting started guide and a video showing you how to set up your evaluation kit. There you will also find the SDK download.

## Setting up your local machine

### Requirements

Python 3.7 or newer. Older versions have limited or no support.

Tested on:

* Python 3 (developed and tested on 3.7, 3.8 and 3.9)
* Windows 10
* Ubuntu 18.04 and 20.04
* WSL (Windows Subsystem for Linux)

### Setup

#### Dependencies

All Python package dependencies are listed in `requirements.txt`. Install them using pip:
```
python -m pip install -U --user setuptools wheel
python -m pip install -U --user -r requirements.txt
```
Depending on your environment, you might have to replace `python` with `python3` or `py`.

If you have PyQt4 installed, it might conflict with PyQt5. If this is the case for you, we recommend using virtual environments to separate the two installations.

To run the GUI on Ubuntu 20.04, `libxcb-xinerama0-dev` needs to be installed:
```
sudo apt update
sudo apt install -y libxcb-xinerama0-dev
```

#### Installing the acconeer.exptool library

Install the supplied library `acconeer.exptool`:
```
python -m pip install -U --user .
```
**Note: The library has to be reinstalled after any change under `src/`, and it is therefore recommended to reinstall after every update.**

#### Windows COM port drivers

If no COM port is recognized when plugging in a module, you might need to install a driver:

* XM112, XM122: [FTDI](https://ftdichip.com/drivers/vcp-drivers/)
* XM132: [Silicon Labs](https://www.silabs.com/developers/usb-to-uart-bridge-vcp-drivers)

#### Connecting to a module through UART on Linux

If you are running Linux together with an XM112, XM122, or XM132 module through UART, you probably need permission to access the serial port. Access is obtained by adding yourself to the dialout group:
```
sudo usermod -a -G dialout $USER
```
For the changes to take effect, you will need to log out and in again.

Note: If you have ModemManager installed and running it might try to connect to the module, which has proven to cause problems. If you are having issues, try disabling the ModemManager service.

#### Connecting to an XM112 through SPI on Linux

If you are using Linux together with an XM112, you probably need permission to access the SPI bridge USB device. Either run the scripts with `sudo`, or create an udev rule as follows. Create and edit:
```
sudo nano /etc/udev/rules.d/50-ft4222.rules
```
with the following content:
```
SUBSYSTEM=="usb", ATTRS{idVendor}=="0403", ATTRS{idProduct}=="601c", MODE:="0666"
```
This method is confirmed to work for **Ubuntu 18.04 and 20.04**.

Note: SPI is not supported under WSL.

## GUI

Using the GUI is the easiest way to start exploring Acconeer's radar sensor and our application examples:
```
python gui/main.py
```

In the top right box of the GUI, named _Connection_, select the interface you wish to use
- SPI: auto-detects an XM112 connected to USB2 (USB1 is also needed for power)
- Socket: specify the IP address of your Raspberry Pi running the streaming server
- Serial: specify the serial port that is assigned to the sensor

After pressing _Connect_, a connection should be established.
In the box below labeled _Scan controls_, select the service or processing example you want to test.
Now you may tune the sensor and processing settings to your specific setup.
Once you press _Start measurement_, the application will start fetching data from the sensor and plotting the results.
After pressing _Stop_, you can save (and later load data) or just replay the data stored in the buffer.

Except for Envelope, IQ, Power bins, and Sparse, the GUI is loading modules from the examples directory.
If you modify code in those files, the changes will appear in the GUI once you reload it.

EXPERIMENTAL deep learning:

If you want to test our new deep learning interface please install additional requirements
```
python -m pip install -U --user -r requirements_ml.txt
```
This will install Keras, TensorFlow and Scikit-learn.
You can then start the machine learning GUI with
```
python gui/main.py -ml
```
Please keep in mind that the deep learning interface is "work in progress"; initial documentation is available here ([doc](https://acconeer-python-exploration.readthedocs.io/en/latest/deep_learning/introduction.html)).

## Running an example script on your local machine

If you prefer using the command line for testing and evaluation of our examples you can use the following instructions.

XC111+XR111 or XC112+XR112 (mounted on a Raspberry Pi):
```
python examples/basic.py -s <your Raspberry Pi IP address>
```
XM112+XB112 via SPI over USB:
```
python examples/basic.py -spi
```
Any module via UART over USB, attempting to auto-detect the serial port:
```
python examples/basic.py -u
```
Any module via UART over USB, using a specific serial port:
```
python examples/basic.py -u <the serial port, for example COM3>
```
_Again, depending on your environment, you might have to replace `python` with `python3` or `py`._

Choosing which sensor(s) to be used can be done by adding the argument `--sensor <id 1> [id 2] ...`. The default is the sensor on port 1. This is not applicable for the modules.

Scripts can be terminated by pressing Ctrl-C in the terminal.

## Examples

### Basic

The basic scripts contains a lot of comments guiding you through the steps taken in most example scripts. We recommend taking a look at these scripts before working with the others.

- `basic.py` \
  Basic script for getting data from the radar. **Start here!**
- `basic_continuous.py` \
  Basic script for getting data continuously that serves as the base for most other examples.

### Services

- `power_bins.py` ([doc](https://acconeer-python-exploration.readthedocs.io/en/latest/services/pb.html)) \
  Demonstrates the power bins service.
- `envelope.py` ([doc](https://acconeer-python-exploration.readthedocs.io/en/latest/services/envelope.html)) \
  Demonstrates the envelope service.
- `iq.py` ([doc](https://acconeer-python-exploration.readthedocs.io/en/latest/services/iq.html)) \
  Demonstrates the IQ service.
- `sparse.py` ([doc](https://acconeer-python-exploration.readthedocs.io/en/latest/services/sparse.html)) \
  Demonstrates the Sparse service.

### Processing

- `breathing.py` \
  An example breathing detection algorithm.
- `button_press.py` ([doc](https://acconeer-python-exploration.readthedocs.io/en/latest/processing/button_press.html)) \
  An example of a "button press" detection algorithm detecting a motion at short distances (~3-5 cm) based on the envelope service, which could be used as "hidden" touch buttons.
- `distance_detector.py` ([doc](https://acconeer-python-exploration.readthedocs.io/en/latest/processing/distance_detector.html)) \
  An example of the envelope-based distance detection algorithm that estimates the distance to an object.
- `obstacle_detection.py` ([doc](https://acconeer-python-exploration.readthedocs.io/en/latest/processing/obstacle.html)) \
  An example of an obstacle detection algorithm estimating the distance and angle to an approaching obstacle.
- `phase_tracking.py` ([doc](https://acconeer-python-exploration.readthedocs.io/en/latest/processing/phase_tracking.html)) \
  An example of a relative movements tracking algorithm using phase information.
- `presence_detection_sparse.py` ([doc](https://acconeer-python-exploration.readthedocs.io/en/latest/processing/presence_detection_sparse.html)) \
  An example of a presence/motion detection algorithm based on the sparse service.
- `sleep_breathing.py` ([doc](https://acconeer-python-exploration.readthedocs.io/en/latest/processing/sleep_breathing.html)) \
  An example of a "sleep breathing" detection algorithm assuming that the person is still (as when in sleep) where only the motion from breathing is to be detected.
- `sparse_fft.py` \
  An example of a frequency analyzer to get an idea of the frequency content in the sparse service data.
- `sparse_inter_fft.py` \
  Another example of a frequency analyzer which keeps a history of frequency data at different distances.
- `sparse_speed.py` \
  An example of a speed detection algorithm estimating speeds of an approaching object based on the sparse service.

### Record data

- `barebones.py` \
  A barebones stub that demonstrates how to save sensor data to file.
- `with_cli.py` \
  A stub for saving sensor data to file that uses command line arguments
  allowing you to set the filename, etc.
- `long_duration_split_files.py` \
  A stub that demonstrates how you can split one recording session into multiple files.

### Plotting

- `plot_with_matplotlib.py` \
  Example of how to use matplotlib for plotting.
- `plot_with_mpl_process.py` \
  Example of how to use the mpl_process (matplotlib process) module for plotting.
- `plot_with_pyqtgraph.py` \
  Example of how to use PyQtGraph for plotting.

## Radar viewer

The radar viewer visualizes the output from Acconeer's service API:s in your default browser.

Run the radar viewer using:
```
python radar_viewer/radar_viewer.py -u
```
The usage of arguments is the same as for the examples.

## Disclaimer

Here you find the [disclaimer](https://acconeer-python-exploration.readthedocs.io/en/latest/disclaimer.html).

## FAQ and common issues

We've moved the FAQ to [Read the Docs](https://acconeer-python-exploration.readthedocs.io/en/latest/faq.html).
