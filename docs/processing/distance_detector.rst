.. _distance-detector:

Distance detector (envelope)
============================

.. note::
   The binary version of the Distance detector is currently under development, so all features of the Distance detector found here in the Python version are not found in the binary version. Specifically, the CFAR-thresholding (explained below) and the two peak sorting methods Strongest reflector and Strongest flat reflector are not found in the binary distance detector.

This is a distance detector algorithm built on top of the :ref:`envelope-service` service -- based on comparing the envelope sweep to a threshold and identifying one or more peaks, which corresponds to reflecting objects. The algorithm both detects the presence of an object and estimates its distance to the radar. The algorithm can be divided into four main parts:

**1. Average envelope sweeps:**
To decrease the effect of noise, a certain number of sweeps can be averaged into a single envelope sweep.

**2. Comparing envelope sweep to a threshold:**
Three different methods for constructing a threshold can be employed: Fixed, Stationary clutter and CFAR, explained below.

**3. Identifying peaks above the threshold:**
First, all peaks in the averaged envelope sweep above the threshold are identified. Secondly, if any peaks are too close, these are merged. For details about algorithms, please see the Python code.

**4. Sort found peaks:**
If multiple peaks are found in a sweep, four different sorting methods can be employed, each suitable for different use-cases.

Sweep averaging
---------------

To lower the signal fluctuation due to noise, multiple envelope sweeps can be averaged. Averaging many sweeps will stabilize the signal and reduce the influence from noise. Collecting sweeps takes time and consumes power, so the optimal number of sweeps collected for averaging is use-case dependent.

In this detector, sweep averaging is performed in the detector. Therefore, the :attr:`~acconeer.exptool.configs.SparseServiceConfig.running_average_factor` in the Envelope service is set to zero so no exponential averaging is performed in the service.

Setting threshold
-----------------

To be able to determine if no objects are present, the measurement needs to be compared to a threshold. Here, three different thresholds can be employed, each suitable for different use-cases.

Fixed threshold
   The most simple approach to setting the threshold is choosing a fixed threshold over the full range. This approach requires that no background objects are present that can trigger detection.

   To maximize the performance with this type of threshold, it is important that the noise normalization functionality in the service is not disabled. Otherwise, there can be variation in noise level over different sensors and different temperatures, which leads to less performance with a fixed threshold.

Stationary clutter threshold
   In situations where stationary objects are present, or when measuring very close to the sensor, the background envelope signal is not flat. In these situation it is recommended to use Stationary clutter threshold. With this approach, the threshold is set from the the mean and standard deviation of collected background sweeps. It is important that no object that should be detected is present during the recording of the background.

   The parameters for this type of threshold are the number of sweeps collected for the background estimation and a sensitivity parameter, :math:`\alpha`, between zero and one adjusting the threshold. The threshold at distance :math:`r`, :math:`t[r]` is

   .. math::
      t[r] = \mathrm{mean}_s e[s,r]  + \left( \frac{1}{\alpha} - 1 \right) \mathrm{std}_s e[s,r]

   where :math:`e[s,r]` is envelope sweep number :math:`s` from the background measurement at distance :math:`r`.

Constant False Alarm Rate (CFAR) threshold
   A final method to construct a threshold for a certain distance is to use the envelope signal from neighboring distances *from the same sweep*. This requires that the object gives rise to a single strong peak, such as a water surface and not, for example, the level in a waste container. The main advantage is that the memory consumption is minimal and that no noise normalization is required.

   The parameters for this type of threshold are the window from which the neighboring envelope sweep is averaged, and the gap around the distance of interest where the sweeps is omitted. Also, a sensitivity parameter, :math:`\alpha`, between zero and one adjusting the threshold. For example, if the guard is 6 cm and the window is 2 cm, the threshold at :math:`r` = 20 cm will be :math:`1/\alpha` times the mean of the sweep from 15 to 17 and 23 to 25 cm.

Peak sorting - Which peak is the most important?
------------------------------------------------

The main feature of the distance detector algorithm is that multiple peaks can be found in the same envelope sweep. Depending on use-case, one is often the most important. Therefore, four different peak sorting methods are available.

For example, if the threshold is low (high sensitivity), the noise can give false alarm and the strongest peak is probably of interest. With a high threshold, on the other hand, all detected peaks are likely real signals and the closest peak is probably of highest interest.

Closest
   This method simply sorts the peaks by distance, with the closest first.

Strongest
   Here, the peaks are sorted after their envelope amplitude, with the strongest first.

Strongest reflector
   The same object at a larger distance from the radar will give a weaker signal. The radar equation tells us that the envelope signal falls over distance squared,

   .. math::
      A \propto \frac{\sigma}{R^2},

   where :math:`A` is the amplitude of the peak in the envelope sweep, :math:`\sigma` is the radar cross section of the object and :math:`R` is the distance to the object. To sort the reflectors after their radar cross section, the peaks are sorted by their :math:`A_i \cdot R_i^2`.

Strongest flat reflector
   For large flat reflectors, such as fluid surfaces, the radar equation from the previous section gets modified to

   .. math::
      A \propto \frac{\sigma}{R}.

   Therefore, using this peak sorting method, the peaks are sorted by their :math:`A_i \cdot R_i`.

In the lower plot in the Distance detector GUI, the first peak after sorting is plotted as the *Main peak*, the rest of the found peaks in the same sweep are plotted as *Minor peaks*.

Configuration parameters
------------------------

.. autoclass:: examples.processing.distance_detector.ProcessingConfiguration
   :members:
