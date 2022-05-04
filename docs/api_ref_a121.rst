API reference (A121)
====================

Config classes
--------------

.. autoclass:: acconeer.exptool.a121.SessionConfig
    :members:

.. autoclass:: acconeer.exptool.a121.SensorConfig
    :members:

.. autoclass:: acconeer.exptool.a121.SubsweepConfig
    :members:

.. autoclass:: acconeer.exptool.a121.PRF
    :members:
    :undoc-members:

.. autoclass:: acconeer.exptool.a121.IdleState
    :members:
    :undoc-members:

.. autoclass:: acconeer.exptool.a121.Profile
    :members:
    :undoc-members:

Input/Output
------------

.. autoclass:: acconeer.exptool.a121.Client
    :members:
       connect,
       setup_session,
       start_session,
       get_next,
       stop_session,
       disconnect,
       connected,
       session_is_setup,
       session_is_started,
       server_info,
       client_info,
       session_config,
