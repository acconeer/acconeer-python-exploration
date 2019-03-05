# Acconeer Exploration Tool

Acconeer Python Exploration Kit is a set of tools and examples for getting started with the Acconeer Evaluation kits. By seamlessly feeding radar data to your local machine, it allows you to quickly start exploring the world of Acconeer's radar sensor technology. This repository serves as a good starting point both for evaluation purposes and algorithm development in Python.

To run the exploration scripts, you will need an Acconeer Evaluation kit running the Streaming or Module server supplied with the Acconeer SDK or Module software image.

This release supports Acconeer SDK and Module SW version 1.5.2 or newer.

## Setting up your evaluation kit

For general help on getting started, head over to the [Acconeer website](https://www.acconeer.com/products). There you'll find both a getting started guide and a video showing you how to set up your evaluation kit. There you'll also find the SDK download.

### XC111+XR111 or XC112+XR112 (mounted on a Raspberry Pi)

#### Overview

At large, these are the steps you'll need to take:

* Assemble your evaluation kit
* Set up your Raspberry Pi
* Load the Acconeer Raspberry Pi SDK onto your Raspberry Pi
* Run the streaming server application on your Raspberry Pi

For a single sensor setup, we recommend plugging the sensor into port 1 for simplicity's sake.

#### Running the streaming server application

For the XC112+XR112 kit, start the streaming server application on your Raspberry Pi located under `utils` in `AcconeerEvk`:
```
$ cd AcconeerEvk
$ ./utils/acc_streaming_server_rpi_xc112_r2b_xr112_r2b_a111_r2c
```
If you have an XC111+XR111 kit, the streaming server will instead be named `acc_streaming_server_rpi_xc111_r4a_xr111-3_r1c_a111_r2c`.

Find the IP address of your Raspberry Pi by running `ifconfig` in its terminal.

### XM112

#### Finding the serial port

On Windows, use device manager to find the port which will be listed as `USB Serial Port`. It's most likely `COMx` where `x` is 3 or higher. On Linux, it's likely `/dev/ttyUSBx` where `x` is 0 or higher.

PySerial has a simple tool for listing all ports available:
```
python -m serial.tools.list_ports
```

#### Flashing

For detailed flashing instructions, head over to the [Acconeer website](https://www.acconeer.com/products).

We recommend flashing using BOSSA ([website](http://www.shumatech.com/web/products/bossa), [GitHub](https://github.com/shumatech/BOSSA)). BOSSA 1.9 or newer is supported.

To get into the bootloader:
- Hold down the ERASE button
- Push the NRST button
- Release the NRST button
- Let go of the ERASE button

Now you should be able to flash the Module software (`acc_module_server_xm112.bin`). After flashing, press the NRST button to reboot into the flashed software.

If you're on Linux you likely will need to compile BOSSA on your own. In our experience, running Ubuntu 18.04, you will need to install `libreadline-dev` and `libwxgtk3.0-dev` before compiling with `make`. To get everything you need:
```
sudo apt-get install libreadline-dev libwxgtk3.0-dev make build-essential
```
To flash:
```
sudo ./bin/bossac -e -w -v -p /dev/ttyUSB0 -b /path/to/acc_module_server_xm112.bin
```

## Setting up your local machine

### Dependencies

Python 3 (developed and tested on 3.6).

Setuptools, NumPy, SciPy, PySerial, matplotlib, PyQtGraph (and PyQt5).

Install all Python dependencies using pip:

```
python -m pip install --user -r requirements.txt
```
_Depending on your environment, you might have to replace `python` with `python3` or `py`._

### Setup

Install the supplied Acconeer utilities module:
```
python setup.py install --user
```
Please note that the utilities module has to be reinstalled after any change in `acconeer_utils`.

If you're running Linux together with the XM112, you probably need permission to access the serial port. Access is obtained by adding yourself to the dialout group:
```
sudo usermod -a -G dialout your-user-name
```
For the changes to take effect, you will need to log out and in again.

Note: If you have ModemManager installed and running it might try to connect to the XM112, which has proven to cause problems. If you're having issues, try disabling the ModemManager service.

## Running an example on your local machine

Against XC111+XR111 or XC112+XR112 (mounted on a Raspberry Pi):
```
python examples/basic.py -s <your Raspberry Pi IP address>
```
Against XM112, autodetecting the serial port:
```
python examples/basic.py -u
```
Against XM112, given a serial port (on Windows):
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

- `power_bin.py` \
  Demonstrates the power bin service.
- `envelope.py` \
  Demonstrates the envelope service.
- `iq.py` \
  Demonstrates the IQ service.

### Detectors

Acconeer's detectors are **only** supported with the XM112 Module.

- `distance_peak_fix_threshold.py` \
  Demonstrates the *distance peak* detector.

### Processing

- `breathing.py` \
  An example breathing detection algorithm.
- `sleep_breathing.py` \
  An example of a "sleep breathing" detection algorithm assuming that the person is still (as when in sleep) where only the motion from breathing is to be detected.
- `phase_tracking.py` \
  An example of a relative movements tracking algorithm using phase information.
- `presence_detection.py` \
  An example of a presence/motion detection algorithm based on **phase** changes in the received signal over time. Small changes/motions in front of the sensor are enough to trigger the detector. Further, static objects are ignored. A typical use case is to detect a person based on the small motions origin from the breathing and pulse.
- `motion_large.py` \
  An example of a presence/motion detection algorithm based on **power** changes in the received signal over time. Large changes/motions in front of the sensor are required to trigger the detector. Further, static objects are ignored but could reduce the sensitivity due to increased received average power. A typical use case is to detect a person walking up to or away from the sensor's coverage region. It will not detect small motions as breathing or pulse from a person standing in front of the sensor, which is the case for the _presence_detection.py_.
- `obstacle_detection.py` \
  An example of a obstacle detection algorithm estimating the distance and angle to an apporaching obstacle. It is based the synthetic aperture radar (SAR) principle.

### Plotting

- `plot_with_matplotlib.py` \
  Example of how to use matplotlib for plotting.
- `plot_with_mpl_process.py` \
  Example of how to use the mpl_process (matplotlib process) module for plotting.
- `plot_with_pyqtgraph.py` \
  Example of how to use PyQtGraph for plotting.

## GUI (beta)

Run the GUI using:
```
python gui/main.py
```

Running examples in the GUI under Windows can be very slow. If you encounter lag in the GUI try reducing the sweep buffer in the GUI or running the examples directly as described above.

## Radar viewer

The radar viewer visualizes the output from Acconeer's service API:s in your default browser.

Currently **only the XM112 module is supported**.

Run the radar viewer using:
```
python radar_viewer/radar_viewer.py -u
```

## FAQ and common issues

### Python-related

1) Import errors with NumPy on Linux

    The solution is to remove all duplicates of NumPy:
    ```
    sudo apt-get remove python3-numpy
    python3 -m pip list | grep numpy
    # Look for duplicate versions of numpy x.xx.x
    # If numpy is installed several times, remove older versions
    python3 -m pip uninstall numpy=x.xx.x
    # If no numpy is installed, install latest
    python3 -m pip install numpy
    ```
