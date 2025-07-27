from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame, QStackedLayout,
    QGraphicsBlurEffect, QTabWidget, QLineEdit, QDoubleSpinBox, QSpinBox, QSlider,
    QComboBox, QSizePolicy
)
from PyQt6.QtCore import Qt
import asyncio
import os
from pydub import AudioSegment
import edge_tts
from FocusMonitor import play_alert_audio

import cv2
import tempfile
import threading
import sounddevice as sd



class SettingsPanel(QWidget):

    def __init__(self, user_manager, current_user, save_callback=None, monitor=None, parent=None):
        super().__init__(parent)
        self.user_manager = user_manager
        self.current_user = current_user
        self.save_callback = save_callback
        self.monitor = monitor

        # Acrylic + frameless (match MainWindow aesthetic)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setWindowTitle("Settings")
        self.resize(520, 420)

        self._cached_preview_voice = None
        self._cached_preview_text = None
        self._cached_preview_audio = None  # pydub.AudioSegment

        # internal to detect changed alert text/voice
        self._last_alert_text = None
        self._last_alert_voice = None

        self._build_ui()
        self._load_values()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Title Bar
        title_bar = self._create_title_bar()
        outer.addWidget(title_bar)

        bg = QFrame()
        bg.setStyleSheet("""
            QFrame {
                background-color: rgba(255, 255, 255, 0.15);
                border-radius: 0px;
            }
        """)
        blur = QGraphicsBlurEffect()
        blur.setBlurRadius(25)
        bg.setGraphicsEffect(blur)
        bg.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: rgba(255, 255, 255, 0.9);
                border-bottom-left-radius: 16px;
                border-bottom-right-radius: 16px;
            }
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(12)

        # Tab widget
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setTabPosition(QTabWidget.TabPosition.North)
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: none;
            }
            QTabBar::tab {
                background: rgba(255,255,255,0.6);
                padding: 6px 18px;
                margin-right: 2px;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                color: #333;
                font-size: 14px;
            }
            QTabBar::tab:selected {
                background: rgba(255,255,255,0.95);
                font-weight: bold;
            }
            QTabBar::tab:hover {
                background: rgba(255,182,193,0.6);
            }
        """)

        # Build each tab
        self.tab_audio = self._build_tab_audio()
        self.tab_video = self._build_tab_video()
        self.tab_monitor = self._build_tab_monitor()

        self.tabs.addTab(self.tab_audio, "Audio")
        self.tabs.addTab(self.tab_video, "Video")
        self.tabs.addTab(self.tab_monitor, "Monitor")

        card_layout.addWidget(self.tabs)

        # Bottom action buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_save = QPushButton("Save")
        for b, bgcol, hovercol in (
            (self.btn_cancel, "#E0E0E0", "#D0D0D0"),
            (self.btn_save,   "#8BC34A", "#7CB342"),
        ):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFixedHeight(32)
            b.setStyleSheet(f"""
                QPushButton {{
                    background-color: {bgcol};
                    color: white;
                    padding: 4px 16px;
                    font-size: 14px;
                    border-radius: 8px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background-color: {hovercol};
                }}
            """)

        self.btn_cancel.clicked.connect(self.close)
        self.btn_save.clicked.connect(self._save_and_close)

        btn_row.addWidget(self.btn_cancel)
        btn_row.addWidget(self.btn_save)
        card_layout.addLayout(btn_row)

        stack = QStackedLayout()
        stack.setStackingMode(QStackedLayout.StackingMode.StackAll)
        stack.addWidget(bg)
        stack.addWidget(card)

        container = QWidget()
        container.setLayout(stack)
        outer.addWidget(container)

    # AUDIO TAB
    def _build_tab_audio(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(12)

        # Output device selection
        out_row = QHBoxLayout()
        out_label = QLabel("Output Device:")
        out_label.setStyleSheet("color:#333; font-size:14px; background:transparent;")
        self.combo_output = QComboBox()
        self.combo_output.setStyleSheet(
            "background:rgba(255,255,255,0.9); color:black; border-radius:6px; padding:2px 6px;")

        try:
            devices = sd.query_devices()
            output_devices = [d['name'] for d in devices if d['max_output_channels'] > 0]
            if output_devices:
                self.combo_output.addItems(output_devices)
            else:
                self.combo_output.addItem("Default Output")
        except Exception as e:
            self.combo_output.addItem("Default Output")

        out_row.addWidget(out_label)
        out_row.addWidget(self.combo_output, 1)
        lay.addLayout(out_row)

        lbl = QLabel("Alert Message Text")
        lbl.setStyleSheet("color:#333; font-size:14px; font-weight:bold; background:transparent;")
        lay.addWidget(lbl)

        self.edit_alert_text = QLineEdit()
        self.edit_alert_text.setPlaceholderText("What should the alert say?")
        self.edit_alert_text.setStyleSheet("""
            QLineEdit {
                background-color: rgba(255,255,255,0.8);
                border: 2px solid #FFB6C1;
                border-radius: 8px;
                padding: 6px 8px;
                color: black;
            }
            QLineEdit:focus { border-color:#FF9AA2; }
        """)
        lay.addWidget(self.edit_alert_text)

        # Voice selection
        lblv = QLabel("Voice")
        lblv.setStyleSheet("color:#333; font-size:14px; font-weight:bold; background:transparent;")
        lay.addWidget(lblv)

        self.combo_voice = QComboBox()
        self.combo_voice.setStyleSheet("background:rgba(255,255,255,0.9); color:black; border-radius:6px; padding:2px 6px;")
        # Sample voices list; extend as needed
        voice_ids = [
            "en-AU-NatashaNeural",
            "en-AU-WilliamNeural",
            "en-CA-ClaraNeural",
            "en-CA-LiamNeural",
            "en-GB-LibbyNeural",
            "en-GB-MaisieNeural",
            "en-GB-RyanNeural",
            "en-GB-SoniaNeural",
            "en-GB-ThomasNeural",
            "en-HK-SamNeural",
            "en-HK-YanNeural",
            "en-IE-ConnorNeural",
            "en-IE-EmilyNeural",
            "en-IN-NeerjaExpressiveNeural",
            "en-IN-NeerjaNeural",
            "en-IN-PrabhatNeural",
            "en-KE-AsiliaNeural",
            "en-KE-ChilembaNeural",
            "en-NG-AbeoNeural",
            "en-NG-EzinneNeural",
            "en-NZ-MitchellNeural",
            "en-NZ-MollyNeural",
            "en-PH-JamesNeural",
            "en-PH-RosaNeural",
            "en-SG-LunaNeural",
            "en-SG-WayneNeural",
            "en-TZ-ElimuNeural",
            "en-TZ-ImaniNeural",
            "en-US-AnaNeural",
            "en-US-AndrewMultilingualNeural",
            "en-US-AndrewNeural",
            "en-US-AriaNeural",
            "en-US-AvaMultilingualNeural",
            "en-US-AvaNeural",
            "en-US-BrianMultilingualNeural",
            "en-US-BrianNeural",
            "en-US-ChristopherNeural",
            "en-US-EmmaMultilingualNeural",
            "en-US-EmmaNeural",
            "en-US-EricNeural",
            "en-US-GuyNeural",
            "en-US-JennyNeural",
            "en-US-MichelleNeural",
            "en-US-RogerNeural",
            "en-US-SteffanNeural",
            "en-ZA-LeahNeural",
            "en-ZA-LukeNeural",
        ]
        self.combo_voice.addItems(voice_ids)

        lay.addWidget(self.combo_voice)

        # Volume
        vl = QHBoxLayout()
        vl.setSpacing(8)
        vlabel = QLabel("Volume:")
        vlabel.setStyleSheet("color:#333; background:transparent; font-size:14px;")
        self.slider_volume = QSlider(Qt.Orientation.Horizontal)
        self.slider_volume.setRange(0, 100)
        self.slider_volume.setValue(100)
        self.slider_volume.setStyleSheet("margin:0 8px;")
        self.lbl_vol_val = QLabel("100%")
        self.lbl_vol_val.setStyleSheet("color:#333; font-size:14px; background:transparent;")
        self.slider_volume.valueChanged.connect(lambda v: self.lbl_vol_val.setText(f"{v}%"))
        vl.addWidget(vlabel)
        vl.addWidget(self.slider_volume, 1)
        vl.addWidget(self.lbl_vol_val)
        lay.addLayout(vl)

        # Preview
        self.btn_preview_audio = QPushButton("Preview Alert")
        self.btn_preview_audio.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_preview_audio.setFixedHeight(50)
        self.btn_preview_audio.setStyleSheet("""
            QPushButton { background-color:#FFB6C1; color:white; border-radius:8px; font-weight:bold; }
            QPushButton:hover { background-color:#FF9AA2; }
        """)
        self.btn_preview_audio.clicked.connect(self._preview_audio)
        lay.addWidget(self.btn_preview_audio)

        lay.addStretch(1)
        return w

    # VIDEO TAB
    def _build_tab_video(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(12)

        # Webcam selection
        webcam_row = QHBoxLayout()
        webcam_label = QLabel("Webcam:")
        webcam_label.setStyleSheet("color:#333; font-size:14px; background:transparent;")
        self.combo_webcam = QComboBox()
        self.combo_webcam.setStyleSheet(
            "background:rgba(255,255,255,0.9); color:black; border-radius:6px; padding:2px 6px;")

        # Detect available webcams (indices 0-4)
        available_cams = []
        for idx in range(5):
            cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)  # CAP_DSHOW is optional but faster on Windows
            if cap.isOpened():
                available_cams.append(f"Camera {idx}")
                cap.release()
        if not available_cams:
            available_cams = ["Camera 0"]
        self.combo_webcam.addItems(available_cams)

        webcam_row.addWidget(webcam_label)
        webcam_row.addWidget(self.combo_webcam, 1)
        lay.addLayout(webcam_row)

        # helper to add slider rows
        def add_vid_slider(label_text, attr_name, minimum=0, maximum=100, default=50):
            row = QHBoxLayout()
            row.setSpacing(8)
            lbl = QLabel(label_text)
            lbl.setStyleSheet("color:#333; font-size:14px; background:transparent;")
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(minimum, maximum)
            slider.setValue(default)
            val_lbl = QLabel(str(default))
            val_lbl.setStyleSheet("color:#333; background:transparent; font-size:14px;")
            slider.valueChanged.connect(lambda v, lab=val_lbl: lab.setText(str(v)))
            row.addWidget(lbl)
            row.addWidget(slider, 1)
            row.addWidget(val_lbl)
            lay.addLayout(row)
            setattr(self, attr_name, slider)

        add_vid_slider("Brightness", "slider_brightness")
        add_vid_slider("Contrast",   "slider_contrast")
        add_vid_slider("Exposure",   "slider_exposure")
        add_vid_slider("Saturation", "slider_saturation")

        lay.addStretch(1)
        return w

    # MONITOR TAB
    def _build_tab_monitor(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(12)

        # Alert threshold
        row_thresh = QHBoxLayout()
        lblt = QLabel("Alert Threshold:")
        lblt.setStyleSheet("color:#333; background:transparent; font-size:14px;")
        self.spin_thresh = QDoubleSpinBox()
        self.spin_thresh.setRange(0.0, 1.0)
        self.spin_thresh.setSingleStep(0.01)
        self.spin_thresh.setDecimals(2)
        self.spin_thresh.setFixedWidth(100)
        self.spin_thresh.setMinimumWidth(100)
        self.spin_thresh.setMinimumHeight(32)
        self.spin_thresh.setStyleSheet("""
            QDoubleSpinBox {
                background-color: rgba(255,255,255,0.8);
                border: 2px solid #FFB6C1;
                border-radius: 8px;
                padding: 2px 6px;
                color: black;
            }
            QDoubleSpinBox:focus { border-color:#FF9AA2; }
        """)
        row_thresh.addWidget(lblt)
        row_thresh.addStretch(1)
        row_thresh.addWidget(self.spin_thresh)
        lay.addLayout(row_thresh)

        # Cooldown seconds
        row_cd = QHBoxLayout()
        lblc = QLabel("Cooldown (sec):")
        lblc.setStyleSheet("color:#333; background:transparent; font-size:14px;")
        self.spin_cooldown = QSpinBox()
        self.spin_cooldown.setRange(0, 600)
        self.spin_cooldown.setValue(15)
        self.spin_cooldown.setFixedWidth(100)
        self.spin_cooldown.setMinimumHeight(32)
        self.spin_cooldown.setStyleSheet("background:rgba(255,255,255,0.8); border:2px solid #FFB6C1; border-radius:8px; color:black;")
        row_cd.addWidget(lblc)
        row_cd.addStretch(1)
        row_cd.addWidget(self.spin_cooldown)
        lay.addLayout(row_cd)

        # FPS -----------------------------------------------------------------
        row_fps = QHBoxLayout()
        lblf = QLabel("FPS:")
        lblf.setStyleSheet("color:#333; background:transparent; font-size:14px;")
        self.spin_fps = QSpinBox()
        self.spin_fps.setRange(1, 60)
        self.spin_fps.setValue(10)
        self.spin_fps.setFixedWidth(100)
        self.spin_fps.setMinimumHeight(32)
        self.spin_fps.setStyleSheet("background:rgba(255,255,255,0.8); border:2px solid #FFB6C1; border-radius:8px; color:black;")
        row_fps.addWidget(lblf)
        row_fps.addStretch(1)
        row_fps.addWidget(self.spin_fps)
        lay.addLayout(row_fps)

        # Window seconds ------------------------------------------------------
        row_ws = QHBoxLayout()
        lblw = QLabel("Sample Window (sec):")
        lblw.setStyleSheet("color:#333; background:transparent; font-size:14px;")
        self.spin_window = QSpinBox()
        self.spin_window.setRange(1, 120)
        self.spin_window.setValue(5)
        self.spin_window.setFixedWidth(100)
        self.spin_window.setMinimumHeight(32)
        self.spin_window.setStyleSheet("background:rgba(255,255,255,0.8); border:2px solid #FFB6C1; border-radius:8px; color:black;")
        row_ws.addWidget(lblw)
        row_ws.addStretch(1)
        row_ws.addWidget(self.spin_window)
        lay.addLayout(row_ws)

        lay.addStretch(1)
        return w

    def _create_title_bar(self):
        bar = QFrame()
        bar.setFixedHeight(36)
        bar.setStyleSheet("""
            QFrame {
                background-color: rgba(30, 30, 30, 0.75);
                color: white;
                border-top-left-radius: 16px;
                border-top-right-radius: 16px;
            }
        """)

        lay = QHBoxLayout(bar)
        lay.setContentsMargins(10, 0, 10, 0)

        title = QLabel("Settings")
        title.setStyleSheet("color: white; font-weight: bold; background: transparent;")
        title.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        btn_min = QPushButton("—")
        btn_close = QPushButton("✕")
        for b in (btn_min, btn_close):
            b.setFixedSize(26, 22)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet("""
                QPushButton {
                    border: none;
                    background: transparent;
                    color: white;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background: rgba(255,255,255,0.25);
                }
            """)

        btn_min.clicked.connect(self.showMinimized)
        btn_close.clicked.connect(self.close)

        lay.addWidget(title)
        lay.addStretch(1)
        lay.addWidget(btn_min)
        lay.addWidget(btn_close)
        return bar

    # Load current setting values into UI controls
    def _load_values(self):
        # Audio ---------------------------------------------------------------
        alert_text = self.user_manager.get_setting('alert_text') or "Stay focused!"
        self.edit_alert_text.setText(str(alert_text))
        self._last_alert_text = str(alert_text)

        alert_voice = self.user_manager.get_setting('alert_voice') or "en-US-JennyNeural"
        idx = self.combo_voice.findText(alert_voice)
        if idx >= 0:
            self.combo_voice.setCurrentIndex(idx)
        self._last_alert_voice = alert_voice

        alert_volume = self.user_manager.get_setting('alert_volume')
        if alert_volume is None:
            alert_volume = 100
        self.slider_volume.setValue(int(alert_volume))
        self.lbl_vol_val.setText(f"{int(alert_volume)}%")

        device_name = self.user_manager.get_setting('output_device')
        if device_name is not None:
            idx = self.combo_output.findText(device_name)
            if idx >= 0:
                self.combo_output.setCurrentIndex(idx)

        # Video
        def load_video_val(key, slider, default=50):
            v = self.user_manager.get_setting(key)
            if v is None:
                v = default
            try:
                slider.setValue(int(float(v)))
            except Exception:
                slider.setValue(default)
        load_video_val('cam_brightness', self.slider_brightness)
        load_video_val('cam_contrast',   self.slider_contrast)
        load_video_val('cam_exposure',   self.slider_exposure)
        load_video_val('cam_saturation', self.slider_saturation)
        cam_index = self.user_manager.get_setting('webcam_index')
        if cam_index is not None and int(cam_index) < self.combo_webcam.count():
            self.combo_webcam.setCurrentIndex(int(cam_index))

        # Monitor
        if self.monitor is not None:
            # pull from running monitor
            self.spin_thresh.setValue(float(self.monitor.threshold))
            self.spin_cooldown.setValue(int(self.monitor.cooldown_seconds))
            # derive fps: max_samples / window_seconds
            fps_eff = max(1, self.monitor.max_samples // max(1, self.monitor.window_seconds))
            self.spin_fps.setValue(int(fps_eff))
            self.spin_window.setValue(int(self.monitor.window_seconds))
        else:
            # fall back to persisted values
            thresh = self.user_manager.get_setting('alert_threshold') or 0.6
            try:
                self.spin_thresh.setValue(float(thresh))
            except Exception:
                self.spin_thresh.setValue(0.6)

            cooldown = self.user_manager.get_setting('cooldown_seconds') or 15
            self.spin_cooldown.setValue(int(cooldown))

            fps = self.user_manager.get_setting('fps') or 4
            self.spin_fps.setValue(int(fps))

            window_s = self.user_manager.get_setting('window_seconds') or 5
            self.spin_window.setValue(int(window_s))

    def _save_and_close(self):
        # Audio ---------------------------------------------------------------
        self.user_manager.update_setting('alert_text', self.edit_alert_text.text().strip())
        self.user_manager.update_setting('alert_voice', self.combo_voice.currentText())
        self.user_manager.update_setting('alert_volume', int(self.slider_volume.value()))
        self.user_manager.update_setting('output_device', self.combo_output.currentText())

        # Video ---------------------------------------------------------------
        self.user_manager.update_setting('cam_brightness', int(self.slider_brightness.value()))
        self.user_manager.update_setting('cam_contrast',   int(self.slider_contrast.value()))
        self.user_manager.update_setting('cam_exposure',   int(self.slider_exposure.value()))
        self.user_manager.update_setting('cam_saturation', int(self.slider_saturation.value()))
        self.user_manager.update_setting('webcam_index', self.combo_webcam.currentIndex())

        # Monitor -------------------------------------------------------------
        self.user_manager.update_setting('alert_threshold', float(self.spin_thresh.value()))
        self.user_manager.update_setting('cooldown_seconds', int(self.spin_cooldown.value()))
        self.user_manager.update_setting('fps', int(self.spin_fps.value()))
        self.user_manager.update_setting('window_seconds', int(self.spin_window.value()))

        # Apply to live monitor (if provided)
        if self.monitor is not None:
            self.monitor.reconfigure(
                threshold=float(self.spin_thresh.value()),
                cooldown_seconds=int(self.spin_cooldown.value()),
                fps=int(self.spin_fps.value()),
                window_seconds=int(self.spin_window.value()),
            )

        # Callback to parent so it can apply runtime changes
        if self.save_callback:
            self.save_callback()

        self.close()

    def _preview_audio(self):
        text = self.edit_alert_text.text().strip() or "Stay focused!"
        voice = self.combo_voice.currentText()
        vol_pct = self.slider_volume.value()  # 0-100

        def worker():
            nonlocal text, voice, vol_pct

            regenerate = (
                    self._cached_preview_audio is None
                    or voice != self._cached_preview_voice
                    or text != self._cached_preview_text
            )

            if regenerate:
                async def _gen_async():
                    # Edge TTS -> temp mp3
                    fd_mp3, mp3_path = tempfile.mkstemp(suffix=".mp3")
                    os.close(fd_mp3)
                    tts = edge_tts.Communicate(text=text, voice=voice)
                    await tts.save(mp3_path)

                    # Load to AudioSegment (pydub), cleanup mp3
                    seg = AudioSegment.from_file(mp3_path, format="mp3")
                    os.remove(mp3_path)
                    return seg

                try:
                    seg_new = asyncio.run(_gen_async())
                except Exception as e:
                    print(f"[Settings] TTS generation failed: {e}")
                    return

                # cache
                self._cached_preview_audio = seg_new
                self._cached_preview_voice = voice
                self._cached_preview_text = text
            else:
                seg_new = self._cached_preview_audio

            # Apply requested volume (non-destructive copy)
            v = vol_pct / 100.0
            if v <= 0.0:
                gain_db = -60.0
            elif v >= 1.0:
                gain_db = 0.0
            else:
                gain_db = -60.0 * (1.0 - (v ** 0.5))
            seg_out = seg_new.apply_gain(gain_db)

            # Export to temp wav & play via existing helper
            fd_wav, wav_path = tempfile.mkstemp(suffix=".wav")
            os.close(fd_wav)
            seg_out.export(wav_path, format="wav")

            try:
                play_alert_audio(filename=wav_path)  # pygame playback. :contentReference[oaicite:0]{index=0}
            except Exception as e:
                print(f"[Settings] Playback error: {e}")

        # run worker in thread so UI doesn't freeze
        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------------
    # Drag support (click anywhere; could refine to title bar hit-test)
    # ------------------------------------------------------------------
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and hasattr(self, "_drag_pos"):
            self.move(self.pos() + event.globalPosition().toPoint() - self._drag_pos)
            self._drag_pos = event.globalPosition().toPoint()
            event.accept()
        else:
            super().mouseMoveEvent(event)
