# Acconeer Exploration Kit

_**Explore the Next Sense**_ with Acconeer's Python Exploration Kit! Use one of our [evaluation kits](https://www.acconeer.com/products) together with our Python examples and start exploring the world of Acconeer's radar sensor technology. The Python scripts and GUI in this repository will help you to easily stream the radar sensor's data to your local machine and begin evaluation and algorithm development for your application.

To run the Python exploration scripts, you will need an [evaluation kit](https://www.acconeer.com/products) running the included Streaming or Module server, which are supplied with the [Acconeer SDK and Module SW](https://developer.acconeer.com/) image.

This release is developed for [Acconeer SDK and Module SW](https://developer.acconeer.com/) **version 1.7.1**.
Running this version is strongly recommended, as we continuously fix bugs and add features. The minimum version supported is 1.5.2.

## Documentation

Additional documentation is available on [Read the Docs](https://acconeer-python-exploration.readthedocs.io).

## Setting up your evaluation kit

* [Raspberry Pi (XC111+XR111 or XC112+XR112)](https://acconeer-python-exploration.readthedocs.io/en/latest/evk_setup/raspberry.html)
* [XM112](https://acconeer-python-exploration.readthedocs.io/en/latest/evk_setup/xm112.html)

For general help on getting started head over to the [Acconeer developer page](https://developer.acconeer.com/). There you will find both a getting started guide and a video showing you how to set up your evaluation kit. There you will also find the SDK download.

## Setting up your local machine

### Requirements

Tested on:

* Python 3 (developed and tested on 3.6 and 3.7)
* Windows 10
* Ubuntu 18.04
* WSL (Windows Subsystem for Linux)

### Setup

#### Dependencies

Setuptools, wheel, NumPy, SciPy, PySerial, matplotlib, PyQtGraph, PyQt5, h5py, Flask.

If you have PyQt4 installed, it might conflict with PyQt5. If this is the case for you, we recommend using `virtualenv` to separate the two installations.

Install all Python dependencies using pip:
```
python -m pip install --user setuptools wheel
python -m pip install --user -r requirements.txt
```
_Depending on your environment, you might have to replace `python` with `python3` or `py`._

#### Installing acconeer_utils

Install the supplied Acconeer utilities module `acconeer_utils`:
```
python setup.py install --user
```
Please note that the utilities module has to be reinstalled after any change in `acconeer_utils`.

#### XM112+XB112 serial on Linux

If you are running Linux together with the XM112, you probably need permission to access the serial port. Access is obtained by adding yourself to the dialout group:
```
sudo usermod -a -G dialout your-user-name
```
For the changes to take effect, you will need to log out and in again.

Note: If you have ModemManager installed and running it might try to connect to the XM112, which has proven to cause problems. If you are having issues, try disabling the ModemManager service.

#### XM112+XB112 SPI

If you are using Linux together with the XM112+XB112, you probably need permission to access the SPI bridge USB device. Either run the scripts with `sudo`, or create an udev rule as follows. Create and edit:
```
sudo nano /etc/udev/rules.d/50-ft4222.rules
```
with the following content:
```
SUBSYSTEM=="usb", ATTRS{idVendor}=="0403", ATTRS{idProduct}=="601c", MODE:="0666"
```
This method is confirmed to work for **Ubuntu 18.04**.

Note: SPI is not supported under WSL.

## Running an example on your local machine

XC111+XR111 or XC112+XR112 (mounted on a Raspberry Pi):
```
python examples/basic.py -s <your Raspberry Pi IP address>
```
XM112+XB112 via SPI over USB:
```
python examples/basic.py -spi
```
XM112+XB112 via UART over USB, autodetecting the serial port:
```
python examples/basic.py -u
```
XM112+XB112 via UART over USB, using a specific serial port:
```
python examples/basic.py -u <your XM112 COM port e.g. COM3>
```
_Again, depending on your environment, you might have to replace `python` with `python3` or `py`._

Choosing which sensor(s) to be used can be done by adding the argument `--sensor <id 1> [id 2] ...`. The default is the sensor on port 1. This is not applicable for XM112.

Scripts can be terminated by pressing Ctrl-C in the terminal.

## Examples

### Basic

The basic scripts contains a lot of comments guiding you through the steps taken in most example scripts. We recommend taking a look at these scripts before working with the others.

- `basic.py` \
  Basic script for getting data from the radar. **Start here!**
- `basic_continuous.py` \
  Basic script for getting data continuously that serves as the base for most other examples.

### Services

- `power_bin.py` ([doc](https://acconeer-python-exploration.readthedocs.io/en/latest/services/pb.html)) \
  Demonstrates the power bin service.
- `envelope.py` ([doc](https://acconeer-python-exploration.readthedocs.io/en/latest/services/envelope.html)) \
  Demonstrates the envelope service.
- `iq.py` ([doc](https://acconeer-python-exploration.readthedocs.io/en/latest/services/iq.html)) \
  Demonstrates the IQ service.

### Processing

- `breathing.py` \
  An example breathing detection algorithm.
- `sleep_breathing.py` \
  An example of a "sleep breathing" detection algorithm assuming that the person is still (as when in sleep) where only the motion from breathing is to be detected.
- `presence_detection.py` ([doc](https://acconeer-python-exploration.readthedocs.io/en/latest/processing/presence_detection.html)) \
  An example of a presence/motion detection algorithm based on **phase** changes in the received signal over time.
- `motion_large.py` ([doc](https://acconeer-python-exploration.readthedocs.io/en/latest/processing/motion_large.html)) \
  An example of a presence/motion detection algorithm based on **power** changes in the received signal over time.
- `phase_tracking.py` ([doc](https://acconeer-python-exploration.readthedocs.io/en/latest/processing/phase_tracking.html)) \
  An example of a relative movements tracking algorithm using phase information.
- `obstacle_detection.py` ([doc](https://acconeer-python-exploration.readthedocs.io/en/latest/processing/obstacle.html)) \
  An example of an obstacle detection algorithm estimating the distance and angle to an approaching obstacle.

### Plotting

- `plot_with_matplotlib.py` \
  Example of how to use matplotlib for plotting.
- `plot_with_mpl_process.py` \
  Example of how to use the mpl_process (matplotlib process) module for plotting.
- `plot_with_pyqtgraph.py` \
  Example of how to use PyQtGraph for plotting.

## GUI

Run the GUI using:
```
python gui/main.py
```

Running examples in the GUI under Windows can be very slow. If you encounter lag in the GUI try reducing the sweep buffer in the GUI or running the examples directly as described above.

## Radar viewer

The radar viewer visualizes the output from Acconeer's service API:s in your default browser.

Currently **only the XM112+XB112 module is supported**.

Run the radar viewer using:
```
python radar_viewer/radar_viewer.py -u
```

## FAQ and common issues

We've moved the FAQ to [Read the Docs](https://acconeer-python-exploration.readthedocs.io/en/latest/faq.html).
