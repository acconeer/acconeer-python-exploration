.. _configure-sensor:

Configure the sensor
====================
The GUI allows you to easily configure all the settings available for the different services.
There are 3 tabs on the side-panel of the GUI for these settings, one for the standard settings, one for advanced settings and one for the session meta data.

In the following, all sensor settings are described briefly.
Since most of them are service-specific, you also get further information by reading the details about each service (:ref:`envelope-service`, :ref:`iq-service`, :ref:`sparse-service`).

.. tip::
    For most options, hovering the mouse over the setting in the GUI will bring up a help box explaining the setting

When you start the GUI for the first time, you will be presented with the default settings for each parameter.
However, the GUI will store any change in settings per Service/Detector and restore them even after restarting the GUI.

.. tip::
    Click on the **Default** button to restore the sensor default settings for the current service/detector!
    If you want to undo all changes, remove *last_config.npy* in the gui folder, which stores all your settings.


Sensor settings
---------------
.. _sensor-settings-standard:
.. figure:: /_static/gui/sensor_settings_standard.png
    :figwidth: 40%
    :align: right

    Sensor settings (standard) in the GUI

Sensor
^^^^^^
Depending on the service/detector/hardware selected, you can choose between 1 and 4 sensors to be used simultaneously.

Range interval
^^^^^^^^^^^^^^
.. automodule:: acconeer.exptool.configs.BaseServiceConfig.range_interval.help_obj

The exact values will be displayed in the **Session meta data** tab after the scan has started.

Profile
^^^^^^^
.. automodule:: acconeer.exptool.configs.BaseServiceConfig.profile.help_obj

For more information on profiles please see the :ref:`Sensor introduction<sensor-introduction-pofiles>`


Update rate
^^^^^^^^^^^^^
.. automodule:: acconeer.exptool.configs.BaseServiceConfig.update_rate.help_obj

A frame contains the range data specific to each service.

a) :ref:`envelope-service`: a frame contains the amplitude for the selected distance range. The distance points are separated by approximately :math:`0.5,\text{mm}` (when using a downsampling factor of 1).
b) :ref:`pb-service`: same as Envelope, but in histogram format, i.e. distance points are grouped together in bins and amplitudes are averages for each bin. It can be seen as a more light weight alternative to the Envelope Service with less data processing in the host, but slightly lower signal quality.
c) :ref:`iq-service`: a frame contains the amplitude and phase in the form of rectangular complex numbers for the selected distance range. The distance points are separated by approximately :math:`0.5,\text{mm}`.
d) :ref:`sparse-service`: a frame includes several sweeps containing amplitude values for the selected distance range. The distance points are separated by approximately :math:`60,\text{mm}`

Sweep rate and Sweeps per frame (Sparse only)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
.. automodule:: acconeer.exptool.configs.SparseServiceConfig.sweep_rate.help_obj

The actual sweep rate will be displayed in the **Session meta data** tab after the scan has been started.

Running avg. factor (Envelope only)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
To remove high frequency amplitude variations in the signal and increase the SNR, the sweeps in the Envelope Service can be time filtered with a standard exponential smoothening filter.

Check the description for the :ref:`Envelope Service <envelope-service>` for more information.

Bin count (Power bins only)
^^^^^^^^^^^^^^^^^^^^^^^^^^^
.. automodule:: acconeer.exptool.configs.PowerBinServiceConfig.bin_count.help_obj


Advanced sensor settings
------------------------
.. _sensor-settings-advanced:
.. figure:: /_static/gui/sensor_settings_advanced.png
    :figwidth: 40%
    :align: right

    Sensor settings (advanced) in the GUI

Sampling mode (Sparse only)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
.. automodule:: acconeer.exptool.configs.SparseServiceConfig.sampling_mode.help_obj

Repetition Mode:
^^^^^^^^^^^^^^^^
.. automodule:: acconeer.exptool.configs.BaseServiceConfig.repetition_mode.help_obj

Downsampling factor
^^^^^^^^^^^^^^^^^^^
.. automodule:: acconeer.exptool.configs.BaseServiceConfig.downsampling_factor.help_obj


HW accel. average samples (HWAAS)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
.. automodule:: acconeer.exptool.configs.BaseServiceConfig.hw_accelerated_average_samples.help_obj


Gain
^^^^
.. automodule:: acconeer.exptool.configs.BaseServiceConfig.gain.help_obj

Max. signal attenuation
^^^^^^^^^^^^^^^^^^^^^^^
.. automodule:: acconeer.exptool.configs.BaseServiceConfig.maximize_signal_attenuation.help_obj

Noise level normalization (all except Sparse)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^


Depth LPF cutoff ratio (IQ only)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
.. automodule:: acconeer.exptool.configs.IQServiceConfig.depth_lowpass_cutoff_ratio.help_obj

Disable TX
^^^^^^^^^^
.. automodule:: acconeer.exptool.configs.BaseServiceConfig.tx_disable.help_obj

Power Save mode
^^^^^^^^^^^^^^^
See the :ref:`Sensor introduction<power-save-modes>` for details.

Sensor meta data
----------------
.. _session-meta-data:
.. figure:: /_static/gui/sensor_settings_meta.png
    :figwidth: 40%
    :align: right

    Session information in the GUI

Due to rounding issues, the some settings from the standard and advanced tab may not be exactly the ones used for the current scan.
Therefor the session meta data tab will report the actual values used for the current session.
Note, that this tab will only show the actual values after you have started a scan.
