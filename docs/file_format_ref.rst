File format reference
=====================

This page explains the format of data files saved from Exploration Tool using the GUI or recording module.

The data files store a ``Record``, a simple key-value store containing the fields shown further down.
Either HDF5 ``.h5`` or NumPy ``.npz`` can be used to save it,
although HDF5 is preferred due to its wider compatibility across systems and languages.

We recommend loading and saving records using the ``load`` and ``save`` functions in the ``acconeer.exptool.recording`` module.
These functions take care of packing and unpacking the ``Record`` fields on save and load respectively.
See `utils/load_record.py <https://github.com/acconeer/acconeer-python-exploration/blob/master/utils/load_record.py>`__
for an example of loading data,
and `examples/record_data/barebones.py <https://github.com/acconeer/acconeer-python-exploration/blob/master/examples/record_data/barebones.py>`__
for saving data.

For an example of how to load HDF5 records in Matlab, see `utils/load_record_h5.m <https://github.com/acconeer/acconeer-python-exploration/blob/master/utils/load_record_h5.m>`__.

Examples of loading
-------------------

Some minimal examples of loading the session info from a data file:

Using ``acconeer.exptool.recording.load`` (recommended):

.. code-block:: python

   import acconeer.exptool as et
   record = et.recording.load("data.h5")  # or .npz
   print(record.session_info)
   # {'data_length': 1238, 'range_length_m': 0.6, ...

Using ``h5py``:

.. code-block:: python

   import json
   import h5py
   with h5py.File("data.h5") as f:
      print(json.loads(f["session_info"][()]))
   # {'data_length': 1238, 'range_length_m': 0.6, ...

Using ``numpy``:

.. code-block:: python

   import json
   import numpy as np
   with np.load("data.npz") as f:
      print(json.loads(str(f["session_info"])))
   # {'data_length': 1238, 'range_length_m': 0.6, ...

Fields
------

The *type* here refers to the *packed* type - the type the value has in the stored file.

Sensor related
^^^^^^^^^^^^^^

The following fields are used for storing the sensor session data itself.
These fields are the only ones that are mandatory.

``mode``
   Type: string

   The mode (service) used in the recording.
   For example ``"sparse"``.
   Unpack the original enum member using ``acconeer.exptool.a111.get_mode`` on this field.

``sensor_config_dump``
   Type: string

   A JSON dump of the sensor configuration.
   Load the original sensor configuration using ``acconeer.exptool.configs.load`` on this field.
   It can also be loaded to a dict using ``json.loads``.

   .. tip::

      With a record you can quickly access the sensor configuration with ``record.sensor_config``.

``session_info``
   Type: string

   A JSON dump of the session information (metadata).
   Unpack the original dict using ``json.loads``.

``data``
   Type: ND array of numbers

   An N-dimensional array containing all data from the sensor(s).
   The shape and data type depends on the mode used.

   Power bins
      | Shape: (number of sweeps, number of sensors, number of distance bins)
      | Type: uint16 (previously float64)

   Envelope
      | Shape: (number of sweeps, number of sensors, number of distances)
      | Type: uint16 (previously float64)

   IQ
      | Shape: (number of sweeps, number of sensors, number of distances)
      | Type: complex128

   Sparse
      | Shape: (number of frames, number of sensors, sweeps per frame, number of distances)
      | Type: uint16 (previously float64)

``data_info``
   Type: string

   A JSON dump of all data information (result_infos).
   Unpack with ``json.loads`` to a nested list of list of dicts.

   The shape of the nested list is (number of frames/sweeps, number of sensors).
   The fields of the dicts depend on mode/service.

Processing related
^^^^^^^^^^^^^^^^^^

The following fields are used for storing metadata for processing.
These fields are optional.

``module_key``
   Type: string

   Key of the processing module used during the recording.
   For example ``sparse_presence``.
   The keys are defined in respective ``_meta.py`` files;
   e.g. ``src/acconeer/exptool/a111/algo/presence_detection_sparse/_meta.py``.

``processing_config_dump``
   Type: string

   A JSON dump of the processing configuration.

   Load the original processing configuration using ``ProcessingConfig._load`` on this field.
   Here, ``ProcessingConfig`` refers to the subclassed ``acconeer.exptool.configbase.ProcessingConfig`` for the processing module used.
   For example, ``ProcessingConfiguration`` in `presence_detection_sparse.py <https://github.com/acconeer/acconeer-python-exploration/blob/bd9dc6d909e89c152b9831e5ce5999834430f3d3/examples/processing/presence_detection_sparse.py#L68>`__.

   .. note::
      The referenced ``ProcessingConfiguration`` is of an old version, mainly meant for illustrative
      purposes.

      Please refer to the :ref:`changelog` in order to find the corresponding file in v4.

   This field can also be loaded to a dict using ``json.loads``.

Other
^^^^^

The following optional fields are used for storing other metadata for the recording.

``rss_version``
   Type: string

   The server/RSS version used on the host (module, RPi, etc.).

``lib_version``
   Type: string

   The Exploration Tool library version used on the PC.

``timestamp``
   Type: string

   ISO formatted time at the start of recording.
   For example ``"2020-12-31T23:59:59"``.

``sample_times``
   Type: 1D array of floats

   The time in seconds for every return of a sweep/frame from ``get_next``.
   Typically timed using Python's ``time.time``, meaning it will be the time since the epoch.

   .. caution::

      Since this is timed on the client side, the timing may significantly differ from the timing when the radar actually sampled the data.
      Thus, we recommend only using this for calculating **average** sampling rate.

``note``
   Type: string

   Free text field.
   Not used by Exploration Tool itself.

Legacy
^^^^^^

The following optional fields are used by legacy components of Exploration Tool.

``legacy_processing_config_dump``
   Type: string

   A JSON dump of a legacy processing configuration.
