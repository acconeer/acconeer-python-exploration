Signal strength
===============

To increase the signal-to-noise ratio (SNR), sampling of points may be repeated and averaged a number of times directly by the sensor itself.
The number of samples used for averaging is called
*hardware accelerated average samples*, or *HWAAS* for short.
Using this parameter correctly is crucial for reaching the desired signal quality while limiting the memory usage.
For static objects, the SNR grows linearly with HWAAS, but keep in mind that so does the measurement time.

..
    TODO: See section~\ref{sec:timing} for a detailed description of the timing in a frame.
