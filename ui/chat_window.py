from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, 
    QPushButton, QLabel, QScrollArea, QFrame, QScrollBar
)
from PyQt6.QtCore import Qt
from qasync import asyncSlot
import time

class ChatWindow(QWidget):
    def __init__(self, chat_id, chat_name, chat_manager, is_group=False, parent=None):
        super().__init__(parent)
        self.chat_id = chat_id
        self.chat_name = chat_name
        self.chat_manager = chat_manager
        self.is_group = is_group
        
        self._setup_ui()
        self._load_history()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Header
        header = QFrame()
        header.setStyleSheet("background-color: #f0f2f5; border-bottom: 1px solid #ddd;")
        header.setFixedHeight(60)
        header_layout = QHBoxLayout(header)
        
        title_layout = QVBoxLayout()
        title_layout.setSpacing(0)
        title = QLabel(self.chat_name)
        title.setStyleSheet("font-size: 16px; font-weight: bold; padding: 5px 10px 0 10px; color: black;")
        
        self.status_label = QLabel("Offline / Unknown")
        self.status_label.setStyleSheet("font-size: 12px; color: gray; padding: 0 10px 5px 10px;")
        
        title_layout.addWidget(title)
        title_layout.addWidget(self.status_label)
        
        header_layout.addLayout(title_layout)
        header_layout.addStretch()
        layout.addWidget(header)
        
        # Messages Area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("background-color: #e5ddd5; border: none;")
        
        self.messages_container = QWidget()
        self.messages_layout = QVBoxLayout(self.messages_container)
        self.messages_layout.addStretch() # Push messages to bottom
        self.scroll_area.setWidget(self.messages_container)
        layout.addWidget(self.scroll_area)
        
        # Input Area
        input_container = QFrame()
        input_container.setStyleSheet("background-color: #f0f2f5; padding: 10px;")
        input_layout = QHBoxLayout(input_container)
        input_layout.setContentsMargins(10, 10, 10, 10)
        
        self.input_field = QTextEdit()
        self.input_field.setFixedHeight(40)
        self.input_field.setPlaceholderText("Type a message...")
        self.input_field.setStyleSheet("background-color: white; border-radius: 20px; padding: 5px; border: 1px solid #ccc;")
        self.input_field.textChanged.connect(self.on_my_typing)
        
        self.send_button = QPushButton("Send")
        self.send_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_button.setStyleSheet("""
            QPushButton {
                background-color: #00a884; color: white; border-radius: 20px; font-weight: bold; padding: 10px 20px;
                border: none; margin-left: 10px;
            }
            QPushButton:hover { background-color: #008f6f; }
        """)
        self.send_button.clicked.connect(self.send_message)
        
        input_layout.addWidget(self.input_field)
        input_layout.addWidget(self.send_button)
        layout.addWidget(input_container)

    def update_status(self, is_connected):
        if is_connected:
            self.status_label.setText("Online")
            self.status_label.setStyleSheet("font-size: 12px; color: green; padding: 0 10px 5px 10px;")
        else:
            self.status_label.setText("Offline")
            self.status_label.setStyleSheet("font-size: 12px; color: gray; padding: 0 10px 5px 10px;")

    def _load_history(self):
        # Clear existing messages before loading
        while self.messages_layout.count() > 1:
            item = self.messages_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
                
        messages = self.chat_manager.db.get_messages(self.chat_id)
        for msg in messages:
            # message_id, chat_id, sender_id, text, timestamp, status
            _, _, sender_id, text, timestamp, status = msg
            self.display_message(sender_id, text, timestamp, status)

    def display_message(self, sender_id, text, timestamp, status="pending"):
        is_mine = sender_id == self.chat_manager.current_user_id
        
        msg_widget = QWidget()
        msg_layout = QHBoxLayout(msg_widget)
        msg_layout.setContentsMargins(10, 2, 10, 2)
        
        bubble = QFrame()
        bubble_layout = QVBoxLayout(bubble)
        bubble_layout.setContentsMargins(10, 8, 10, 8)
        
        text_label = QLabel(text)
        text_label.setWordWrap(True)
        text_label.setStyleSheet("font-size: 14px; background: transparent; color: black;")
        bubble_layout.addWidget(text_label)
        
        time_str = timestamp[-8:-3] if timestamp else "Now"
        if is_mine:
            ticks = " ⏳"
            if status == "sent": ticks = " ✓"
            elif status == "delivered": ticks = " ✓✓"
            elif status == "read": ticks = " ✓✓ (Read)"
            time_str += ticks
            
        time_label = QLabel(time_str)
        time_label.setStyleSheet("font-size: 10px; color: gray; background: transparent;")
        time_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        bubble_layout.addWidget(time_label)
        
        if is_mine:
            bubble.setStyleSheet("background-color: #dcf8c6; border-radius: 10px;")
            msg_layout.addStretch()
            msg_layout.addWidget(bubble)
        else:
            bubble.setStyleSheet("background-color: white; border-radius: 10px;")
            msg_layout.addWidget(bubble)
            msg_layout.addStretch()
            
        # Insert before the stretch
        count = self.messages_layout.count()
        self.messages_layout.insertWidget(count - 1, msg_widget)
        
        # Scroll to bottom
        scrollbar = self.scroll_area.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    @asyncSlot()
    async def send_message(self):
        text = self.input_field.toPlainText().strip()
        if not text: return
        self.input_field.clear()
        import asyncio
        await self.chat_manager.send_message(self.chat_id, text)

    @asyncSlot()
    async def on_my_typing(self):
        # Debounce the typing indicator emission to avoid flooding
        now = time.time()
        if not hasattr(self, 'last_typing_sent') or now - self.last_typing_sent > 2.0:
            if self.input_field.toPlainText().strip():
                self.last_typing_sent = now
                await self.chat_manager.send_typing(self.chat_id)

    def show_typing_indicator(self):
        from PyQt6.QtCore import QTimer
        self.status_label.setText("typing...")
        self.status_label.setStyleSheet("font-size: 12px; color: #00a884; font-style: italic; padding: 0 10px 5px 10px;")
        
        # Reset back to Online after 3 seconds
        if hasattr(self, 'typing_timer'):
            self.typing_timer.stop()
        else:
            self.typing_timer = QTimer(self)
            self.typing_timer.setSingleShot(True)
            self.typing_timer.timeout.connect(lambda: self.update_status(True)) # assume connected if receiving typing
            
        self.typing_timer.start(3000)
