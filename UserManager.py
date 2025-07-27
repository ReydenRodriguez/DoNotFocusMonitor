import json
import os

class UserManager:
    def __init__(self, user_file='users.json'):
        self.user_file = user_file
        self.users = self.load_users()
        self.current_user = None

    def load_users(self):
        if os.path.exists(self.user_file):
            with open(self.user_file, 'r') as f:
                return json.load(f).get('users', {})
        return {}

    def save_users(self):
        with open(self.user_file, 'w') as f:
            json.dump({'users': self.users}, f, indent=4)

    def signup(self, username):
        if username in self.users:
            return False
        self.users[username] = {
            'calibration_data': {},
            'settings': {'alert_threshold': 0.6}
        }
        self.current_user = username
        self.save_users()
        return True

    def login(self, username):
        if username in self.users:
            self.current_user = username
            return True
        return False

    def get_current_user_data(self):
        return self.users.get(self.current_user, {}) if self.current_user else {}

    def update_calibration_data(self, calibration_data):
        if self.current_user:
            self.users[self.current_user]['calibration_data'] = calibration_data
            self.save_users()

    def get_calibration_data(self):
        return self.users.get(self.current_user, {}).get('calibration_data', {}) if self.current_user else {}

    def update_setting(self, key, value):
        if self.current_user:
            self.users[self.current_user]['settings'][key] = value
            self.save_users()

    def get_setting(self, key):
        return self.users.get(self.current_user, {}).get('settings', {}).get(key) if self.current_user else None

    def add_intentional_action(self, action_text):
        if self.current_user:
            self.users[self.current_user].setdefault("intentional_actions", []).append(action_text)
            self.save_users()

    def get_intentional_actions(self):
        if self.current_user:
            return self.users[self.current_user].get("intentional_actions", [])
        return []

