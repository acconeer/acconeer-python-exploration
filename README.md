acconeer-python-exploration
---------------------------

Acconeer Python Exploration Kit is a set of tools and examples for getting started with the Acconeer development kits. By seamlessly streaming radar data to your local machine, you can quickly start exploring what the sensor is capable of and start developing algorithms on your own.

## Prerequisites
### Overview

To run the exploration scripts, you'll need an Acconeer development kit running the streaming server supplied with the Acconeer A1 SDK.

For help on getting started, head over to the [Acconeer website](https://www.acconeer.com/products). There you'll find both a getting started guide and a video showing you how to set up your development kit. There you'll also find the SDK download. At large, these are the steps you'll need to take:

* Assemble your development kit
* Set up your Raspberry Pi
* Load the Acconeer A1 SDK onto your Raspberry Pi
* Run the streaming server

This release supports SDK version 1.3.9 or newer (developed and tested on 1.3.9).

### Running the streaming server

On your Raspberry Pi, start the streaming server located under `utils` in `AcconeerEvk`:
```
$ cd AcconeerEvk
$ ./utils/acc_streaming_server_rpi_xc112_r2b_xr112_r2b_a111_r2c
```
If you have an X111 kit, the streaming server will instead be named `acc_streaming_server_rpi_xc111_r4a_xr111-3_r1c_a111_r2c`.

Find the IP address of your Raspberry Pi by running `ifconfig` in the terminal.

## Dependencies

Python 3 (developed and tested on 3.6).

Setuptools, NumPy, matplotlib, PyQtGraph (and PyQt5). Install using pip:
```
pip install --user -r requirements.txt
```
_Depending on your environment, you might have to replace `pip` with `pip3`._

## Setup

Install the supplied Acconeer utilities module:

```
python setup.py install --user
```

_Depending on your environment, you might have to replace `python` with `python3`._

## Running an example

To run an example:
```
python examples/simple_data_dump.py <host> [<sensor>]
```
For example:
```
python examples/simple_data_dump.py 192.168.1.234 2
```
_Again, depending on your environment, you might have to replace `python` with `python3`._

If no sensor id is given, the example will default to 1.

Scripts can be terminated using Ctrl-C in the terminal.

## Examples
- `simple_data_dump.py` \
  A bare bones script for getting envelope data from the radar.
- `movement.py` \
  Shows one way to perform movement detection while ignoring static objects.
- `plot_iq_data_with_matplotlib.py` \
  Example of how to use matplotlib for plotting IQ data.
- `plot_iq_data_with_mpl_process.py` \
  Example of how to use the supplied matplotlib process module for plotting IQ data.
- `plot_iq_data_with_pyqtgraph.py` \
  Example of how to use PyQtGraph for plotting IQ data.
