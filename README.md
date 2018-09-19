acconeer-python-exploration
---------------------------

## Dependencies

Acconeer A1 SDK 1.3.9 or newer.

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

## Getting started
### Setting up the SDK on your Raspberry Pi

For SDK download and help on getting started, head over to the [Acconeer website](https://www.acconeer.com/products).

### Running the streaming server

The example programs require access to the Acconeer streaming server running on your Raspberry Pi. On your Raspberry Pi, start the streaming server located under `utils` in `AcconeerEvk`:
```
$ cd AcconeerEvk
$ ./utils/acc_streaming_server_xc112
```
If you're using another connector board than XC112, replace `xc112` above with your model.

Find the IP address of your Raspberry Pi by running `ifconfig` in the terminal.

### Running an example

To run an example:
```
python examples/simple_data_dump.py <host> [<sensor>]
```
For example:
```
python examples/simple_data_dump.py 192.168.1.234 2
```
If no sensor id is given, the example will default to 1.

_Depending on your environment, you might have to replace `python` with `python3`._

Scripts can be terminated using Ctrl-C in the terminal.
