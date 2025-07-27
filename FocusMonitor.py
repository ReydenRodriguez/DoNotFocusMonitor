import time
import threading
from collections import deque
import asyncio
import os
import edge_tts
from pydub import AudioSegment
import tempfile
import shutil
import cv2
import numpy as np
try:
    from deepface import DeepFace  # heavy
except ImportError:
    DeepFace = None

class FocusMonitor:
    def __init__(
        self,
        user_manager=None,
        window_seconds=5,
        fps=4,
        threshold=0.6,
        cooldown_seconds=15,
        ia_stride=10,
        analysis_stride=2,
        verbose=False,
    ):
        self.user_manager = user_manager
        self.is_monitoring = False
        self.window_seconds = window_seconds
        self.fps = fps
        self.max_samples = window_seconds * fps
        self.threshold = threshold
        self.focus_history = deque(maxlen=self.max_samples)
        self.last_alert_time = 0
        self.cooldown_seconds = cooldown_seconds

        # defer expensive IA load until needed
        self.ia_model = None
        self._ia_loaded = False

        self.ia_stride = max(1, int(ia_stride))
        self.analysis_stride = max(1, int(analysis_stride))
        self._last_processed_frame = None
        self._last_focus_state = None

        self.verbose = verbose


    def _ensure_ia_model(self):
        # Lazy load the CLIP model
        if self._ia_loaded:
            return
        try:
            from IAModel import IntentionalActionRecognizer
            self.ia_model = IntentionalActionRecognizer()
            self._ia_loaded = True
        except Exception as e:
            print(f"[FocusMonitor] IA model unavailable: {e}")
            self.ia_model = None
            self._ia_loaded = True  # don't retry endlessly

    def set_intent_actions(self, actions):
        if actions:
            self._ensure_ia_model()
            if self.ia_model:
                self.ia_model.set_defined_actions(actions)
        else:
            self.ia_model = None
            self._ia_loaded = False

    def start_monitoring(self, cap, analyzer, frame_callback=None, intent_actions=None):
        # clone analyzer args
        analyzer_ctor = None
        if analyzer is not None:
            from FaceAnalysis import FaceAnalyzer
            analyzer_args = dict(use_dlib=analyzer.use_dlib)  # add other relevant fields
            calib = getattr(analyzer, "calibration_data", None)
            baseline_v = getattr(analyzer, "baseline_vertical_ratio", None)
            baseline_h = getattr(analyzer, "baseline_horizontal_ratio", None)

        if self.is_monitoring:
            print("Monitoring already running.")
            return

        # configure intentional actions if provided
        if intent_actions:
            self.set_intent_actions(intent_actions)

        self.is_monitoring = True

        def run():
            local_analyzer = None
            if analyzer is not None:
                from FaceAnalysis import FaceAnalyzer
                local_analyzer = FaceAnalyzer(**analyzer_args)
                if calib:
                    local_analyzer.calibration_data = calib
                local_analyzer.baseline_vertical_ratio = baseline_v
                local_analyzer.baseline_horizontal_ratio = baseline_h

            frame_count = 0
            log_every = 60 if not self.verbose else 15
            target_dt = 1.0 / max(self.fps, 1)
            next_ts = time.perf_counter()

            distraction_streak = 0
            awaiting_ia = False
            streak_threshold = 5  # or whatever you want

            while self.is_monitoring:
                # FPS throttle
                now = time.perf_counter()
                if now < next_ts:
                    time.sleep(next_ts - now)
                next_ts += target_dt

                ret, frame = cap.read()
                if not ret:
                    break
                frame = cv2.flip(frame, 1)
                user_brightness = get_user_setting_safe(self.user_manager, 'cam_brightness')
                user_contrast = get_user_setting_safe(self.user_manager, 'cam_contrast')
                user_exposure = get_user_setting_safe(self.user_manager, 'cam_exposure')
                user_saturation = get_user_setting_safe(self.user_manager, 'cam_saturation')

                try:
                    frame = adjust_brightness_contrast(
                        frame,
                        brightness=float(user_brightness),
                        contrast=float(user_contrast)
                    )
                    frame = adjust_exposure(frame, exposure=float(user_exposure))
                    frame = adjust_saturation(frame, saturation=float(user_saturation))
                except Exception as e:
                    print(f"Frame adjustment error: {e}")
                    print(f"  brightness={user_brightness}, contrast={user_contrast}, exposure={user_exposure}, saturation={user_saturation}")

                frame_count += 1

                if local_analyzer is not None and (frame_count % self.analysis_stride == 0):
                    try:
                        processed_frame, emotions, eye_contacts, focus_states = local_analyzer.process_frame(frame)
                    except Exception as e:
                        print(f"[FocusMonitor] analyzer error: {e}")
                        processed_frame, focus_states = frame, []
                        emotions, eye_contacts = [], []
                    self._last_processed_frame = processed_frame
                    focus_state = focus_states[0] if focus_states else "Unknown"

                    if focus_state == "Distracted":
                        distraction_streak += 1

                        # Only trigger IA if streak threshold met and IA enabled
                        if (
                                distraction_streak >= streak_threshold
                                and self.ia_model
                                and getattr(self.ia_model, "defined_actions", None)
                                and len(self.ia_model.defined_actions) > 0
                                and not awaiting_ia
                        ):
                            print(f"[DEBUG] Triggering IA after {distraction_streak} distracted frames.")
                            self.ia_model.trigger_async_detection(frame)
                            awaiting_ia = True

                        # Poll for IA result if triggered detection
                        if awaiting_ia:
                            detected, label, conf = self.ia_model.get_last_result()
                            print(f"[DEBUG] IA result: detected={detected}, label={label}, conf={conf}")
                            if detected:
                                focus_state = "Focused"
                                print(f"[Suppressed] Intentional action detected: {label}")
                                distraction_streak = 0
                                awaiting_ia = False
                    else:
                        distraction_streak = 0
                        awaiting_ia = False

                    self._last_focus_state = focus_state
                    self.update(focus_state, samples=self.analysis_stride)

                    if self.verbose and frame_count % log_every == 0:
                        print("Focus:", focus_states)
                        print("Eye Contact:", eye_contacts)
                else:
                    processed_frame = self._last_processed_frame if self._last_processed_frame is not None else frame

                if frame_callback:
                    frame_callback(processed_frame)

            cap.release()
            print("Monitoring loop ended.")

        self.monitoring_thread = threading.Thread(target=run, daemon=True)
        self.monitoring_thread.start()

    def update(self, focus_state, samples=1):
        # Record focus_state samples times to maintain timing with stride
        ts = time.time()
        for _ in range(samples):
            self.focus_history.append((ts, focus_state))
        self.check_focus()



    def check_focus(self):
        if len(self.focus_history) < self.max_samples:
            return  # this means theres not enough data yet

        distracted_count = sum(1 for _, state in self.focus_history if state == "Distracted")
        distraction_ratio = distracted_count / len(self.focus_history)

        now = time.time()
        # Trigger according to threshold
        if distraction_ratio >= self.threshold and now - self.last_alert_time > self.cooldown_seconds:
            self.trigger_alert(distraction_ratio)
            self.last_alert_time = now

    def trigger_alert(self, ratio):
        print(f"Distracted for {int(ratio * 100)}% of the last {self.window_seconds} seconds!")
        username = self.user_manager.current_user if self.user_manager else "default"
        filename = get_alert_audio_filename(username)
        play_alert_audio(filename=filename)

    def stop_monitoring(self):
        # stop the monitoring process and release any used resources
        self.is_monitoring = False
        if self.monitoring_thread and self.monitoring_thread.is_alive():
            self.monitoring_thread.join(timeout=1)
        print("Monitoring stopped.")

    def reconfigure(self, *, threshold=None, cooldown_seconds=None, fps=None, window_seconds=None):
        """
        Update runtime parameters without recreating the FocusMonitor.
        Any arg left as None keeps the current value.
        Resizes focus_history if fps or window_seconds imply a new sample length.
        """
        changed = False

        if threshold is not None:
            self.threshold = float(threshold)
            changed = True

        if cooldown_seconds is not None:
            self.cooldown_seconds = int(cooldown_seconds)
            changed = True

        # Update fps / window_seconds & max_samples coherently
        new_window = int(window_seconds) if window_seconds is not None else self.window_seconds
        # Infer current fps from max_samples/window.
        current_fps = self.max_samples // self.window_seconds if self.window_seconds else 1
        new_fps = int(fps) if fps is not None else current_fps


        if new_window != self.window_seconds or new_fps != current_fps:
            self.window_seconds = new_window
            self.fps = new_fps
            self.max_samples = self.window_seconds * new_fps
            # rebuild deque w/ latest samples (truncate/pad as needed)
            from collections import deque
            self.focus_history = deque(list(self.focus_history)[-self.max_samples:], maxlen=self.max_samples)
            changed = True

        # Scale heavy model strides when fps high
        if new_fps >= 8:
            self.ia_stride = 10
            self.analysis_stride = 2
        elif new_fps >= 5:
            self.ia_stride = 5
            self.analysis_stride = 2
        else:
            self.ia_stride = 3
            self.analysis_stride = 1


        if changed:
            print(f"[FocusMonitor] Reconfigured: threshold={self.threshold} "
                  f"cooldown={self.cooldown_seconds}s window={self.window_seconds}s "
                  f"max_samples={self.max_samples}")


    def update_params(self, *, window_seconds=None, fps=None, threshold=None, cooldown_seconds=None):
        # Update runtime parameters after user changes settings
        if threshold is not None:
            self.threshold = float(threshold)
        if cooldown_seconds is not None:
            self.cooldown_seconds = int(cooldown_seconds)
        # window/fps affect history length
        changed_hist = False
        if window_seconds is not None:
            self.window_seconds = int(window_seconds)
            changed_hist = True
        if fps is not None:
            self.fps = int(fps)
            changed_hist = True
        if changed_hist:
            self.max_samples = self.window_seconds * self.fps
            # shrink/grow history while preserving most recent entries
            old = list(self.focus_history)[-self.max_samples:]
            self.focus_history = deque(old, maxlen=self.max_samples)

def play_alert_audio(filename=None):
    if not filename or not os.path.exists(filename):
        filename = "alert.wav"
    def _play():
        try:
            import pygame
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            pygame.mixer.music.load(filename)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                pygame.time.Clock().tick(10)
        except Exception as e:
            print(f"[Pygame Playback Error] {e}")
    threading.Thread(target=_play, daemon=True).start()


def get_alert_audio_filename(username, folder="alerts"):
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, f"alert_{username}.wav")


def generate_alert_audio(
        text="Stay focused!",
        voice="en-US-JennyNeural",
        volume_pct=100,
        filename="alert.wav",
):
    async def speak():
        mp3_filename = filename + ".mp3"
        temp_wav_fd, temp_wav_filename = tempfile.mkstemp(suffix=".wav")
        os.close(temp_wav_fd)
        tts = edge_tts.Communicate(text=text, voice=voice)
        await tts.save(mp3_filename)
        audio = AudioSegment.from_file(mp3_filename, format="mp3")
        os.remove(mp3_filename)

        v = max(0, min(int(volume_pct), 100)) / 100.0
        if v <= 0.0:
            gain_db = -60.0
        elif v >= 1.0:
            gain_db = 0.0
        else:
            gain_db = -60.0 * (1.0 - (v ** 0.5))
        audio = audio.apply_gain(gain_db)

        audio.export(temp_wav_filename, format="wav")
        try:
            # Atomically overwrite original alert.wav (avoid "in use" errors)
            shutil.move(temp_wav_filename, filename)
        except Exception as e:
            print(f"[TTS] Could not move temp audio into place: {e}")
            # As a fallback, keep the temp file for debugging
        print(f"[TTS Ready] Saved: {filename}")

    asyncio.run(speak())


def adjust_brightness_contrast(frame, brightness=50, contrast=50):
    # brightness: 0–100 (50 = unchanged)
    # contrast: 0–100 (50 = unchanged)
    alpha = max(0.0, contrast / 50.0)  # Contrast control (1.0 = unchanged)
    beta = (brightness - 50) * 2.55  # Brightness control (-127 to +127)
    return cv2.convertScaleAbs(frame, alpha=alpha, beta=beta)

def adjust_exposure(frame, exposure=50):
    # exposure: 0–100 (50 = unchanged)
    factor = max(0.0, exposure / 50.0)
    return cv2.convertScaleAbs(frame, alpha=factor, beta=0)


def adjust_saturation(frame, saturation=50):
    # saturation: 0–100 (50 = unchanged)
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV).astype(np.float32)
    s = hsv[:, :, 1]
    scale = saturation / 50.0  # 1.0 = unchanged
    s = np.clip(s * scale, 0, 255)
    hsv[:, :, 1] = s
    frame_sat = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)
    return frame_sat

def get_user_setting_safe(user_manager, key, default=50):
    try:
        v = user_manager.get_setting(key)
        if v is None:
            return default
        v = float(v)
        if not np.isfinite(v):
            return default
        return v
    except Exception:
        return default
