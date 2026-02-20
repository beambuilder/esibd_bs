# -*- coding: utf-8 -*-
"""
Created on Wed May  8 12:50:56 2024

@author: Niclas
"""



import sys
import os
import re
import matplotlib.pyplot as plt
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QFileDialog, QLabel, QGridLayout
from datetime import datetime
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.animation import FuncAnimation
import matplotlib.dates as mdates

class RealTimePlot(QWidget):
    def __init__(self, log_file, parent=None):
        super(RealTimePlot, self).__init__(parent)
        self.log_file = log_file
        self.log_entries = []
        self.log_file_size = 0

        self.initUI()

    def initUI(self):
        self.figure = plt.figure()
        self.canvas = FigureCanvas(self.figure)
        self.layout = QVBoxLayout()
        self.layout.addWidget(self.canvas)
        self.setLayout(self.layout)

        self.ani = FuncAnimation(self.figure, self.update_plot, interval=1000) #delay between frames in ms

    def update_plot(self, i):
        current_size = os.path.getsize(self.log_file)

        if current_size > self.log_file_size:
            with open(self.log_file, 'r') as file:
                file.seek(self.log_file_size)
                new_data = file.readlines()
                self.log_entries.extend(new_data)
                self.log_file_size = current_size

        psu0_timestamps = []
        psu0_currents = []
        psu1_timestamps = []
        psu1_currents = []

        current_psu = None
        current_timestamp = None

        for entry in self.log_entries:
            # Check for PSU block header: e.g. "2026-02-20 14:51:58,089 - INFO - get_psu0_data() results:"
            psu_match = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d{3} - INFO - get_psu(\d)_data\(\) results:', entry)
            if psu_match:
                current_timestamp = datetime.strptime(psu_match.group(1), '%Y-%m-%d %H:%M:%S')
                current_psu = int(psu_match.group(2))
                continue

            # Check for Output Current line within a PSU block
            if current_psu is not None:
                current_match = re.match(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3} - INFO -\s+Output Current:\s+([\d.]+)A', entry)
                if current_match:
                    current_value = float(current_match.group(1))
                    if current_psu == 0:
                        psu0_timestamps.append(current_timestamp)
                        psu0_currents.append(current_value)
                    elif current_psu == 1:
                        psu1_timestamps.append(current_timestamp)
                        psu1_currents.append(current_value)
                    current_psu = None
                    current_timestamp = None

        self.figure.clear()

        ax1 = self.figure.add_subplot(211)
        ax1.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
        if psu0_timestamps:
            ax1.plot(psu0_timestamps, psu0_currents, label='PSU0 Current', marker='o', linestyle='-')
        ax1.set_xlabel('Time // HH:MM:SS')
        ax1.set_ylabel('Current // A')
        ax1.set_title('PSU0 Output Current')
        ax1.grid(True)
        ax1.legend()

        ax2 = self.figure.add_subplot(212)
        ax2.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
        if psu1_timestamps:
            ax2.plot(psu1_timestamps, psu1_currents, label='PSU1 Current', marker='o', linestyle='-')
        ax2.set_xlabel('Time // HH:MM:SS')
        ax2.set_ylabel('Current // A')
        ax2.set_title('PSU1 Output Current')
        ax2.grid(True)
        ax2.legend()

        self.figure.tight_layout()
        

class LogMonitorApp(QMainWindow):
    def __init__(self):
        super(LogMonitorApp, self).__init__()

        self.initUI()

    def initUI(self):
        self.central_widget = QWidget(self)
        self.setCentralWidget(self.central_widget)

        self.layout = QVBoxLayout()
        self.central_widget.setLayout(self.layout)

        self.select_log_button = QPushButton('Select Logging File', self)
        self.select_log_button.clicked.connect(self.select_log_file)
        self.layout.addWidget(self.select_log_button)

        self.log_file_label = QLabel('Selected Logging File:')
        self.layout.addWidget(self.log_file_label)

        self.plot_button = QPushButton('Add Live Plot', self)
        self.plot_button.clicked.connect(self.add_plot)
        self.layout.addWidget(self.plot_button)

        self.plot_container = QWidget(self)
        self.plot_layout = QGridLayout()
        self.plot_container.setLayout(self.plot_layout)
        self.layout.addWidget(self.plot_container)

        self.selected_log_file = None

    def select_log_file(self):
        options = QFileDialog.Options()
        options |= QFileDialog.ReadOnly
        file_name, _ = QFileDialog.getOpenFileName(self, 'Select Log File', '', 'Log Files (*.log);;All Files (*)', options=options)
        if file_name:
            self.selected_log_file = file_name
            self.log_file_label.setText(f'Selected Log File: {file_name}')

    def add_plot(self):
        if self.selected_log_file:
            plot_widget = RealTimePlot(self.selected_log_file)
            self.plot_layout.addWidget(plot_widget)

def main():
    app = QApplication(sys.argv)
    window = LogMonitorApp()
    window.setGeometry(100, 100, 800, 600)
    window.setWindowTitle('Log Watchdog')
    window.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
