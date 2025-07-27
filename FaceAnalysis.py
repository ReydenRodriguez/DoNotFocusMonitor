import cv2
import dlib
import mediapipe as mp
from deepface import DeepFace
import time
import statistics


class FaceAnalyzer:
    def __init__(self, use_dlib=False):
        # dlib detector is slow, default off
        self.use_dlib = use_dlib
        self.detector = dlib.get_frontal_face_detector() if use_dlib else None

        self.mp_face_mesh = mp.solutions.face_mesh.FaceMesh(
            static_image_mode=False,
            refine_landmarks=True,
            max_num_faces=1
        )

        self.LEFT_PUPIL = 468
        self.RIGHT_PUPIL = 473
        self.LEFT_EYE = [33, 133]
        self.RIGHT_EYE = [362, 263]
        self.LEFT_EYE_TOP = 159
        self.LEFT_EYE_BOTTOM = 145
        self.RIGHT_EYE_TOP = 386
        self.RIGHT_EYE_BOTTOM = 374

        self.baseline_vertical_ratio = None
        self.baseline_horizontal_ratio = None

    def extract_gaze_ratios(self, landmarks):
        try:
            left_eye_inner = landmarks[self.LEFT_EYE[0]].x
            left_eye_outer = landmarks[self.LEFT_EYE[1]].x
            right_eye_inner = landmarks[self.RIGHT_EYE[0]].x
            right_eye_outer = landmarks[self.RIGHT_EYE[1]].x

            left_pupil_x = landmarks[self.LEFT_PUPIL].x
            right_pupil_x = landmarks[self.RIGHT_PUPIL].x

            left_horizontal_ratio = (left_pupil_x - left_eye_inner) / (left_eye_outer - left_eye_inner)
            right_horizontal_ratio = (right_pupil_x - right_eye_inner) / (right_eye_outer - right_eye_inner)
            avg_horizontal = (left_horizontal_ratio + right_horizontal_ratio) / 2

            left_eye_top = landmarks[self.LEFT_EYE_TOP].y
            left_eye_bottom = landmarks[self.LEFT_EYE_BOTTOM].y
            right_eye_top = landmarks[self.RIGHT_EYE_TOP].y
            right_eye_bottom = landmarks[self.RIGHT_EYE_BOTTOM].y

            left_pupil_y = landmarks[self.LEFT_PUPIL].y
            right_pupil_y = landmarks[self.RIGHT_PUPIL].y

            left_vertical_ratio = (left_pupil_y - left_eye_top) / (left_eye_bottom - left_eye_top)
            right_vertical_ratio = (right_pupil_y - right_eye_top) / (right_eye_bottom - right_eye_top)
            avg_vertical = (left_vertical_ratio + right_vertical_ratio) / 2

            return avg_vertical, avg_horizontal
        except Exception as e:
            print(f"[extract_gaze_ratios] Error: {e}")
            return None, None

    def calibrate_gaze(self, cap, duration_seconds=2):
        ret, frame = cap.read()
        if not ret:
            print("Failed to read from camera.")
            return

        frame = cv2.flip(frame, 1)
        screen_width = frame.shape[1]
        screen_height = frame.shape[0]

        points = [
            ("top_left", (int(screen_width * 0.05), int(screen_height * 0.05))),
            ("top_right", (int(screen_width * 0.95), int(screen_height * 0.05))),
            ("bottom_left", (int(screen_width * 0.05), int(screen_height * 0.95))),
            ("bottom_right", (int(screen_width * 0.95), int(screen_height * 0.95))),
            ("center", (int(screen_width * 0.5), int(screen_height * 0.5)))
        ]

        self.calibration_data = {}


        # Initialize fullscreen window
        cv2.namedWindow("Calibration", cv2.WND_PROP_FULLSCREEN)
        cv2.setWindowProperty("Calibration", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)



        for label, screen_pos in points:
            if cv2.getWindowProperty("Calibration", cv2.WND_PROP_VISIBLE) < 1:
                print("[Calibration] Cancelled by user (window closed before point).")
                cv2.destroyAllWindows()
                return None
            print(f"Look at the {label.replace('_', ' ')} corner. Press SPACE when ready.")


            while True:
                if cv2.getWindowProperty("Calibration", cv2.WND_PROP_VISIBLE) < 1:
                    print("[Calibration] Cancelled by user (window closed during point selection).")
                    cv2.destroyAllWindows()
                    return None
                ret, frame = cap.read()
                frame = cv2.flip(frame, 1)
                cv2.circle(frame, screen_pos, 5, (0, 255, 0), -1)

                # Arrow tip (the dot position)
                tip_x, tip_y = screen_pos
                if label != "center":
                    tip_x = tip_x - 15 if "right" in label else tip_x + 15
                    tip_y = tip_y - 15 if "bottom" in label else tip_y + 15
                else:
                    tip_y = tip_y - 15


                # Arrow base: position the arrow pointing inward toward the dot
                if "top_left" in label:
                    base_x, base_y = tip_x + 50, tip_y + 50
                elif "top_right" in label:
                    base_x, base_y = tip_x - 50, tip_y + 50
                elif "bottom_left" in label:
                    base_x, base_y = tip_x + 50, tip_y - 50
                elif "bottom_right" in label:
                    base_x, base_y = tip_x - 50, tip_y - 50
                else:  # center
                    base_x, base_y = tip_x, tip_y - 50

                # Draw arrowed line
                cv2.arrowedLine(frame, (base_x, base_y), (tip_x, tip_y), (130, 130, 255), 2, tipLength=0.2)

                if label != "center":
                    text_offset_x = -150 if "right" in label else 70
                    text_offset_y = -70 if "bottom" in label else 70
                else:
                    text_offset_x = 0
                    text_offset_y = -65
                text_pos = (screen_pos[0] + text_offset_x, screen_pos[1] + text_offset_y)

                # Show full instructions only for the first dot
                if label == "top_left":
                    intro_lines = [
                        "Calibration beginning...",
                        "Press SPACE for each calibration",
                        "dot and stare at the dot for",
                        "as long as it appears."
                    ]
                    for i, line in enumerate(intro_lines):
                        text_size = cv2.getTextSize(line, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)[0]
                        x = (frame.shape[1] - text_size[0]) // 2
                        y = int(frame.shape[0] * 0.35) + (i * 30)
                        cv2.putText(frame, line, (x, y),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

                cv2.imshow("Calibration", frame)
                if cv2.waitKey(1) & 0xFF == ord(' '):
                    break

                # Wait for user to press SPACE
                cv2.putText(frame, "Look here", (text_pos),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 100, 255), 1)
                cv2.imshow("Calibration", frame)
                if cv2.waitKey(1) & 0xFF == ord(' '):
                    break



            vertical_samples = []
            horizontal_samples = []

            start_time = time.time()

            while time.time() - start_time < duration_seconds:
                if cv2.getWindowProperty("Calibration", cv2.WND_PROP_VISIBLE) < 1:
                    print("[Calibration] Cancelled by user (window closed during sample collection).")
                    cv2.destroyAllWindows()
                    return None
                ret, frame = cap.read()
                if not ret:
                    continue
                frame = cv2.flip(frame, 1)
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                results = self.mp_face_mesh.process(rgb_frame)

                if results.multi_face_landmarks:
                    landmarks = results.multi_face_landmarks[0].landmark
                    vertical_ratio, horizontal_ratio = self.extract_gaze_ratios(landmarks)
                    if vertical_ratio is not None and horizontal_ratio is not None:
                        vertical_samples.append(vertical_ratio)
                        horizontal_samples.append(horizontal_ratio)

                cv2.circle(frame, screen_pos, 5, (0, 255, 0), -1)
                text_offset_x = -170 if "right" in label else 20
                text_offset_y = -30 if "bottom" in label else 30
                cv2.putText(frame, f"Calibrating...", text_pos,
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                cv2.imshow("Calibration", frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break

            self.calibration_data[label] = {
                "v": float(statistics.median(vertical_samples)),
                "h": float(statistics.median(horizontal_samples))
            }

        cv2.destroyWindow("Calibration")
        self.baseline_vertical_ratio = self.calibration_data["center"]["v"]
        self.baseline_horizontal_ratio = self.calibration_data["center"]["h"]
        print("Calibration complete.")

        return self.baseline_vertical_ratio, self.baseline_horizontal_ratio

    def analyze_emotion(self, face_region):
        result = DeepFace.analyze(face_region, actions=['emotion'], enforce_detection=False, detector_backend="opencv")
        return result[0]['dominant_emotion'] if result else "Unknown"

    def detect_gaze(self, landmarks):
        if not landmarks:
            return "Unknown"

        # Get the average pupil ratios
        avg_vertical, avg_horizontal = self.extract_gaze_ratios(landmarks)

        if avg_vertical is None or avg_horizontal is None:
            return "Unknown"

        # In case calibration isnt run
        if self.baseline_vertical_ratio is None or self.baseline_horizontal_ratio is None:
            return "Unknown"

        # Compare to calibrated baseline
        delta_v = avg_vertical - self.baseline_vertical_ratio
        delta_h = avg_horizontal - self.baseline_horizontal_ratio

        # Gaze threshold logic
        if delta_h < -0.07:
            return "Looking Left"
        elif delta_h > 0.07:
            return "Looking Right"
        elif delta_v < -0.06:
            return "Looking Down"
        elif delta_v > 0.06:
            return "Looking Up"
        else:
            return "Eye Contact"

    def interpret_focus_state(self, emotion, gaze):
        if emotion.lower() in ["bored", "tired", "disgust"]:
            return "Distracted"
        if gaze in ["Looking Away", "Looking Left", "Looking Right", "Looking Down", "Looking Up"]:
            return "Distracted"
        return "Focused"

    def process_frame(self, frame):
        # Analyze a frame using Mediapipe/Facemesh and return (annotated_frame, emotions, eye_contacts, focus_states).

        h, w = frame.shape[:2]
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.mp_face_mesh.process(rgb_frame)

        emotions_list = []
        eye_contact_list = []
        focus_state_list = []

        if results.multi_face_landmarks:
            # Use only 1 face
            landmarks = results.multi_face_landmarks[0].landmark

            # bbox from landmarks
            x, y, bw, bh = self._bbox_from_landmarks(landmarks, w, h)
            roi = frame[y:y + bh, x:x + bw]

            # emotion (can be throttled externally via self.skip_emotion)
            if getattr(self, "skip_emotion", False):
                emotion = "Unknown"
            else:
                emotion = self.analyze_emotion(roi)

            # gaze
            eye_contact = self.detect_gaze(landmarks)

            # focus interpretation
            focus_state = self.interpret_focus_state(emotion, eye_contact)

            emotions_list.append(emotion)
            eye_contact_list.append(eye_contact)
            focus_state_list.append(focus_state)

            # overlays
            cv2.rectangle(frame, (x, y), (x + bw, y + bh), (0, 255, 0), 2)
            cv2.putText(frame, f"{emotion}", (x, y - 40), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                        (0, 255, 0), 2)
            cv2.putText(frame, f"{eye_contact}", (x, y - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                        (0, 255, 255), 2)
            cv2.putText(frame, f"{focus_state}", (x, y - 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                        (0, 0, 255), 2)

            return frame, emotions_list, eye_contact_list, focus_state_list


        # Optional slow fallback: dlib (if self.use_dlib is True and FaceMesh fails).
        if self.use_dlib:
            # fallback to legacy dlib path (rare)
            if self.detector is None:
                self.detector = dlib.get_frontal_face_detector()
            faces = self.detector(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
            if faces:
                # take the largest face
                face = max(faces, key=lambda f: f.width() * f.height())
                x, y, bw, bh = face.left(), face.top(), face.width(), face.height()
                roi = frame[y:y + bh, x:x + bw]

                if getattr(self, "skip_emotion", False):
                    emotion = "Unknown"
                else:
                    emotion = self.analyze_emotion(roi)

                eye_contact = "Unknown"  # no landmarks
                focus_state = self.interpret_focus_state(emotion, eye_contact)

                emotions_list.append(emotion)
                eye_contact_list.append(eye_contact)
                focus_state_list.append(focus_state)

                cv2.rectangle(frame, (x, y), (x + bw, y + bh), (0, 255, 0), 2)
                cv2.putText(frame, f"{emotion}", (x, y - 20), cv2.FONT_HERSHEY_SIMPLEX,
                            0.6, (0, 255, 0), 2)

                return frame, emotions_list, eye_contact_list, focus_state_list

        # if nothing detected
        focus_state_list.append("Distracted")
        return frame, ["Unknown"], ["No Face"], focus_state_list

        return frame, emotions_list, eye_contact_list, focus_state_list

    def _bbox_from_landmarks(self, landmarks, width, height, pad=0.05):
        # pixel bounding box from normalized FaceMesh landmarks
        xs = [lm.x for lm in landmarks]
        ys = [lm.y for lm in landmarks]
        x_min = max(0, int(min(xs) * width))
        x_max = min(width - 1, int(max(xs) * width))
        y_min = max(0, int(min(ys) * height))
        y_max = min(height - 1, int(max(ys) * height))

        # pad
        box_w = x_max - x_min
        box_h = y_max - y_min
        dx = int(box_w * pad)
        dy = int(box_h * pad)
        x_min = max(0, x_min - dx)
        y_min = max(0, y_min - dy)
        x_max = min(width - 1, x_max + dx)
        y_max = min(height - 1, y_max + dy)

        return x_min, y_min, x_max - x_min, y_max - y_min



def main():
        cap = cv2.VideoCapture(0)  # 0 = default webcam
        analyzer = FaceAnalyzer()
        analyzer.calibrate_gaze(cap)

        while cap.isOpened():
            ret, frame = cap.read()
            frame = cv2.flip(frame, 1)

            if not ret:
                break

            # Analyze current frame
            processed_frame, emotions, eye_contacts, focus_states = analyzer.process_frame(frame)

            # Show the result
            cv2.imshow("DoNot - Focus Analyzer", processed_frame)

            # Exit on 'q' key
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

        cap.release()
        cv2.destroyAllWindows()

if __name__ == "__main__":
        main()