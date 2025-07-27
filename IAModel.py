import torch
from transformers import CLIPProcessor, CLIPModel
from PIL import Image
import cv2
import numpy as np
import threading

class IntentionalActionRecognizer:
    def __init__(self, model_name="openai/clip-vit-base-patch32"):
        print("[IA] Loading CLIP model...")
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = CLIPModel.from_pretrained(model_name).to(self.device)
        if self.device.type == "cuda":
            self.model = self.model.half()
        self.processor = CLIPProcessor.from_pretrained(model_name)
        self.defined_actions = []  # List of text descriptions
        print("[IA] Model loaded and ready.")

        self._last_result = (False, None, 0.0)
        self._lock = threading.Lock()
        self._inference_thread = None

    def set_defined_actions(self, actions):
        self.defined_actions = actions
        print(f"[IA] Set defined actions: {actions}")

    def frame_to_image(self, frame):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        resized = cv2.resize(rgb, (224, 224), interpolation=cv2.INTER_LINEAR)
        return Image.fromarray(resized)

    def _inference_worker(self, frame, threshold, neutral_action):
        result = self.is_action_detected_blocking(frame, threshold, neutral_action)
        with self._lock:
            self._last_result = result

    def trigger_async_detection(self, frame, threshold=0.4, neutral_action="sitting and working"):
        # Start a new thread if one is not already running
        if self._inference_thread is None or not self._inference_thread.is_alive():
            self._inference_thread = threading.Thread(
                target=self._inference_worker,
                args=(frame, threshold, neutral_action),
                daemon=True
            )
            self._inference_thread.start()
    def get_last_result(self):
        # Returns the last completed detection
        with self._lock:
            return self._last_result

    def is_action_detected_blocking(self, frame, threshold=0.4, neutral_action="sitting and working"):
        if not self.defined_actions:
            return False, None, 0.0

        action_texts = self.defined_actions + [neutral_action]

        image = self.frame_to_image(frame)
        inputs = self.processor(text=action_texts, images=image, return_tensors="pt", padding=True)
        inputs = {k: v.to(self.device) for k, v in inputs.items()}
        if self.device.type == "cuda":
            for k, v in inputs.items():
                if torch.is_floating_point(v):
                    inputs[k] = v.half()

        with torch.no_grad():
            outputs = self.model(**inputs)
            logits_per_image = outputs.logits_per_image
            probs = logits_per_image.softmax(dim=1).cpu().numpy().flatten()

        max_index = int(np.argmax(probs))
        confidence = float(probs[max_index])
        label = action_texts[max_index]

        if label == neutral_action:
            return False, label, confidence
        if confidence >= threshold:
            return True, label, confidence
        return False, label, confidence