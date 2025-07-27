from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QSpinBox, QPushButton, QMessageBox, QApplication
)

from PyQt6.QtCore import Qt, QTimer, QDateTime
from PyQt6.QtGui import QColor

class StudyTechniquePopup(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Study Techniques")
        self.setMinimumWidth(440)
        self.setMinimumHeight(230)
        self.setStyleSheet("""
            background-color: rgba(255,255,255,0.85);
            border-radius: 22px;
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("""
            font-size: 1.08em;
            color: #4780d4;
            font-weight: bold;
            background: transparent;
        """)
        # Create a horizontal layout for top bar
        top_bar = QHBoxLayout()
        top_bar.addStretch(1)  # Pushes label to the right
        top_bar.addWidget(self.status_label)
        layout.addLayout(top_bar)

        # Technique selection
        row1 = QHBoxLayout()
        technique_label = QLabel("Technique:")
        self.technique_combo = QComboBox()
        self.technique_combo.setStyleSheet("""
        QComboBox {
            background: rgba(255,255,255,0.96);
            border-radius: 8px;
            border: 2px solid #4F8CFF;
            padding: 6px 10px;
            font-size: 1em;
            color: #222;
        }
        QComboBox::drop-down {
            border: none;
        }
        QComboBox QAbstractItemView {
            background: #f6f7fb;
            color: #222;
            border-radius: 8px;
            border: 1.5px solid #b0b0b0;
            font-size: 1em;
            selection-background-color: #c5d8fa;
            selection-color: #212f4a;
        }
        QComboBox:focus {
            border: 2.5px solid #4F8CFF;
        }
        QComboBox:hover {
            border: 2.5px solid #82B1FF;
        }
        """)

        self.technique_combo.addItems([
            "Pomodoro (25/5)",
            "52/17",
            "Spaced Repetition",
            "Custom"
        ])
        row1.addWidget(technique_label)
        row1.addWidget(self.technique_combo)
        layout.addLayout(row1)

        # Custom times
        row2 = QHBoxLayout()
        self.focus_spin = QSpinBox()
        self.focus_spin.setRange(1, 180)
        self.focus_spin.setValue(25)
        self.focus_spin.setSuffix(" min focus")
        self.focus_spin.setStyleSheet("""
            background: rgba(240,240,250,1);
            border-radius: 8px;
            padding: 6px 8px;
            font-size: 1em;
            color: #222;
        """)
        self.break_spin = QSpinBox()
        self.break_spin.setRange(1, 90)
        self.break_spin.setValue(5)
        self.break_spin.setSuffix(" min break")
        self.break_spin.setStyleSheet(self.focus_spin.styleSheet())
        row2.addWidget(self.focus_spin)
        row2.addWidget(self.break_spin)
        layout.addLayout(row2)
        self.focus_spin.hide()
        self.break_spin.hide()

        self.technique_combo.currentIndexChanged.connect(self.update_for_technique)

        # Start/Stop buttons
        self.start_btn = QPushButton("Start")
        self.stop_btn = QPushButton("Stop")
        btn_style = """
            background: #4F8CFF;
            color: white;
            border-radius: 10px;
            padding: 10px 30px;
            font-size: 1.05em;
            font-weight: bold;
        """
        self.start_btn.setStyleSheet(btn_style)
        self.stop_btn.setStyleSheet(btn_style.replace("#4F8CFF", "#CCCCCC").replace("white", "#333"))
        self.stop_btn.setEnabled(False)
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_row.addWidget(self.start_btn)
        btn_row.addWidget(self.stop_btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        self.pause_resume_btn = QPushButton("Pause")
        self.pause_resume_btn.setEnabled(False)
        btn_row.addWidget(self.pause_resume_btn)
        self.pause_resume_btn.clicked.connect(self.pause_or_resume_technique)
        self.is_paused = False
        self.remaining_ms = 0
        self.pause_resume_btn.setStyleSheet("""
            background: #ff5858;
            color: white;
            border-radius: 10px;
            padding: 10px 30px;
            font-size: 1.05em;
            font-weight: bold;
        """)

        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.timer_tick)
        self.in_focus = True
        self.cycles = 0

        self.time_label = QLabel("Time: 00:00")
        self.time_label.setStyleSheet("""
            font-size: 1.25em;
            color: #263;
            background: transparent;
            qproperty-alignment: 'AlignHCenter | AlignVCenter';
        """)
        layout.addWidget(self.time_label)

        self.time_update_timer = QTimer(self)
        self.time_update_timer.timeout.connect(self.update_time_label)

        self.spaced_repetition_intervals = [5, 10, 20, 40, 60]  # In minutes
        self.spaced_index = 0

        self.start_btn.clicked.connect(self.start_technique)
        self.stop_btn.clicked.connect(self.stop_technique)

        self.update_for_technique()

    def update_for_technique(self):
        technique = self.technique_combo.currentText()
        custom = (technique == "Custom")
        self.focus_spin.setVisible(custom)
        self.break_spin.setVisible(custom)
        if technique == "Pomodoro (25/5)":
            self.focus_spin.setValue(25)
            self.break_spin.setValue(5)
        elif technique == "52/17":
            self.focus_spin.setValue(52)
            self.break_spin.setValue(17)
        elif technique == "Spaced Repetition":
            self.spaced_index = 0
        self.adjustSize()

    def start_technique(self):
        self.in_focus = True
        self.cycles = 0
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.pause_resume_btn.setEnabled(True)
        self.pause_resume_btn.setText("Pause")
        self.pause_resume_btn.setStyleSheet("""
            background: #ff5858;
            color: white;
            border-radius: 10px;
            padding: 10px 30px;
            font-size: 1.05em;
            font-weight: bold;
        """)
        self.is_paused = False
        self.remaining_ms = 0

        if self.technique_combo.currentText() == "Spaced Repetition":
            self.spaced_index = 0
            self.next_spaced_repetition()
        else:
            self.next_phase()

    def stop_technique(self):
        self.timer.stop()
        self.status_label.setText("Ready")
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.spaced_index = 0  # Reset
        self.pause_resume_btn.setEnabled(False)
        self.pause_resume_btn.setText("Pause")
        self.pause_resume_btn.setStyleSheet("""
            background: #ff5858;
            color: white;
            border-radius: 10px;
            padding: 10px 30px;
            font-size: 1.05em;
            font-weight: bold;
        """)
        self.is_paused = False
        self.remaining_ms = 0
        self.time_update_timer.stop()
        self.time_label.setText("Time: 00:00")

    def pause_or_resume_technique(self):
        if not self.is_paused:
            if self.timer.isActive():
                self.is_paused = True
                self.remaining_ms = self.timer.remainingTime()
                self.timer.stop()
                self.pause_resume_btn.setText("Resume")
                self.pause_resume_btn.setStyleSheet("""
                    background: #65c96f;
                    color: white;
                    border-radius: 10px;
                    padding: 10px 30px;
                    font-size: 1.05em;
                    font-weight: bold;
                """)
                now = QDateTime.currentDateTime()
                self.remaining_ms = now.msecsTo(self.end_time)
                self.time_update_timer.stop()
                self.timer.stop()
                self.is_paused = True
                self.pause_resume_btn.setText("Resume")


        else:
            if self.remaining_ms > 0:
                self.timer.start(self.remaining_ms)
                self.is_paused = False
                self.pause_resume_btn.setText("Pause")
                self.pause_resume_btn.setStyleSheet("""
                    background: #ff5858;
                    color: white;
                    border-radius: 10px;
                    padding: 10px 30px;
                    font-size: 1.05em;
                    font-weight: bold;
                """)
                self.end_time = QDateTime.currentDateTime().addMSecs(self.remaining_ms)
                self.time_update_timer.start(1000)
                self.timer.start(self.remaining_ms)
                self.is_paused = False
                self.pause_resume_btn.setText("Pause")

    def next_phase(self):
        if self.in_focus:
            mins = self.focus_spin.value()
        else:
            mins = self.break_spin.value()
        duration_ms = mins * 60 * 1000
        self.end_time = QDateTime.currentDateTime().addMSecs(duration_ms)
        self.time_update_timer.start(1000)
        self.update_time_label()
        self.timer.start(duration_ms)
        # existing Pomodoro and 52/17 logic
        technique = self.technique_combo.currentText()
        if technique == "Spaced Repetition":
            self.next_spaced_repetition()
        else:
            if self.in_focus:
                mins = self.focus_spin.value()
                msg = "Focus time! Stay on task."
                self.status_label.setText("Study time!")

            else:
                mins = self.break_spin.value()
                msg = "Break time! Step away!"
                self.status_label.setText("Break time!")
            self.reminder(msg)
            self.in_focus = not self.in_focus
            self.cycles += 1

    def timer_tick(self):
        technique = self.technique_combo.currentText()
        self.pause_resume_btn.setEnabled(True)
        self.pause_resume_btn.setText("Pause")
        self.pause_resume_btn.setStyleSheet("""
            background: #ff5858;
            color: white;
            border-radius: 10px;
            padding: 10px 30px;
            font-size: 1.05em;
            font-weight: bold;
        """)

        if technique == "Spaced Repetition":
            self.next_spaced_repetition()
        else:
            self.next_phase()

    def update_time_label(self):
        now = QDateTime.currentDateTime()
        ms_left = now.msecsTo(self.end_time)
        if ms_left < 0:
            ms_left = 0
        minutes = ms_left // (60 * 1000)
        seconds = (ms_left % (60 * 1000)) // 1000
        self.time_label.setText(f"Time: {minutes:02d}:{seconds:02d}")

    def next_spaced_repetition(self):
        # In next_spaced_repetition():
        if self.spaced_index < len(self.spaced_repetition_intervals):
            mins = self.spaced_repetition_intervals[self.spaced_index]
            msg = f"Review now! Next in {mins} min."
            self.status_label.setText("Review!")
            self.reminder(msg)
            duration_ms = mins * 60 * 1000
            self.end_time = QDateTime.currentDateTime().addMSecs(duration_ms)
            self.time_update_timer.start(1000)
            self.update_time_label()
            self.timer.start(duration_ms)
            self.spaced_index += 1
        else:
            self.reminder("Spaced Repetition complete! Great job.")
            self.stop_technique()

    def reminder(self, msg):
        # Visual popup
        msgbox = QMessageBox(self)
        msgbox.setWindowTitle("Study Technique")
        msgbox.setText(msg)
        msgbox.setStyleSheet("""
            QMessageBox {
                background-color: rgba(255,255,255,0.92);
                border-radius: 18px;
                font-size: 1.1em;
            }
            QLabel {
                color: #223;
                font-size: 1.1em;
            }
            QPushButton {
                background: #81C784;
                color: white;
                border-radius: 8px;
                padding: 8px 22px;
                font-weight: bold;
                font-size: 1em;
            }
            QPushButton:hover {
                background: #66bb6a;
            }
        """)
        QApplication.beep()
        msgbox.exec()


    def closeEvent(self, event):
        self.hide()
        event.ignore()


