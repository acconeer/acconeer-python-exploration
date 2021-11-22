.. _connect-sensor:

Connecting to a sensor
======================

.. figure:: /_static/gui/sensor_connections.png

   Different ways of connecting to a sensor with the GUI

Depending on the type of hardware you are using, you will need to select a different type of connection from the **Connection** drop-down menu.
Regardless of the hardware, you will be able to select all services and detectors, but you may be limited in the number of sensors and the maximum usable update rate.

.. attention::
    If your update rate is too high for the connection interface (slow WiFi or Serial), you will start dropping frames! The GUI will inform you about dropped frames in the lower right side, where the info panel is located!

Raspberry Pi (XR/XC112)
^^^^^^^^^^^^^^^^^^^^^^^
Using the XC112 connector board with the Raspberry Pi, you can connect to up to 4 XR112 sensors simultaneously.
Before you try to connect to the senors, make sure they are correctly attached to the connector board with the flat-cable and the exploration server is started.
It does not matter, which ports are used.

.. attention::
    Improperly connecting the sensor with the flat-cables to the connector board can damage your hardware!

The exploration server can be downloaded from our `developer website <https://developer.acconeer.com>`_.
Navigate to the login page, create an account and log in.
Next, find the **Software Downloads** tab and click on **XC112** (or **XC111** for the older sensor version).
This will bring up the download link for the Raspberry Pi.
Download and unzip the software kit and upload it to your Raspberry Pi.
If you are on Windows you may need to install an SCP client such as `WinSCP <https://winscp.net/eng/index.php>`_ or `Bitvise <https://www.bitvise.com/ssh-client>`_ to upload files to your Raspberry Pi.

The exploration server is located in the *out* folder and is called
*acc_exploration_server_a111*

You may need to enable execution first and then start it::

    chmod +x acc_exploration_server_a111
    ./acc_exploration_server_a111

When the exploration server is started, select **Socket** in the *Connections* drop-down list and type in the IP-address of your Raspberry Pi.

.. tip::
    If you have a fast and stable WiFi connection, no cable is required.
    When using all 4 sensors or very high update rates (~200Hz), a wired network connection might be better, to avoid dropped sensor frames.

Now click on the **Connect** button to connect to the exploration server.
The GUI will automatically determine, which sensors are available and select those for you in the **Sensor settings** panel.
On successful connection, the **Connect** button will show in red **Disconnect**.
The GUI may warn you to either update the Acconeer Exploration Tool or the exploration server with a red message under the **Connect** button.

If any error occurs while connecting, the GUI will display an error message; you should

- make sure the IP address is correct
- check the cables
- check that the exploration server is still running
- check the log of the exploration server for error messages (the GUI does not receive those errors and you need to check them manually)

.. attention::
    The GUI will NOT know, if you add or remove sensors after you have connected. You need to either disconnect and connect again to update or change the sensor selection yourself. If the selected sensor is not available, the GUI will bring up an error message!

USB Module (XM112/122/132)
^^^^^^^^^^^^^^^^^^^^^^^^^^
Using our USB modules, you can either connect through Serial or SPI.
The SPI interface allows for much higher data transfer rates than the Serial interface. However, it is only supported on the XM112.
If you need to evaluate/tune a service or detector with high update rates, you should use the SPI interface to avoid accumulation of dropped frames.

For SPI connections, simply select **SPI** and connect.

.. attention::
    In order to use the SPI interface, you must connect both USB ports of the module to your PC!

For Serial connections, select **Serial**; this will show a COM port drop-down list, a **Scan ports** and **Advanced port settings** button.
You may need to check which COM port is assigned to your USB module in the Windows Device Manager under the *Ports (COM&LPT)* section.
If the correct port is not available for selection in the drop-down list, you can click **Scan-ports** to re-populate the COM list; if this still doesn't add the correct port, please check the connection cables.
The **Advanced port settings** menu should only be used with specialized, non-standard hardware; please contact our customer support to get help in his case.

Simulated
^^^^^^^^^
If you don't have any Acconeer Hardware available, you can still test our services and detectors using this simulated sensor server.
Select **Simulated** from the **Connections** drop-down menu and click **Connect**.
Once you are connected, you can operate all services and detectors with up to 4 sensors.

.. attention::
    The simulated sensor server uses numerically generated, noise-free data and is thus highly idealized. It does not accurately reflect the sensor SNR performance!
