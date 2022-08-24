Presence detection
==================

This presence detector measures changes in the data over time to detect motion. It is divided into two separate parts:

Inter-frame presence -- detecting (slower) movements *between* frames
    For every frame and depth, the absolute value of the mean sweep is filtered through a fast and a slow low pass filter.
    The inter-frame deviation is the deviation between the two filters.

Intra-frame presence -- detecting (faster) movements *inside* frames
    For every frame and depth, the intra-frame deviation is based on the deviation from the mean of the sweeps

Both the inter- and the intra-frame deviations are filtered both in time and depth. Also, to be more robust against changing environments and variations between sensors, normalization is done against the noise floor.
Finally, the output from each part is the maximum value in the measured range.
