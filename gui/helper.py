from PyQt5 import QtCore, QtWidgets
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QWidget, QLabel, QFrame, QVBoxLayout, QHBoxLayout, QToolButton, QGridLayout, QCheckBox,
    QLineEdit
)


class Label(QLabel):
    def __init__(self, img, img_scale=0.7):
        super(Label, self).__init__()

        self.img_scale = img_scale
        self.pixmap = QPixmap(img)

        self.setMinimumSize(1, 1)
        self.setAlignment(QtCore.Qt.AlignVCenter | QtCore.Qt.AlignHCenter)
        self.setPixmap(self.pixmap)

    def resizeEvent(self, event):
        w = self.size().width() * self.img_scale
        h = self.size().height() * self.img_scale
        scaled_size = QtCore.QSize(w, h)

        scaled_pixmap = self.pixmap.scaled(
            scaled_size,
            QtCore.Qt.KeepAspectRatio,
            QtCore.Qt.SmoothTransformation,
        )

        self.setPixmap(scaled_pixmap)


class CollapsibleSection(QFrame):
    def __init__(self, header_text, init_collapsed=False, is_top=False):
        super().__init__()

        if not is_top:
            self.setObjectName("CollapsibleSection")
            self.setStyleSheet("#CollapsibleSection{border-top: 1px solid lightgrey;}")

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self.setLayout(self._layout)
        self._header_widget = QWidget()
        self.body_widget = QWidget()
        self._layout.addWidget(self._header_widget)
        self._layout.addWidget(self.body_widget)

        self.grid = QGridLayout(self.body_widget)
        self.grid.setContentsMargins(9, 0, 9, 9)
        self.grid.setColumnStretch(0, 1)
        self.grid.setColumnStretch(1, 1)

        self._header_widget_layout = QHBoxLayout(self._header_widget)
        self._header_widget_layout.setContentsMargins(7, 7, 7, 7)
        self._header_widget.setLayout(self._header_widget_layout)

        self._button = QToolButton()
        self._button.setText(header_text)
        self._button.setCheckable(True)
        self._button.setStyleSheet("QToolButton { border: none; }")
        self._button.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self._button.pressed.connect(self.button_event)
        self.button_event(override=init_collapsed)
        self._header_widget_layout.addWidget(self._button)
        self._header_widget_layout.addStretch()

    def button_event(self, override=None):
        if override is None:
            checked = not self._button.isChecked()
        else:
            checked = override
            self._button.setChecked(checked)

        if checked:  # collapsed
            self._button.setArrowType(QtCore.Qt.ArrowType.RightArrow)
            self.body_widget.hide()
        else:
            self._button.setArrowType(QtCore.Qt.ArrowType.DownArrow)
            self.body_widget.show()


class SensorSelection(QFrame):
    def __init__(self, multi_sensors=False, error_handler=None):
        super().__init__()

        self.error_handler = error_handler
        self.multi_sensors = multi_sensors

        # text, checked, visible, enabled, function
        checkbox_info = {
            "sensor_1": ("1", False, True, True, None),
            "sensor_2": ("2", False, True, True, None),
            "sensor_3": ("3", False, True, True, None),
            "sensor_4": ("4", False, True, True, None),
        }

        self.checkboxes = {}
        for key, (text, checked, visible, enabled, fun) in checkbox_info.items():
            cb = QCheckBox(text, self)
            cb.setChecked(checked)
            cb.setVisible(visible)
            cb.setEnabled(enabled)
            if fun:
                cb.stateChanged.connect(fun)
            self.checkboxes[key] = cb

        self.textbox = QLineEdit()
        self.textbox.setText("1")
        self.textbox.editingFinished.connect(lambda: self.check_value())

        self.grid = QtWidgets.QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.addWidget(self.checkboxes["sensor_1"], 0, 0)
        self.grid.addWidget(self.checkboxes["sensor_2"], 0, 1)
        self.grid.addWidget(self.checkboxes["sensor_3"], 0, 2)
        self.grid.addWidget(self.checkboxes["sensor_4"], 0, 3)
        self.grid.addWidget(self.textbox, 0, 4)

        self.set_multi_sensor_support(multi_sensors)

    def get_sensors(self):
        sensors = []
        if self.multi_sensors:
            for s in range(1, 5):
                sensor_id = "sensor_{:d}".format(s)
                if self.checkboxes[sensor_id].isChecked():
                    sensors.append(s)
        else:
            sensors.append(int(self.textbox.text()))

        return sensors

    def set_sensors(self, sensors):
        if not sensors:
            sensors = []

        if len(sensors) > 1:
            self.set_multi_sensor_support(True)

        if self.multi_sensors:
            for s in range(1, 5):
                enabled = s in sensors
                sensor_id = "sensor_{:d}".format(s)
                self.checkboxes[sensor_id].setChecked(enabled)
        else:
            if isinstance(sensors, list):
                sensors = sensors[0]
            try:
                self.textbox.setText(str(sensors))
            except Exception as e:
                self.error_handler("Could not set sensor {}".format(e))

    def set_multi_sensor_support(self, multi_sensors):
        if multi_sensors is None:
            multi_sensors = False
        self.textbox.setVisible(not multi_sensors)

        for s in range(1, 5):
            sensor_id = "sensor_{:d}".format(s)
            self.checkboxes[sensor_id].setVisible(multi_sensors)

        self.multi_sensors = multi_sensors

    def check_value(self):
        error = None
        if not self.textbox.text().isdigit():
            error = "Sensor must be an integer between 1 and 4!\n"
            self.textbox["sensor"].setText("1")
        else:
            sensor = int(self.textbox.text())
            e = sensor < 1 or sensor > 4
            if e:
                error = "Sensor must be an integer between 1 and 4!\n"
                self.textbox.setText("1")

        if error is not None and self.error_message is not None:
            self.error_handler(error)


class PassthroughProcessor:
    def __init__(self, sensor_config, processing_config):
        pass

    def process(self, data):
        return data
