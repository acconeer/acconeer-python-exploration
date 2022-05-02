.. _button-press:

Button press detection (envelope)
=================================

A simple button press detection algorithm built on top of the :ref:`envelope-service` service - based on measuring changes over time in the radar signal close to the sensor.

A radar sensor can by simple reconfiguration have multiple functionalities. A radar sensor at the dashboard of a car, or in the light switch in a room, running presence detection can also act as a touch button. In this example detector, the radar is configured to measure changes in the signal only very close to the sensor, to create a touch button functionality.

.. figure:: /_tikz/res/button_press/button_press.png
   :align: center
   :width: 60%

   The A1 radar sensor can be configured to measure only very close to the sensor, thereby acting as a touch button behind solid plastic.

Detailed description
--------------------

Close to the sensor, the so-called direct leakage is often dominating the radar signal. This is the signal due to the radar pulse going directly from the transmitting antenna to the receiving antenna in the chip. When the button is pressed, the signal from the radar pulse reflecting off the fingers or hand will either constructively or destructively interfere with the direct leakage. Therefore, we here search for the resulting oscillations in the signal.

The recommended configuration for measurements close to the sensor is using the :ref:`envelope-service` service with ``maximize_signal_attenuation`` enabled, lower gain and shortest wavelet, i.e. Profile 1, which sets the radar in an insensitive configuration to not saturate from the strong direct leakage and the short radar pulse to be able to separate reflectors at different distances. The Envelope service is in this detector configured by default to scan from 3 to 4 cm. Scanning closer to the sensor will decrease the sensitivity since the direct leakage grows in strength towards 0 cm, while scanning further away from the sensor results in button press detections before the fingers touch the button. The optimal scan range depends on the mechanical integration of the sensor and wanted user experience, so some parameter tuning is usually required. Best performance is often obtained by placing the radar sensor close to the plastic with an air-gap of only a few millimeters.

Let :math:`x(s, d)` be the envelope sweep data where :math:`s` is the sweep index and :math:`d` is the range index. With the default configuration the number of range index, :math:`N_d`, is approx 20 and the sensor collects :math:`f_s` sweeps per second. The first step in the algorithm is to average each sweep to a single number,

.. math::
   y(s) = \frac{1}{N_d} \sum_d x( s, d),

which will be referred to as signal. To find variations in the signal, a low-pass version of the signal is created using a standard exponential filter,

.. math::
   \bar{y}(s) = \alpha_y \cdot \bar{y}(s-1) + (1 - \alpha_y) \cdot y(s),

where :math:`\alpha_y` is a smoothing factor determined as

.. math::
   \alpha_y = \exp\left(-\frac{1}{\tau_y \cdot f_s}\right)

and :math:`\tau_y` is the time constant for the signal.

The next step is to calculate the normalized deviation,

.. math::
   z(s) = \frac{\left( y(s) - \bar{y}(s) \right)^2 }{\bar{y}(s)^2}.

The normalization is done to handle the variation in direct leakage due to minute differences in mechanical integration and sensor variation. This deviation is then low pass filtered

.. math::
   \bar{z}(s) = \alpha_z \cdot \bar{z}(s-1) + (1 - \alpha_z) \cdot z(s)

where the smoothing factor now is calculated using the deviation time constant, which should be chosen to tbe the length of a typical button press event.

The final step of the algorithm is to detect a button press at sweep :math:`s` if, and only if, the following both are true:

1. :math:`\bar{z}(s) > \lambda`, where :math:`\lambda` is the threshold.
2. The time since the last button press detection is more than :math:`T_{bp}`.

Configuration parameters
------------------------

In the implementation, the smoothing factors :math:`\alpha_y` and :math:`\alpha_z` are set through the
:attr:`~examples.processing.button_press.ProcessingConfiguration.signal_tc_s`
and
:attr:`~examples.processing.button_press.ProcessingConfiguration.rel_dev_tc_s`
parameters and the threshold :math:`\lambda` and the minimal button press time :math:`T_{bp}` are set through
:attr:`~examples.processing.button_press.ProcessingConfiguration.threshold`
and
:attr:`~examples.processing.button_press.ProcessingConfiguration.buttonpress_length_s`.


.. autoclass:: acconeer.exptool.a111.algo.button_press._processor.ProcessingConfiguration
   :members:
