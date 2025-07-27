import sys
from PyQt6.QtWidgets import (QApplication, QWidget, QPushButton, QLabel, QVBoxLayout, QHBoxLayout, QFrame, QLineEdit, QStackedLayout, QGraphicsBlurEffect)
from PyQt6.QtGui import QImage, QPixmap, QFont
from PyQt6.QtCore import Qt, pyqtSignal
import cv2

from FaceAnalysis import FaceAnalyzer
from FocusMonitor import FocusMonitor
from UserManager import UserManager
from IAPanel import IntentionalActionsPanel
from SettingsPanel import SettingsPanel
from FocusMonitor import generate_alert_audio
from StudyTechniquePanel import StudyTechniquePopup
import threading


class MainWindow(QWidget):
    frame_ready = pyqtSignal(object)
    def __init__(self):
        super().__init__()
        # # transparent background
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)

        self.setWindowTitle("DoNot Focus Monitor")
        self.setGeometry(100, 100, 1000, 600)

        self.setStyleSheet("""
            QWidget {
                 background-color: transparent;
            }
            QLabel {
                color: #333;
                font-size: 16px;
            }
            QPushButton {
                background-color: rgba(255, 255, 255, 0.5);
                border: 2px solid white;
                color: #333;
                border-radius: 10px;
                padding: 10px;
                font-size: 16px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.7);
            }
            QLineEdit {
                background-color: rgba(255, 255, 255, 0.6);
                border: 1px solid #ccc;
                padding: 8px;
                border-radius: 8px;
                font-size: 14px;
            }
        """
        )

        font = QFont("Segoe UI")
        font.setPointSize(12)
        self.setFont(font)

        self.user_manager = UserManager()
        self.current_user = None

        self.stack = QStackedLayout(self)
        self.setLayout(self.stack)

        self.login_widget = self.create_login_ui()
        self.app_widget = self.create_main_ui()

        self.stack.addWidget(self.login_widget)
        self.stack.addWidget(self.app_widget)

        self.frame_ready.connect(self.update_video_frame)

        self.cap = None
        self.analyzer = None
        self.monitor = FocusMonitor(user_manager=self.user_manager, fps=15)
        self.ia_panel = None

        self._last_alert_text = None
        self._last_alert_voice = None
        self._last_alert_volume = None

        self._last_cam_props = {
            'cam_brightness': None,
            'cam_contrast': None,
            'cam_exposure': None,
            'cam_saturation': None,
        }
        self.enable_camera_tuning = True



    def create_login_ui(self):
        widget = QWidget()
        outer_layout = QVBoxLayout(widget)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        # ---------- Custom Title Bar ----------
        title_bar = self.create_title_bar()
        outer_layout.addWidget(title_bar)

        # ---------- Background Blur ----------
        background_blur = QFrame()
        background_blur.setStyleSheet("""
            background-color: rgba(255, 255, 255, .75);
            border-radius: 0px;
        """)
        blur_effect = QGraphicsBlurEffect()
        blur_effect.setBlurRadius(100)
        background_blur.setGraphicsEffect(blur_effect)
        background_blur.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        # ---------- Foreground Form ----------
        form_card = QFrame()
        form_card.setStyleSheet("""
            background-color: rgba(255, 255, 255, 0.75);
            border-radius: 20px;
        """)
        form_layout = QVBoxLayout(form_card)
        form_layout.setContentsMargins(30, 30, 30, 30)
        form_layout.setSpacing(20)

        self.login_label = QLabel("Welcome to DoNot!  Please log in or create new user.")
        self.login_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.login_label.setStyleSheet("font-size: 16px; font-weight: bold; color: black;")
        form_layout.addWidget(self.login_label)

        self.login_error_label = QLabel("")
        self.login_error_label.setStyleSheet("color: red; font-size: 14px; background-color: transparent;")
        self.login_error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        form_layout.addWidget(self.login_error_label)

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Enter your username")
        self.username_input.setStyleSheet("""
            QLineEdit {
                color: black;
                padding: 10px;
                border-radius: 8px;
                border: 1px solid white;
                background-color: rgba(255, 255, 255, 0.5);
            }
        """)
        form_layout.addWidget(self.username_input)

        self.login_button = QPushButton("Login")
        self.signup_button = QPushButton("Create new user")

        for btn in [self.login_button, self.signup_button]:
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(40)
            btn.setStyleSheet("""
                            QPushButton {
                                background-color: #E0E0E0;
                                border-radius: 8px;
                                font-weight: bold;
                                font-size: 14px;
                            }
                            QPushButton:hover {
                                background-color: #D0D0D0;
                            }
                        """)

        form_layout.addWidget(self.login_button)
        form_layout.addWidget(self.signup_button)

        # ---------- Stack ----------
        stack = QStackedLayout()
        stack.setStackingMode(QStackedLayout.StackingMode.StackAll)
        stack.addWidget(background_blur)
        stack.addWidget(form_card)

        container = QWidget()
        container.setLayout(stack)
        outer_layout.addWidget(container)

        # ---------- Connect signals ----------
        self.login_button.clicked.connect(self.handle_login)
        self.signup_button.clicked.connect(self.handle_signup)

        return widget

    def initialize_analyzer(self):
        self.analyzer = FaceAnalyzer(use_dlib=False)  # turn off dlib for speed
        calibration_data = self.user_manager.get_calibration_data()

        if calibration_data:
            self.analyzer.calibration_data = calibration_data
            self.analyzer.baseline_vertical_ratio = calibration_data.get("vertical")
            self.analyzer.baseline_horizontal_ratio = calibration_data.get("horizontal")
            print("[Init] Loaded calibration from user data.")
        else:
            print("[Init] No calibration data found. Please calibrate.")

    def handle_login(self):
        name = self.username_input.text().strip()
        if not name:
            self.login_error_label.setText("Please enter a username in the text field")
            return
        if self.user_manager.login(name):
            self.current_user = name
            self.login_error_label.setText("")
            self.initialize_analyzer()
            self.apply_user_settings()
            self.stack.setCurrentWidget(self.app_widget)
            print(f"[Login] Logged in as: {name}")
        else:
            self.login_error_label.setText("User does not exist")

    def handle_signup(self):
        name = self.username_input.text().strip()
        if not name:
            self.login_error_label.setText("Please enter a username in the text field")
            return
        if self.user_manager.signup(name):
            self.current_user = name
            self.login_error_label.setText("")
            self.initialize_analyzer()
            self.stack.setCurrentWidget(self.app_widget)
        else:
            self.login_error_label.setText("Username already exists")

    def create_main_ui(self):
        widget = QWidget()
        outer_layout = QVBoxLayout(widget)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        # ---------- Custom Title Bar ----------
        title_bar = self.create_title_bar()
        outer_layout.addWidget(title_bar)  # Add to top

        # ---------- Background Blur ----------
        background_blur = QFrame()
        background_blur.setStyleSheet("""
            background-color: rgba(255, 255, 255, 0.15);
            border-radius: 0px;
        """)
        blur_effect = QGraphicsBlurEffect()
        blur_effect.setBlurRadius(0)
        background_blur.setGraphicsEffect(blur_effect)
        background_blur.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        # ---------- Foreground Layout ----------
        main_panel = QWidget()
        main_panel.setStyleSheet("background-color: rgba(255, 255, 255, 0.75);")
        layout = QHBoxLayout(main_panel)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)

        # Side Panel
        side_panel = QVBoxLayout()
        side_panel.setSpacing(15)

        self.btn_calibrate = QPushButton("Calibrate")
        self.btn_start = QPushButton("Start Monitoring")
        self.btn_pause = QPushButton("Pause")
        self.intentional_actions_button = QPushButton("Edit Intentional Actions")
        self.study_btn = QPushButton("Study Techniques")
        self.btn_settings = QPushButton("Settings")
        self.btn_logout = QPushButton("Log Out")

        for btn in [self.btn_calibrate, self.btn_start, self.btn_pause,
                    self.intentional_actions_button, self.study_btn, self.btn_settings, self.btn_logout]:
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(45)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #E0E0E0;
                    border-radius: 8px;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background-color: #D0D0D0;
                }
            """)

        side_panel.addWidget(self.btn_calibrate)
        side_panel.addWidget(self.btn_start)
        side_panel.addWidget(self.btn_pause)
        side_panel.addWidget(self.intentional_actions_button)
        side_panel.addWidget(self.study_btn)
        side_panel.addStretch(1)
        side_panel.addWidget(self.btn_settings)
        side_panel.addWidget(self.btn_logout)

        # Main Area
        content_layout = QVBoxLayout()
        self.status_label = QLabel("Status: Ready")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("font-size: 18px; color: #333;")

        self.video_label = QLabel("Camera feed will appear here")
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_label.setStyleSheet("background-color: black; color: #777;")
        self.video_label.setFixedHeight(400)

        content_layout.addWidget(self.status_label)
        content_layout.addWidget(self.video_label)

        layout.addLayout(side_panel, 1)
        layout.addLayout(content_layout, 4)

        # ---------- Stack Everything ----------
        stack = QStackedLayout()
        stack.setStackingMode(QStackedLayout.StackingMode.StackAll)
        stack.addWidget(background_blur)
        stack.addWidget(main_panel)

        container = QWidget()
        container.setLayout(stack)

        outer_layout.addWidget(container)

        # ---------- Connect Buttons ----------
        self.intentional_actions_button.clicked.connect(self.show_IA_panel)
        self.btn_calibrate.clicked.connect(self.on_calibrate_clicked)
        self.btn_start.clicked.connect(self.on_start_clicked)
        self.btn_pause.clicked.connect(self.on_pause_clicked)
        self.study_btn.clicked.connect(self.open_study_popup)
        self.btn_settings.clicked.connect(self.show_settings_panel)
        self.btn_logout.clicked.connect(self.on_logout_clicked)

        return widget

    def create_title_bar(self):
        title_bar = QWidget()
        title_bar.setFixedHeight(40)
        title_bar.setStyleSheet("""
            QWidget {
                background-color: rgba(30, 30, 30, 0.90);
                color: white;
            }
        """)

        layout = QHBoxLayout()
        layout.setContentsMargins(10, 0, 10, 0)

        title = QLabel("DoNot Focus Monitor")
        title.setStyleSheet("color: white; font-weight: bold; background-color: transparent;")
        title.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        btn_min = QPushButton("—")
        btn_max = QPushButton("□")
        btn_close = QPushButton("✕")

        for btn in [btn_min, btn_max, btn_close]:
            btn.setFixedSize(30, 25)
            btn.setStyleSheet("""
                QPushButton {
                    border: none;
                    background-color: transparent;
                    color: white;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background-color: rgba(255, 255, 255, 0.2);
                }
            """)

        btn_min.clicked.connect(self.showMinimized)
        btn_max.clicked.connect(self.toggle_max_restore)
        btn_close.clicked.connect(self.close)

        layout.addWidget(title)
        layout.addStretch()
        layout.addWidget(btn_min)
        layout.addWidget(btn_max)
        layout.addWidget(btn_close)

        title_bar.setLayout(layout)
        return title_bar

    def toggle_max_restore(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_position = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton:
            self.move(self.pos() + event.globalPosition().toPoint() - self.drag_position)
            self.drag_position = event.globalPosition().toPoint()

    def update_video_frame(self, frame):
        # Convert BGR -> RGB
        rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, _ = rgb_image.shape
        q_image = QImage(rgb_image.data, w, h, 3 * w, QImage.Format.Format_RGB888)
        pm = QPixmap.fromImage(q_image)

        # Cache target size to avoid querying layout constantly
        if not hasattr(self, "_vid_target_size"):
            self._vid_target_size = self.video_label.size()

        size_now = self.video_label.size()
        if size_now != self._vid_target_size:
            self._vid_target_size = size_now

        # Use FastTransformation (nearest-ish) instead of smooth every frame
        if self._vid_target_size.width() == w and self._vid_target_size.height() == h:
            self.video_label.setPixmap(pm)
        else:
            self.video_label.setPixmap(
                pm.scaled(
                    self._vid_target_size,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.FastTransformation,
                )
            )

    def on_calibrate_clicked(self):
        print("Calibrate button pressed")

        if self.monitor and self.monitor.is_monitoring:
            print("Stopping monitoring for calibration...")
            self.monitor.stop_monitoring()

        self.status_label.setText("Status: Calibrating...")

        # Store previous data in case of cancellation
        prev_calib = {
            "vertical": getattr(self.analyzer, "baseline_vertical_ratio", None),
            "horizontal": getattr(self.analyzer, "baseline_horizontal_ratio", None),
            "data": getattr(self.analyzer, "calibration_data", None)
        }

        self.cap = cv2.VideoCapture(0)
        result = self.analyzer.calibrate_gaze(self.cap)
        self.cap.release()
        cv2.destroyAllWindows()

        if result is not None:
            vertical, horizontal = result
            self.analyzer.baseline_vertical_ratio = vertical
            self.analyzer.baseline_horizontal_ratio = horizontal
            if self.current_user:
                self.user_manager.update_calibration_data({
                    "vertical": vertical,
                    "horizontal": horizontal
                })
            self.status_label.setText("Status: Ready")
        else:
            # Restore previous calibration
            self.analyzer.baseline_vertical_ratio = prev_calib["vertical"]
            self.analyzer.baseline_horizontal_ratio = prev_calib["horizontal"]
            if prev_calib["data"] is not None:
                self.analyzer.calibration_data = prev_calib["data"]
            print("[Calibration] Cancelled. Previous calibration restored.")
            self.status_label.setText("Status: Calibration cancelled.")

    def on_start_clicked(self):
        print("Start Monitoring button pressed")
        self.status_label.setText("Status: Monitoring.")
        print(f"[DBG] Monitor params before start: "
              f"fps={self.monitor.fps}, "
              f"threshold={self.monitor.threshold}, "
              f"cooldown={self.monitor.cooldown_seconds}, "
              f"window_s={self.monitor.window_seconds}")
        if self.cap is None or not self.cap.isOpened():
            self.cap = cv2.VideoCapture(0)
            actual_fps = self.cap.get(cv2.CAP_PROP_FPS)
            w = self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)
            h = self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
            print(f"[DBG] Camera opened: {w}x{h} @ {actual_fps} fps (driver report)")

        # Apply current user settings to monitor + camera before starting.
        self.apply_user_settings()

        if self.current_user:
            actions = self.user_manager.get_intentional_actions()
            self.monitor.set_intent_actions(actions)

        if not self.monitor.is_monitoring:
            self.monitor.start_monitoring(
                self.cap,
                self.analyzer,
                frame_callback = self.frame_ready.emit,
                intent_actions = self.user_manager.get_intentional_actions() if self.current_user else None,
            )

    def on_pause_clicked(self):
        print("Pause button pressed")
        self.status_label.setText("Status: Paused")
        self.monitor.stop_monitoring()
        if self.cap:
            self.cap.release()
            self.cap = None

    def show_IA_panel(self):
        self.ia_panel = IntentionalActionsPanel(
            user_manager=self.user_manager,
            current_user=self.current_user,
            save_callback=self.reload_intentional_actions
        )
        print("Showing IA panel...")
        self.ia_panel.show()

    def open_study_popup(self):
        if not hasattr(self, 'study_popup') or self.study_popup is None:
            self.study_popup = StudyTechniquePopup(self)
        self.study_popup.show()
        self.study_popup.raise_()
        self.study_popup.activateWindow()

    def reload_intentional_actions(self):
        if self.current_user:
            actions = self.user_manager.get_intentional_actions()
            self.monitor.set_intent_actions(actions)
            print(f"[GUI] Intentional actions reloaded: {actions}")

    def show_settings_panel(self):
        if not self.current_user:
            print("[Settings] No user logged in; ignoring.")
            return
        self.settings_panel = SettingsPanel(
            user_manager=self.user_manager,
            current_user=self.current_user,
            save_callback=self.apply_user_settings,  # optional
            monitor=self.monitor,
            parent=self,
        )
        # Center over main window
        g = self.geometry()
        self.settings_panel.move(
            g.center().x() - self.settings_panel.width() // 2,
            g.center().y() - self.settings_panel.height() // 2
        )
        self.settings_panel._load_values()
        self.settings_panel.show()
        self.settings_panel.raise_()

    def apply_user_settings(self):
        s = self.user_manager.get_current_user_data().get('settings', {})

        # Reconfigure live monitor (if open)
        self.monitor.reconfigure(
            threshold=float(s.get('alert_threshold', self.monitor.threshold)),
            cooldown_seconds=int(s.get('cooldown_seconds', self.monitor.cooldown_seconds)),
            fps=int(s.get('fps', self.monitor.fps)),
            window_seconds=int(s.get('window_seconds', self.monitor.window_seconds)),
        )

        # (Re)generate alert audio only if something changed, and do it off the UI thread.
        alert_text = self.user_manager.get_setting('alert_text') or "Stay focused!"
        alert_voice = self.user_manager.get_setting('alert_voice') or "en-US-JennyNeural"
        alert_volume = int(self.user_manager.get_setting('alert_volume') or 100)

        changed = (
                alert_text != self._last_alert_text or
                alert_voice != self._last_alert_voice or
                alert_volume != self._last_alert_volume
        )

        if changed:
            self._last_alert_text = alert_text
            self._last_alert_voice = alert_voice
            self._last_alert_volume = alert_volume

            def _tts_worker():
                try:
                    from FocusMonitor import generate_alert_audio, get_alert_audio_filename
                    filename = get_alert_audio_filename(self.current_user)
                    generate_alert_audio(
                        text=alert_text,
                        voice=alert_voice,
                        volume_pct=alert_volume,
                        filename=filename,
                    )
                except Exception as e:
                    print(f"[Settings] Could not regenerate alert audio: {e}")

            threading.Thread(target=_tts_worker, daemon=True).start()

    def reload_settings(self):
        # ----- load & apply monitor parameters -----
        thresh = self.user_manager.get_setting('alert_threshold')
        if thresh is not None:
            try:
                self.monitor.threshold = float(thresh)
            except Exception:
                pass

        cooldown = self.user_manager.get_setting('cooldown_seconds')
        if cooldown is not None:
            try:
                self.monitor.cooldown_seconds = int(cooldown)
            except Exception:
                pass

        fps = self.user_manager.get_setting('fps')
        window_s = self.user_manager.get_setting('window_seconds')
        try:
            if fps is not None:
                fps = int(fps)
                self.monitor.max_samples = (
                                               int(window_s) if window_s is not None else self.monitor.window_seconds) * fps
                if window_s is not None:
                    self.monitor.window_seconds = int(window_s)
        except Exception:
            pass

        # ----- regenerate alert audio (critical for your issue) -----
        alert_text = self.user_manager.get_setting('alert_text') or "Stay focused!"
        alert_voice = self.user_manager.get_setting('alert_voice') or "en-US-JennyNeural"
        alert_volume = self.user_manager.get_setting('alert_volume')
        if alert_volume is None:
            alert_volume = 100

        try:
            # Overwrite the default file FocusMonitor plays. :contentReference[oaicite:5]{index=5}
            generate_alert_audio(
                text=alert_text,
                voice=alert_voice,
                volume_pct=int(alert_volume),
                filename="alert.wav",
            )
        except Exception as e:
            print(f"[GUI] Failed to regenerate alert audio: {e}")

        print("[GUI] Settings reloaded & alert audio regenerated.")

    def on_logout_clicked(self):
        print(f"[Logout] Logging out user: {self.current_user}")

        # close open panels
        if hasattr(self, 'settings_panel') and self.settings_panel is not None:
            self.settings_panel.close()
            self.settings_panel = None
        if hasattr(self, 'study_popup') and self.study_popup is not None:
            self.study_popup.close()
            self.study_popup = None
        if hasattr(self, 'ia_panel') and self.ia_panel is not None:
            self.ia_panel.close()
            self.ia_panel = None
        self.current_user = None
        self.user_manager.current_user = None
        self.stack.setCurrentWidget(self.login_widget)
        self.status_label.setText("Status: Ready")
        self.username_input.clear()
        if self.monitor and self.monitor.is_monitoring:
            print("Stopping monitoring for calibration...")
            self.monitor.stop_monitoring()
        if self.cap:
            self.cap.release()
            self.cap = None

    def open_camera_safely(index=0, backend=cv2.CAP_ANY,
                           width=1280, height=720, fps=30,
                           saturation=None):
        cap = cv2.VideoCapture(index, backend)
        if not cap.isOpened():
            cap = cv2.VideoCapture(index)
        if not cap.isOpened():
            return None

        # Hint at color; harmless if unsupported
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
        cap.set(cv2.CAP_PROP_CONVERT_RGB, 1)
        cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.75)

        if saturation is not None:
            cap.set(cv2.CAP_PROP_SATURATION, saturation)

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        cap.set(cv2.CAP_PROP_FPS, fps)
        return cap


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
