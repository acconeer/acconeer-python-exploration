from acconeer.exptool.a111.algo import (
    breathing,
    button_press,
    button_press_sparse,
    distance_detector,
    envelope,
    iq,
    obstacle_detection,
    parking,
    phase_tracking,
    power_bins,
    presence_detection_sparse,
    sleep_breathing,
    sparse,
    sparse_fft,
    sparse_inter_fft,
    sparse_speed,
)


MODULE_INFOS = [
    envelope.module_info,
    iq.module_info,
    power_bins.module_info,
    sparse.module_info,
    presence_detection_sparse.module_info,
    sparse_fft.module_info,
    sparse_inter_fft.module_info,
    sparse_speed.module_info,
    breathing.module_info,
    phase_tracking.module_info,
    sleep_breathing.module_info,
    obstacle_detection.module_info,
    button_press.module_info,
    button_press_sparse.module_info,
    distance_detector.module_info,
    parking.module_info,
]

MODULE_KEY_TO_MODULE_INFO_MAP = {mi.key: mi for mi in MODULE_INFOS}
MODULE_LABEL_TO_MODULE_INFO_MAP = {mi.label: mi for mi in MODULE_INFOS}
