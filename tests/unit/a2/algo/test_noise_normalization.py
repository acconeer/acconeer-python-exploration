# Copyright (c) Acconeer AB, 2025-2026
# All rights reserved

from unittest.mock import MagicMock

import numpy as np
import pytest

from acconeer.exptool import a2
from acconeer.exptool.a2.algo.noise_normalization import (
    NoiseNormalizationRecording,
    NoiseNormalizationResultProcessor,
)


NUM_SAMPLES = 1000


def get_circular_noise_vector(std, num_samples):
    rng = np.random.default_rng(1)
    return rng.normal(0, std / np.sqrt(2), num_samples) + 1j * rng.normal(
        0, std / np.sqrt(2), num_samples
    )


# fmt: off
@pytest.mark.parametrize(
    "noise_frames, num_points, expected_noise_values, tx_antenna_mask, rx_antenna_mask",
    [
        pytest.param(
            [
                200.0 + 166.0j, 196.0 + 160.0j, 121.0 + 228.0j, 120.0 + 174.0j, 427.0 + 69.0j, 276.0 + 273.0j, 17.0 + 410.0j, 264.0 + 478.0j,
                136.0 + 94.0j, 21.0 + 424.0j, 420.0 + 310.0j, 379.0 + 181.0j, 344.0 + 290.0j, 348.0 + 398.0j, 296.0 + 447.0j, 317.0 + 205.0j,
                66.0 + 144.0j, 222.0 + 430.0j, 349.0 + 71.0j, 38.0 + 138.0j, 5.0 + 108.0j, 253.0 + 439.0j, 352.0 + 153.0j, 64.0 + 204.0j,
                213.0 + 79.0j, 110.0 + 183.0j, 109.0 + 357.0j, 286.0 + 51.0j, 37.0 + 345.0j, 315.0 + 306.0j, 401.0 + 2.0j, 422.0 + 60.0j,
                455.0 + 409.0j, 164.0 + 9.0j, 180.0 + 157.0j, 467.0 + 56.0j, 209.0 + 237.0j, 86.0 + 11.0j, 308.0 + 215.0j, 389.0 + 99.0j,
                4.0 + 359.0j, 149.0 + 189.0j, 327.0 + 431.0j, 129.0 + 201.0j, 260.0 + 76.0j, 238.0 + 106.0j, 47.0 + 41.0j, 116.0 + 433.0j,
                355.0 + 155.0j, 3.0 + 390.0j, 303.0 + 285.0j, 444.0 + 432.0j, 8.0 + 257.0j, 15.0 + 168.0j, 356.0 + 147.0j, 231.0 + 454.0j,
                101.0 + 462.0j, 87.0 + 476.0j, 449.0 + 474.0j, 46.0 + 472.0j, 12.0 + 236.0j, 448.0 + 299.0j, 190.0 + 275.0j, 22.0 + 134.0j,
                324.0 + 125.0j, 332.0 + 24.0j, 137.0 + 0.0j, 172.0 + 465.0j, 298.0 + 405.0j, 128.0 + 369.0j, 320.0 + 288.0j, 226.0 + 85.0j,
                473.0 + 14.0j, 151.0 + 339.0j, 239.0 + 385.0j, 140.0 + 367.0j, 412.0 + 333.0j, 451.0 + 156.0j, 203.0 + 97.0j, 262.0 + 48.0j,
                92.0 + 217.0j, 70.0 + 230.0j, 220.0 + 312.0j, 269.0 + 55.0j, 313.0 + 63.0j, 178.0 + 167.0j, 319.0 + 49.0j, 62.0 + 393.0j,
                382.0 + 361.0j, 250.0 + 301.0j, 479.0 + 258.0j, 434.0 + 446.0j, 336.0 + 418.0j, 107.0 + 35.0j, 248.0 + 370.0j, 416.0 + 18.0j,
                387.0 + 304.0j, 353.0 + 249.0j, 124.0 + 194.0j, 265.0 + 198.0j, 42.0 + 219.0j, 65.0 + 199.0j, 50.0 + 316.0j, 246.0 + 402.0j,
                89.0 + 54.0j, 311.0 + 368.0j, 354.0 + 57.0j, 118.0 + 127.0j, 242.0 + 77.0j, 335.0 + 1.0j, 314.0 + 133.0j, 227.0 + 235.0j,
                414.0 + 305.0j, 195.0 + 100.0j, 426.0 + 256.0j, 240.0 + 291.0j, 383.0 + 159.0j, 7.0 + 74.0j, 399.0 + 397.0j, 331.0 + 400.0j,
                346.0 + 184.0j, 268.0 + 392.0j, 175.0 + 165.0j, 325.0 + 321.0j, 61.0 + 27.0j, 322.0 + 123.0j, 442.0 + 463.0j, 293.0 + 464.0j,
                30.0 + 415.0j, 261.0 + 81.0j, 459.0 + 119.0j, 16.0 + 287.0j, 384.0 + 374.0j, 221.0 + 72.0j, 366.0 + 143.0j, 457.0 + 477.0j,
                182.0 + 372.0j, 318.0 + 362.0j, 188.0 + 58.0j, 45.0 + 75.0j, 211.0 + 187.0j, 408.0 + 283.0j, 31.0 + 206.0j, 347.0 + 28.0j,
                435.0 + 475.0j, 350.0 + 113.0j, 461.0 + 396.0j, 126.0 + 394.0j, 406.0 + 114.0j, 443.0 + 84.0j, 411.0 + 131.0j, 145.0 + 386.0j,
                179.0 + 232.0j, 243.0 + 360.0j, 279.0 + 68.0j, 83.0 + 267.0j, 292.0 + 6.0j, 88.0 + 207.0j, 373.0 + 371.0j, 52.0 + 43.0j,
                323.0 + 161.0j, 186.0 + 91.0j, 104.0 + 294.0j, 329.0 + 404.0j, 254.0 + 326.0j, 152.0 + 173.0j, 417.0 + 191.0j, 300.0 + 192.0j,
                295.0 + 277.0j, 185.0 + 169.0j, 259.0 + 302.0j, 212.0 + 241.0j, 13.0 + 29.0j, 141.0 + 388.0j, 266.0 + 193.0j, 440.0 + 458.0j,
                36.0 + 142.0j, 363.0 + 309.0j, 26.0 + 95.0j, 93.0 + 428.0j, 377.0 + 234.0j, 436.0 + 263.0j, 413.0 + 274.0j, 403.0 + 34.0j,
                158.0 + 78.0j, 425.0 + 132.0j, 80.0 + 365.0j, 342.0 + 468.0j, 202.0 + 307.0j, 59.0 + 340.0j, 148.0 + 252.0j, 218.0 + 351.0j,
                255.0 + 130.0j, 272.0 + 210.0j, 53.0 + 378.0j, 229.0 + 82.0j, 281.0 + 407.0j, 122.0 + 171.0j, 23.0 + 419.0j, 453.0 + 10.0j,
                376.0 + 150.0j, 423.0 + 177.0j, 391.0 + 102.0j, 289.0 + 233.0j, 105.0 + 111.0j, 197.0 + 162.0j, 251.0 + 19.0j, 67.0 + 73.0j,
                280.0 + 364.0j, 39.0 + 282.0j, 460.0 + 117.0j, 330.0 + 471.0j, 450.0 + 381.0j, 214.0 + 337.0j, 33.0 + 224.0j, 112.0 + 40.0j,
                429.0 + 20.0j, 297.0 + 245.0j, 466.0 + 98.0j, 343.0 + 44.0j, 375.0 + 395.0j, 284.0 + 244.0j, 154.0 + 271.0j, 341.0 + 96.0j,
                139.0 + 223.0j, 445.0 + 135.0j, 334.0 + 441.0j, 225.0 + 146.0j, 216.0 + 456.0j, 32.0 + 452.0j, 278.0 + 247.0j, 469.0 + 328.0j,
                176.0 + 170.0j, 437.0 + 163.0j, 358.0 + 90.0j, 421.0 + 380.0j, 208.0 + 103.0j, 470.0 + 438.0j, 25.0 + 270.0j, 338.0 + 115.0j,
            ],
            1,
            np.array(
                [
                    27.40825413, 26.14778661, 27.27926665, 29.49666186, 27.40825413, 26.14778661, 27.27926665, 29.49666186, 27.40825413, 26.14778661, 27.27926665, 29.49666186
                ]
            ),
            0b111,
            0b1111,
        ),
        pytest.param(
            [
                0.0 + 1.0j, 2.0 + 3.0j, 4.0 + 5.0j, 6.0 + 7.0j, 8.0 + 9.0j, 10.0 + 11.0j, 12.0 + 13.0j, 14.0 + 15.0j,
                16.0 + 17.0j, 18.0 + 19.0j, 20.0 + 21.0j, 22.0 + 23.0j, 24.0 + 25.0j, 26.0 + 27.0j, 28.0 + 29.0j, 30.0 + 31.0j,
                32.0 + 33.0j, 34.0 + 35.0j, 36.0 + 37.0j, 38.0 + 39.0j, 40.0 + 41.0j, 42.0 + 43.0j, 44.0 + 45.0j, 46.0 + 47.0j,
                48.0 + 49.0j, 50.0 + 51.0j, 52.0 + 53.0j, 54.0 + 55.0j, 56.0 + 57.0j, 58.0 + 59.0j, 60.0 + 61.0j, 62.0 + 63.0j,
                64.0 + 65.0j, 66.0 + 67.0j, 68.0 + 69.0j, 70.0 + 71.0j, 72.0 + 73.0j, 74.0 + 75.0j, 76.0 + 77.0j, 78.0 + 79.0j,
                80.0 + 81.0j, 82.0 + 83.0j, 84.0 + 85.0j, 86.0 + 87.0j, 88.0 + 89.0j, 90.0 + 91.0j, 92.0 + 93.0j, 94.0 + 95.0j,
                96.0 + 97.0j, 98.0 + 99.0j, 100.0 + 101.0j, 102.0 + 103.0j, 104.0 + 105.0j, 106.0 + 107.0j, 108.0 + 109.0j, 110.0 + 111.0j,
                112.0 + 113.0j, 114.0 + 115.0j, 116.0 + 117.0j, 118.0 + 119.0j, 120.0 + 121.0j, 122.0 + 123.0j, 124.0 + 125.0j, 126.0 + 127.0j,
                128.0 + 129.0j, 130.0 + 131.0j, 132.0 + 133.0j, 134.0 + 135.0j, 136.0 + 137.0j, 138.0 + 139.0j, 140.0 + 141.0j, 142.0 + 143.0j,
                144.0 + 145.0j, 146.0 + 147.0j, 148.0 + 149.0j, 150.0 + 151.0j, 152.0 + 153.0j, 154.0 + 155.0j, 156.0 + 157.0j, 158.0 + 159.0j,
                160.0 + 161.0j, 162.0 + 163.0j, 164.0 + 165.0j, 166.0 + 167.0j, 168.0 + 169.0j, 170.0 + 171.0j, 172.0 + 173.0j, 174.0 + 175.0j,
                176.0 + 177.0j, 178.0 + 179.0j, 180.0 + 181.0j, 182.0 + 183.0j, 184.0 + 185.0j, 186.0 + 187.0j, 188.0 + 189.0j, 190.0 + 191.0j,
                192.0 + 193.0j, 194.0 + 195.0j, 196.0 + 197.0j, 198.0 + 199.0j, 200.0 + 201.0j, 202.0 + 203.0j, 204.0 + 205.0j, 206.0 + 207.0j,
                208.0 + 209.0j, 210.0 + 211.0j, 212.0 + 213.0j, 214.0 + 215.0j, 216.0 + 217.0j, 218.0 + 219.0j, 220.0 + 221.0j, 222.0 + 223.0j,
                224.0 + 225.0j, 226.0 + 227.0j, 228.0 + 229.0j, 230.0 + 231.0j, 232.0 + 233.0j, 234.0 + 235.0j, 236.0 + 237.0j, 238.0 + 239.0j,
                240.0 + 241.0j, 242.0 + 243.0j, 244.0 + 245.0j, 246.0 + 247.0j, 248.0 + 249.0j, 250.0 + 251.0j, 252.0 + 253.0j, 254.0 + 255.0j,
                256.0 + 257.0j, 258.0 + 259.0j, 260.0 + 261.0j, 262.0 + 263.0j, 264.0 + 265.0j, 266.0 + 267.0j, 268.0 + 269.0j, 270.0 + 271.0j,
                272.0 + 273.0j, 274.0 + 275.0j, 276.0 + 277.0j, 278.0 + 279.0j, 280.0 + 281.0j, 282.0 + 283.0j, 284.0 + 285.0j, 286.0 + 287.0j,
                288.0 + 289.0j, 290.0 + 291.0j, 292.0 + 293.0j, 294.0 + 295.0j, 296.0 + 297.0j, 298.0 + 299.0j, 300.0 + 301.0j, 302.0 + 303.0j,
                304.0 + 305.0j, 306.0 + 307.0j, 308.0 + 309.0j, 310.0 + 311.0j, 312.0 + 313.0j, 314.0 + 315.0j, 316.0 + 317.0j, 318.0 + 319.0j,
                320.0 + 321.0j, 322.0 + 323.0j, 324.0 + 325.0j, 326.0 + 327.0j, 328.0 + 329.0j, 330.0 + 331.0j, 332.0 + 333.0j, 334.0 + 335.0j,
                336.0 + 337.0j, 338.0 + 339.0j, 340.0 + 341.0j, 342.0 + 343.0j, 344.0 + 345.0j, 346.0 + 347.0j, 348.0 + 349.0j, 350.0 + 351.0j,
                352.0 + 353.0j, 354.0 + 355.0j, 356.0 + 357.0j, 358.0 + 359.0j, 360.0 + 361.0j, 362.0 + 363.0j, 364.0 + 365.0j, 366.0 + 367.0j,
                368.0 + 369.0j, 370.0 + 371.0j, 372.0 + 373.0j, 374.0 + 375.0j, 376.0 + 377.0j, 378.0 + 379.0j, 380.0 + 381.0j, 382.0 + 383.0j,
                384.0 + 385.0j, 386.0 + 387.0j, 388.0 + 389.0j, 390.0 + 391.0j, 392.0 + 393.0j, 394.0 + 395.0j, 396.0 + 397.0j, 398.0 + 399.0j,
                400.0 + 401.0j, 402.0 + 403.0j, 404.0 + 405.0j, 406.0 + 407.0j, 408.0 + 409.0j, 410.0 + 411.0j, 412.0 + 413.0j, 414.0 + 415.0j,
                416.0 + 417.0j, 418.0 + 419.0j, 420.0 + 421.0j, 422.0 + 423.0j, 424.0 + 425.0j, 426.0 + 427.0j, 428.0 + 429.0j, 430.0 + 431.0j,
                432.0 + 433.0j, 434.0 + 435.0j, 436.0 + 437.0j, 438.0 + 439.0j, 440.0 + 441.0j, 442.0 + 443.0j, 444.0 + 445.0j, 446.0 + 447.0j,
                448.0 + 449.0j, 450.0 + 451.0j, 452.0 + 453.0j, 454.0 + 455.0j, 456.0 + 457.0j, 458.0 + 459.0j, 460.0 + 461.0j, 462.0 + 463.0j,
                464.0 + 465.0j, 466.0 + 467.0j, 468.0 + 469.0j, 470.0 + 471.0j, 472.0 + 473.0j, 474.0 + 475.0j, 476.0 + 477.0j, 478.0 + 479.0j,
            ],
            1,
            np.array(
                [
                    27.70896365, 27.70896365, 27.70896365, 27.70896365, 27.70896365, 27.70896365,
                    27.70896365, 27.70896365, 27.70896365, 27.70896365, 27.70896365, 27.70896365
                ]
            ),
            0b111,
            0b1111,
        ),
        pytest.param(
            [
                0.0 + 1.0j, 2.0 + 3.0j, 4.0 + 5.0j, 6.0 + 7.0j, 8.0 + 9.0j, 10.0 + 11.0j, 12.0 + 13.0j, 14.0 + 15.0j,
                16.0 + 17.0j, 18.0 + 19.0j, 20.0 + 21.0j, 22.0 + 23.0j, 24.0 + 25.0j, 26.0 + 27.0j, 28.0 + 29.0j, 30.0 + 31.0j,
                32.0 + 33.0j, 34.0 + 35.0j, 36.0 + 37.0j, 38.0 + 39.0j, 40.0 + 41.0j, 42.0 + 43.0j, 44.0 + 45.0j, 46.0 + 47.0j,
                48.0 + 49.0j, 50.0 + 51.0j, 52.0 + 53.0j, 54.0 + 55.0j, 56.0 + 57.0j, 58.0 + 59.0j, 60.0 + 61.0j, 62.0 + 63.0j,
                64.0 + 65.0j, 66.0 + 67.0j, 68.0 + 69.0j, 70.0 + 71.0j, 72.0 + 73.0j, 74.0 + 75.0j, 76.0 + 77.0j, 78.0 + 79.0j,
                80.0 + 81.0j, 82.0 + 83.0j, 84.0 + 85.0j, 86.0 + 87.0j, 88.0 + 89.0j, 90.0 + 91.0j, 92.0 + 93.0j, 94.0 + 95.0j,
                96.0 + 97.0j, 98.0 + 99.0j, 100.0 + 101.0j, 102.0 + 103.0j, 104.0 + 105.0j, 106.0 + 107.0j, 108.0 + 109.0j, 110.0 + 111.0j,
                112.0 + 113.0j, 114.0 + 115.0j, 116.0 + 117.0j, 118.0 + 119.0j, 120.0 + 121.0j, 122.0 + 123.0j, 124.0 + 125.0j, 126.0 + 127.0j,
                128.0 + 129.0j, 130.0 + 131.0j, 132.0 + 133.0j, 134.0 + 135.0j, 136.0 + 137.0j, 138.0 + 139.0j, 140.0 + 141.0j, 142.0 + 143.0j,
                144.0 + 145.0j, 146.0 + 147.0j, 148.0 + 149.0j, 150.0 + 151.0j, 152.0 + 153.0j, 154.0 + 155.0j, 156.0 + 157.0j, 158.0 + 159.0j,
                160.0 + 161.0j, 162.0 + 163.0j, 164.0 + 165.0j, 166.0 + 167.0j, 168.0 + 169.0j, 170.0 + 171.0j, 172.0 + 173.0j, 174.0 + 175.0j,
                176.0 + 177.0j, 178.0 + 179.0j, 180.0 + 181.0j, 182.0 + 183.0j, 184.0 + 185.0j, 186.0 + 187.0j, 188.0 + 189.0j, 190.0 + 191.0j,
                192.0 + 193.0j, 194.0 + 195.0j, 196.0 + 197.0j, 198.0 + 199.0j, 200.0 + 201.0j, 202.0 + 203.0j, 204.0 + 205.0j, 206.0 + 207.0j,
                208.0 + 209.0j, 210.0 + 211.0j, 212.0 + 213.0j, 214.0 + 215.0j, 216.0 + 217.0j, 218.0 + 219.0j, 220.0 + 221.0j, 222.0 + 223.0j,
                224.0 + 225.0j, 226.0 + 227.0j, 228.0 + 229.0j, 230.0 + 231.0j, 232.0 + 233.0j, 234.0 + 235.0j, 236.0 + 237.0j, 238.0 + 239.0j,
                240.0 + 241.0j, 242.0 + 243.0j, 244.0 + 245.0j, 246.0 + 247.0j, 248.0 + 249.0j, 250.0 + 251.0j, 252.0 + 253.0j, 254.0 + 255.0j,
                256.0 + 257.0j, 258.0 + 259.0j, 260.0 + 261.0j, 262.0 + 263.0j, 264.0 + 265.0j, 266.0 + 267.0j, 268.0 + 269.0j, 270.0 + 271.0j,
                272.0 + 273.0j, 274.0 + 275.0j, 276.0 + 277.0j, 278.0 + 279.0j, 280.0 + 281.0j, 282.0 + 283.0j, 284.0 + 285.0j, 286.0 + 287.0j,
                288.0 + 289.0j, 290.0 + 291.0j, 292.0 + 293.0j, 294.0 + 295.0j, 296.0 + 297.0j, 298.0 + 299.0j, 300.0 + 301.0j, 302.0 + 303.0j,
                304.0 + 305.0j, 306.0 + 307.0j, 308.0 + 309.0j, 310.0 + 311.0j, 312.0 + 313.0j, 314.0 + 315.0j, 316.0 + 317.0j, 318.0 + 319.0j,
                320.0 + 321.0j, 322.0 + 323.0j, 324.0 + 325.0j, 326.0 + 327.0j, 328.0 + 329.0j, 330.0 + 331.0j, 332.0 + 333.0j, 334.0 + 335.0j,
                336.0 + 337.0j, 338.0 + 339.0j, 340.0 + 341.0j, 342.0 + 343.0j, 344.0 + 345.0j, 346.0 + 347.0j, 348.0 + 349.0j, 350.0 + 351.0j,
                352.0 + 353.0j, 354.0 + 355.0j, 356.0 + 357.0j, 358.0 + 359.0j, 360.0 + 361.0j, 362.0 + 363.0j, 364.0 + 365.0j, 366.0 + 367.0j,
                368.0 + 369.0j, 370.0 + 371.0j, 372.0 + 373.0j, 374.0 + 375.0j, 376.0 + 377.0j, 378.0 + 379.0j, 380.0 + 381.0j, 382.0 + 383.0j,
                384.0 + 385.0j, 386.0 + 387.0j, 388.0 + 389.0j, 390.0 + 391.0j, 392.0 + 393.0j, 394.0 + 395.0j, 396.0 + 397.0j, 398.0 + 399.0j,
                400.0 + 401.0j, 402.0 + 403.0j, 404.0 + 405.0j, 406.0 + 407.0j, 408.0 + 409.0j, 410.0 + 411.0j, 412.0 + 413.0j, 414.0 + 415.0j,
                416.0 + 417.0j, 418.0 + 419.0j, 420.0 + 421.0j, 422.0 + 423.0j, 424.0 + 425.0j, 426.0 + 427.0j, 428.0 + 429.0j, 430.0 + 431.0j,
                432.0 + 433.0j, 434.0 + 435.0j, 436.0 + 437.0j, 438.0 + 439.0j, 440.0 + 441.0j, 442.0 + 443.0j, 444.0 + 445.0j, 446.0 + 447.0j,
                448.0 + 449.0j, 450.0 + 451.0j, 452.0 + 453.0j, 454.0 + 455.0j, 456.0 + 457.0j, 458.0 + 459.0j, 460.0 + 461.0j, 462.0 + 463.0j,
                464.0 + 465.0j, 466.0 + 467.0j, 468.0 + 469.0j, 470.0 + 471.0j, 472.0 + 473.0j, 474.0 + 475.0j, 476.0 + 477.0j, 478.0 + 479.0j,
            ],
            5,
            np.array(
                [
                    74.05532038, 74.05532038, 74.05532038, 74.05532038, 74.05532038,
                    74.05532038, 74.05532038, 74.05532038, 74.05532038, 74.05532038,
                    74.05532038, 74.05532038, 54.3417486 , 54.3417486 , 54.3417486 ,
                    54.3417486 , 54.3417486 , 54.3417486 , 54.3417486 , 54.3417486 ,
                    54.3417486 , 54.3417486 , 54.3417486 , 54.3417486 , 42.75585915,
                    42.75585915, 42.75585915, 42.75585915, 42.75585915, 42.75585915,
                    42.75585915, 42.75585915, 42.75585915, 42.75585915, 42.75585915,
                    42.75585915, 33.60205409, 33.60205409, 33.60205409, 33.60205409,
                    33.60205409, 33.60205409, 33.60205409, 33.60205409, 33.60205409,
                    33.60205409, 33.60205409, 33.60205409, 27.70896365, 27.70896365,
                    27.70896365, 27.70896365, 27.70896365, 27.70896365, 27.70896365,
                    27.70896365, 27.70896365, 27.70896365, 27.70896365, 27.70896365,
                ]
            ),
            0b111,
            0b1111,
        ),
        pytest.param(
            np.array([
                get_circular_noise_vector(1,NUM_SAMPLES),
                get_circular_noise_vector(10,NUM_SAMPLES),
                get_circular_noise_vector(100,NUM_SAMPLES),
                get_circular_noise_vector(1000,NUM_SAMPLES),
                get_circular_noise_vector(1,NUM_SAMPLES),
                get_circular_noise_vector(10,NUM_SAMPLES),
                get_circular_noise_vector(100,NUM_SAMPLES),
                get_circular_noise_vector(1000,NUM_SAMPLES),
                get_circular_noise_vector(1,NUM_SAMPLES),
                get_circular_noise_vector(10,NUM_SAMPLES),
                get_circular_noise_vector(100,NUM_SAMPLES),
                get_circular_noise_vector(1000,NUM_SAMPLES),
            ]).transpose().flatten(),
            1,
            np.tile([0.14223698,   1.42236981,  14.22369807, 142.23698068],3).flatten(),
            0b111,
            0b1111,
        ),
        pytest.param(
            np.array([
                get_circular_noise_vector(1,NUM_SAMPLES),
                get_circular_noise_vector(10,NUM_SAMPLES),
                get_circular_noise_vector(100,NUM_SAMPLES),
                get_circular_noise_vector(1000,NUM_SAMPLES),
                get_circular_noise_vector(2,NUM_SAMPLES),
                get_circular_noise_vector(10,NUM_SAMPLES),
                get_circular_noise_vector(100,NUM_SAMPLES),
                get_circular_noise_vector(1000,NUM_SAMPLES),
                get_circular_noise_vector(2,NUM_SAMPLES),
                get_circular_noise_vector(10,NUM_SAMPLES),
                get_circular_noise_vector(100,NUM_SAMPLES),
                get_circular_noise_vector(1000,NUM_SAMPLES),
            ]).transpose().flatten(),
            1,
            np.tile([ 0.24637835,   1.42236981,  14.22369807, 142.23698068],3).flatten(),
            0b111,
            0b1111,
        ),
        pytest.param(
            np.array([
                get_circular_noise_vector(10,NUM_SAMPLES),
                get_circular_noise_vector(100,NUM_SAMPLES),
                get_circular_noise_vector(1000,NUM_SAMPLES),
                get_circular_noise_vector(10,NUM_SAMPLES),
                get_circular_noise_vector(100,NUM_SAMPLES),
                get_circular_noise_vector(1000,NUM_SAMPLES),
                get_circular_noise_vector(10,NUM_SAMPLES),
                get_circular_noise_vector(100,NUM_SAMPLES),
                get_circular_noise_vector(1000,NUM_SAMPLES),
            ]).transpose().flatten(),
            1,
            np.tile([1.42236981,  14.22369807, 142.23698068],3).flatten(),
            0b111,
            0b0111,
        ),
        pytest.param(
            np.array([
                get_circular_noise_vector(10,NUM_SAMPLES),
                get_circular_noise_vector(100,NUM_SAMPLES),
                get_circular_noise_vector(1000,NUM_SAMPLES),
                get_circular_noise_vector(10,NUM_SAMPLES),
                get_circular_noise_vector(100,NUM_SAMPLES),
                get_circular_noise_vector(1000,NUM_SAMPLES),
                get_circular_noise_vector(10,NUM_SAMPLES),
                get_circular_noise_vector(100,NUM_SAMPLES),
                get_circular_noise_vector(1000,NUM_SAMPLES),
            ]).transpose().flatten(),
            1,
            np.tile([1.42236981,  14.22369807, 142.23698068],3).flatten(),
            0b111,
            0b1011,
        ),
        pytest.param(
            np.array([
                get_circular_noise_vector(10,NUM_SAMPLES),
                get_circular_noise_vector(100,NUM_SAMPLES),
                get_circular_noise_vector(1000,NUM_SAMPLES),
                get_circular_noise_vector(10,NUM_SAMPLES),
                get_circular_noise_vector(100,NUM_SAMPLES),
                get_circular_noise_vector(1000,NUM_SAMPLES),
                get_circular_noise_vector(10,NUM_SAMPLES),
                get_circular_noise_vector(100,NUM_SAMPLES),
                get_circular_noise_vector(1000,NUM_SAMPLES),
            ]).transpose().flatten(),
            1,
            np.tile([1.42236981,  14.22369807, 142.23698068],3).flatten(),
            0b111,
            0b1101,
        ),
        pytest.param(
            np.array([
                get_circular_noise_vector(10,NUM_SAMPLES),
                get_circular_noise_vector(1000,NUM_SAMPLES),
                get_circular_noise_vector(10,NUM_SAMPLES),
                get_circular_noise_vector(1000,NUM_SAMPLES),
                get_circular_noise_vector(10,NUM_SAMPLES),
                get_circular_noise_vector(1000,NUM_SAMPLES),
            ]).transpose().flatten(),
            1,
            np.tile([1.42236981, 142.23698068],3).flatten(),
            0b111,
            0b1010,
        ),
    ],
)
# fmt: on
def test_calc_noise(
    noise_frames, num_points, expected_noise_values, tx_antenna_mask, rx_antenna_mask
):
    sensor_config = a2.SensorConfig.single_subsweep(
        num_points=num_points,
        sweeps_per_frame=1,
        tx_antenna_mask=tx_antenna_mask,
        rx_antenna_mask=rx_antenna_mask,
        hwaas_exponent=4,
    )
    noise_values = NoiseNormalizationRecording._calc_noise_values(
        noise_frames, sensor_config.subsweep
    )
    np.testing.assert_allclose(noise_values, expected_noise_values)


@pytest.mark.parametrize(
    "frame, noise, expected_norm_frame",
    [
        pytest.param(
            np.array(
                [
                    [1 + 2j, 3 + 4j, 5 + 6j],
                    [7 + 8j, 9 + 10j, 11 + 12j],
                    [13 + 14j, 15 + 16j, 17 + 18j],
                ]
            ),
            np.array([19, 20, 21]),
            np.array(
                [
                    [0.052632 + 0.105263j, 0.15 + 0.2j, 0.238095 + 0.285714j],
                    [0.368421 + 0.421053j, 0.45 + 0.5j, 0.52381 + 0.571429j],
                    [0.684211 + 0.736842j, 0.75 + 0.8j, 0.809524 + 0.857143j],
                ]
            ),
        ),
        pytest.param(
            np.array(
                [
                    [1 + 2j, 3 + 4j, 5 + 6j],
                    [7 + 8j, 9 + 10j, 11 + 12j],
                    [13 + 14j, 15 + 16j, 17 + 18j],
                ]
            ),
            np.array([1, 1, 1]),
            np.array(
                [
                    [1 + 2j, 3 + 4j, 5 + 6j],
                    [7 + 8j, 9 + 10j, 11 + 12j],
                    [13 + 14j, 15 + 16j, 17 + 18j],
                ]
            ),
        ),
        pytest.param(
            np.array(
                [
                    [13 + 10j, 5 + 8j, 3 + 7j],
                    [9 + 4j, 14 + 16j, 2 + 18j],
                    [17 + 12j, 1 + 11j, 15 + 6j],
                ]
            ),
            np.array([19, 20, 21]),
            np.array(
                [
                    [0.684211 + 0.526316j, 0.25 + 0.4j, 0.142857 + 0.333333j],
                    [0.473684 + 0.210526j, 0.7 + 0.8j, 0.095238 + 0.857143j],
                    [0.894737 + 0.631579j, 0.05 + 0.55j, 0.714286 + 0.285714j],
                ]
            ),
        ),
    ],
)
def test_normalize_frame(frame, noise, expected_norm_frame):
    norm_frame = NoiseNormalizationResultProcessor.normalize_frame(frame, noise)

    np.testing.assert_allclose(norm_frame, expected_norm_frame, rtol=5e-6)


def _make_mock_client(noise_stds: list[float], rng: np.random.Generator) -> MagicMock:
    """Mock client for create() tests.

    noise_stds[i] is the circular-Gaussian std for noise sensor config i
    in the expanded noise session (ordered by sensor_config then subsweep).
    """
    client = MagicMock()
    client.connected = True
    # List used as a mutable container so the closure can share state between
    # setup_session and get_next without needing nonlocal rebinding.
    noise_config_holder: list[a2.SessionConfig] = []

    def setup_session(config: a2.SessionConfig) -> None:
        noise_config_holder.append(config)

    def get_next(**kwargs: object) -> MagicMock:
        results = []
        for i, sensor_config in enumerate(noise_config_holder[0].sensor_configs):
            subsweep_config = sensor_config.subsweeps[0]
            std = noise_stds[i]
            shape = (
                sensor_config.sweeps_per_frame,
                subsweep_config.num_points * subsweep_config.num_channels,
            )
            frame = rng.normal(0, std / np.sqrt(2), shape) + 1j * rng.normal(
                0, std / np.sqrt(2), shape
            )
            result = MagicMock()
            result.frame = frame
            results.append(result)
        group_result = MagicMock()
        group_result.results = results
        return group_result

    client.setup_session.side_effect = setup_session
    client.get_next.side_effect = get_next
    return client


def _make_subsweep(
    num_points: int,
    hwaas_exponent: int = 0,
    hwaas_max: int = 1,
    tx_antenna_mask: int = 0b001,
    rx_antenna_mask: int = 0b0001,
) -> a2.SubsweepConfig:
    return a2.SubsweepConfig(
        num_points=num_points,
        tx_antenna_mask=tx_antenna_mask,
        rx_antenna_mask=rx_antenna_mask,
        hwaas_exponent=hwaas_exponent,
        hwaas_max=hwaas_max,
    )


def test_create_multi_subsweep() -> None:
    rng = np.random.default_rng(42)
    subsweep_config_0 = _make_subsweep(
        num_points=5, hwaas_exponent=4, hwaas_max=110, tx_antenna_mask=0b111, rx_antenna_mask=0b0001
    )
    subsweep_config_1 = _make_subsweep(
        num_points=3, hwaas_exponent=4, hwaas_max=50, tx_antenna_mask=0b001, rx_antenna_mask=0b0011
    )

    sensor_config = a2.SensorConfig(
        subsweeps=[subsweep_config_0, subsweep_config_1],
        sweeps_per_frame=1,
        sweep_rate=None,
        frame_rate=None,
        inter_frame_idle_state=a2.IdleState.ARMED,
        inter_sweep_idle_state=a2.IdleState.ARMED,
    )
    session_config = a2.SessionConfig(sensor_configs=[sensor_config], update_rate=None)

    # one noise sensor config per subsweep_config:
    # (sensor_config, subsweep_config_0), (sensor_config, subsweep_config_1)
    noise_stds = [1.0, 10.0]
    recording = NoiseNormalizationRecording.create(
        _make_mock_client(noise_stds, rng), session_config
    )

    ss0_len = subsweep_config_0.num_points * subsweep_config_0.num_channels
    ss1_len = subsweep_config_1.num_points * subsweep_config_1.num_channels
    assert len(recording.noise_values) == 1
    assert len(recording.noise_values[0]) == ss0_len + ss1_len

    np.testing.assert_allclose(
        recording.noise_values[0][:ss0_len],
        np.repeat(noise_stds[0] / np.sqrt(subsweep_config_0.hwaas_points), subsweep_config_0.num_channels),
        rtol=0.05,
    )
    np.testing.assert_allclose(
        recording.noise_values[0][ss0_len:],
        np.repeat(noise_stds[1] / np.sqrt(subsweep_config_1.hwaas_points), subsweep_config_1.num_channels),
        rtol=0.05,
    )


def test_create_multi_sensor_config_multi_subsweep() -> None:
    rng = np.random.default_rng(42)
    subsweep_config_0 = _make_subsweep(
        num_points=5, hwaas_exponent=4, hwaas_max=50, tx_antenna_mask=0b001, rx_antenna_mask=0b0001
    )
    subsweep_config_1 = _make_subsweep(
        num_points=3, hwaas_exponent=4, hwaas_max=10, tx_antenna_mask=0b001, rx_antenna_mask=0b0011
    )
    subsweep_config_2 = _make_subsweep(
        num_points=4, hwaas_exponent=4, hwaas_max=100, tx_antenna_mask=0b011, rx_antenna_mask=0b1111
    )
    subsweep_config_3 = _make_subsweep(
        num_points=6, hwaas_exponent=4, hwaas_max=5, tx_antenna_mask=0b111, rx_antenna_mask=0b0001
    )

    sensor_config_0 = a2.SensorConfig(
        subsweeps=[subsweep_config_0, subsweep_config_1],
        sweeps_per_frame=1,
        sweep_rate=None,
        frame_rate=None,
        inter_frame_idle_state=a2.IdleState.ARMED,
        inter_sweep_idle_state=a2.IdleState.ARMED,
    )
    sensor_config_1 = a2.SensorConfig(
        subsweeps=[subsweep_config_2, subsweep_config_3],
        sweeps_per_frame=1,
        sweep_rate=None,
        frame_rate=None,
        inter_frame_idle_state=a2.IdleState.ARMED,
        inter_sweep_idle_state=a2.IdleState.ARMED,
    )
    session_config = a2.SessionConfig(
        sensor_configs=[sensor_config_0, sensor_config_1], update_rate=None
    )

    # Order: (sensor_config_0, subsweep_config_0), (sensor_config_0, subsweep_config_1),
    #        (sensor_config_1, subsweep_config_2), (sensor_config_1, subsweep_config_3)
    noise_stds = [1.0, 10.0, 100.0, 1000.0]
    recording = NoiseNormalizationRecording.create(
        _make_mock_client(noise_stds, rng), session_config
    )

    assert len(recording.noise_values) == 2

    ss0_len = subsweep_config_0.num_points * subsweep_config_0.num_channels
    ss1_len = subsweep_config_1.num_points * subsweep_config_1.num_channels
    assert len(recording.noise_values[0]) == ss0_len + ss1_len
    np.testing.assert_allclose(
        recording.noise_values[0][:ss0_len],
        np.repeat(noise_stds[0] / np.sqrt(subsweep_config_0.hwaas_points), subsweep_config_0.num_channels),
        rtol=0.05,
    )
    np.testing.assert_allclose(
        recording.noise_values[0][ss0_len:],
        np.repeat(noise_stds[1] / np.sqrt(subsweep_config_1.hwaas_points), subsweep_config_1.num_channels),
        rtol=0.05,
    )

    ss2_len = subsweep_config_2.num_points * subsweep_config_2.num_channels
    ss3_len = subsweep_config_3.num_points * subsweep_config_3.num_channels
    assert len(recording.noise_values[1]) == ss2_len + ss3_len
    np.testing.assert_allclose(
        recording.noise_values[1][:ss2_len],
        np.repeat(noise_stds[2] / np.sqrt(subsweep_config_2.hwaas_points), subsweep_config_2.num_channels),
        rtol=0.05,
    )
    np.testing.assert_allclose(
        recording.noise_values[1][ss2_len:],
        np.repeat(noise_stds[3] / np.sqrt(subsweep_config_3.hwaas_points), subsweep_config_3.num_channels),
        rtol=0.05,
    )
