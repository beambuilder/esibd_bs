# -*- coding: utf-8 -*-
"""
Created on Wed May  8 12:50:56 2024

@author: Niclas
"""



import sys
import os
import re
import matplotlib.pyplot as plt
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QFileDialog, QLabel, QLineEdit, QGridLayout, QVBoxLayout
from datetime import datetime
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.animation import FuncAnimation
import matplotlib.dates as mdates

class RealTimePlot(QWidget):
    def __init__(self, log_file, value_strings, parent=None):
        super(RealTimePlot, self).__init__(parent)
        self.log_file = log_file
        self.value_strings = value_strings
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

    def parse_log_entry(self, line):
        match = re.match(r'(\d{2}-\d{2}-\d{4} \d{2}:\d{2}:\d{2}.\d{3}) \| INFO     \| (\w+: \w+)\s+= (-?\d+\.\d+) (\w+)', line)
        if match:
            timestamp_str, value_name, value, unit = match.groups()
            timestamp = datetime.strptime(timestamp_str, '%d-%m-%Y %H:%M:%S.%f')
            #print(f"{unit}")
            return timestamp, value_name, float(value), unit
        return None, None, None, None

    def update_plot(self, i):
        current_size = os.path.getsize(self.log_file)

        if current_size > self.log_file_size:
            with open(self.log_file, 'r') as file:
                file.seek(self.log_file_size)
                new_data = file.readlines()
                self.log_entries.extend(new_data)
                self.log_file_size = current_size

        timestamps = []
        values = {value: [] for value in self.value_strings}

        for entry in self.log_entries:
            timestamp, value_name, value, unit = self.parse_log_entry(entry)
            if timestamp and value_name in self.value_strings:
                timestamps.append(timestamp)
                values[value_name].append(value)

        self.figure.clear()
        ax = self.figure.add_subplot(111)
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
        for value_name, value_data in values.items():
            ax.plot(timestamps, value_data, label=value_name, marker='o', linestyle='-')
        ax.set_xlabel('Time // HH:MM:SS')
        #print(f"{unit}")
        ax.set_ylabel(f"{value_name} // {unit}")
        ax.set_title('Real-Time Data')
        ax.grid(True)
        ax.legend()
        

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

        self.value_strings_label = QLabel('Enter Value Strings (comma-separated):')
        self.layout.addWidget(self.value_strings_label)

        self.value_strings_input = QLineEdit(self)
        self.layout.addWidget(self.value_strings_input)

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
            value_strings = self.value_strings_input.text().split(',')
            plot_widget = RealTimePlot(self.selected_log_file, value_strings)
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
