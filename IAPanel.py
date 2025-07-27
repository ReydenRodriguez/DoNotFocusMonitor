from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget,
    QListWidgetItem, QLineEdit, QFrame, QStackedLayout, QGraphicsBlurEffect,
    QSizePolicy, QSpacerItem
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont


class IntentionalActionsPanel(QWidget):
    # small floating panel used to add / remove Intentional Actions.

    def __init__(self, user_manager, current_user, save_callback=None):
        super().__init__()
        self.user_manager = user_manager
        self.current_user = current_user
        self.save_callback = save_callback

        # Acrylic / frameless styling to match MainWindow
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setWindowTitle("Edit Intentional Actions")
        self.resize(420, 480)  # starting size; resizable

        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        title_bar = self._create_title_bar()
        outer.addWidget(title_bar)

        bg = QFrame()
        bg.setStyleSheet("""
            QFrame {
                background-color: rgba(255, 255, 255, 0.15);
                border-radius: 0px; /* full-bleed; outer already shapes window */
            }
        """)
        blur = QGraphicsBlurEffect()
        blur.setBlurRadius(25)
        bg.setGraphicsEffect(blur)
        bg.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: rgba(255, 255, 255, 0.85);
                border-bottom-left-radius: 16px;
                border-bottom-right-radius: 16px;
            }
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 20, 20, 20)
        card_layout.setSpacing(12)

        # Header label
        self.label = QLabel("Intentional Actions")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        self.label.setStyleSheet("color: #4A148C; background: transparent;")
        card_layout.addWidget(self.label)

        # Input row
        self.action_input = QLineEdit()
        self.action_input.setPlaceholderText("Type a new intentional action…")
        self.action_input.setStyleSheet("""
            QLineEdit {
                background-color: rgba(255, 255, 255, 0.8);
                border: 2px solid #FFB6C1;
                padding: 8px 10px;
                font-size: 14px;
                border-radius: 8px;
                color: black;
            }
            QLineEdit:focus {
                border-color: #FF9AA2;
            }
        """)
        card_layout.addWidget(self.action_input)

        self.add_button = QPushButton("Add Action")
        self.add_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.add_button.setFixedHeight(32)
        self.add_button.setStyleSheet("""
            QPushButton {
                background-color: #8BC34A;
                color: white;
                padding: 4px 16px;
                font-size: 14px;
                border-radius: 8px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #7CB342;
            }
        """)
        self.add_button.clicked.connect(self.add_action)
        card_layout.addWidget(self.add_button)

        # Actions list
        self.actions_list = QListWidget()
        self.actions_list.setStyleSheet("""
            QListWidget {
                background-color: rgba(255, 255, 255, 0.9);
                border: 1px solid #FFB6C1;
                border-radius: 8px;
            }
        """)
        card_layout.addWidget(self.actions_list, 1)

        # Bottom buttons row
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(8)

        bottom_row.addStretch(1)
        self.reload_button = QPushButton("Reload Actions")
        self.reload_button.setFixedHeight(32)
        self.reload_button.setStyleSheet("""
            QPushButton {
                background-color: #FFB6C1;
                color: white;
                padding: 4px 16px;
                font-size: 14px;
                border-radius: 8px;
            }
            QPushButton:hover {
                background-color: #FF9AA2;
            }
        """)
        self.reload_button.clicked.connect(self.on_reload_clicked)
        bottom_row.addWidget(self.reload_button)
        card_layout.addLayout(bottom_row)

        # Populate list after widgets exist
        self.refresh_actions()

        stack = QStackedLayout()
        stack.setStackingMode(QStackedLayout.StackingMode.StackAll)
        stack.addWidget(bg)
        stack.addWidget(card)

        container = QWidget()
        container.setLayout(stack)
        outer.addWidget(container)

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

        title = QLabel("Edit Intentional Actions")
        title.setStyleSheet("color: white; font-weight: bold; background: transparent;")
        title.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        btn_min = QPushButton("—")
        btn_close = QPushButton("✕")
        for b in (btn_min, btn_close):
            b.setFixedSize(26, 22)
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

    create_title_bar = _create_title_bar

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

    # Data operations (unchanged logic)
    def refresh_actions(self):
        self.actions_list.clear()
        actions = self.user_manager.get_intentional_actions()
        for action in actions:
            item = QListWidgetItem(action)

            # row widget w/ remove button
            row_w = QWidget()
            hbox = QHBoxLayout(row_w)
            hbox.setContentsMargins(8, 0, 8, 0)
            hbox.setSpacing(4)

            lbl = QLabel(action)
            lbl.setStyleSheet("color: #333; background: transparent;")
            rem = QPushButton("×")
            rem.setFixedSize(16, 16)
            rem.setCursor(Qt.CursorShape.PointingHandCursor)
            rem.setStyleSheet("""
                QPushButton {
                    color: #ff1744;                /* vivid red/pink */
                    font-weight: bold;
                    border: none;
                    background: transparent;
                    padding: 0;
                }
                QPushButton:hover {
                    background: rgba(255, 23, 68, 0.25);  /* soft red glow */
                    color: white;
                    border-radius: 6px;                  /* make hover background circular */
                }
                QPushButton:pressed {
                    background: rgba(255, 23, 68, 0.40);
                }
            """)
            rem.clicked.connect(lambda _, a=action: self.remove_action(a))

            hbox.addWidget(lbl)
            hbox.addStretch(1)
            hbox.addWidget(rem)

            item.setSizeHint(row_w.sizeHint())
            self.actions_list.addItem(item)
            self.actions_list.setItemWidget(item, row_w)

    def on_reload_clicked(self):
        if self.save_callback:
            print("[Panel] Reloading intentional actions...")
            self.save_callback()
        # always refresh locally in case changed
        self.refresh_actions()

    def add_action(self):
        new_action = self.action_input.text().strip()
        if new_action:
            self.user_manager.add_intentional_action(new_action)
            self.action_input.clear()
            self.refresh_actions()
            if self.save_callback:
                self.save_callback()

    def remove_action(self, action_text):
        current_actions = self.user_manager.get_intentional_actions()
        if action_text in current_actions:
            current_actions.remove(action_text)
            self.user_manager.users[self.current_user]["intentional_actions"] = current_actions
            self.user_manager.save_users()
            self.refresh_actions()
            if self.save_callback:
                self.save_callback()
