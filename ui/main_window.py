from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStackedWidget,
)
from PyQt6.QtCore import Qt, pyqtSignal
from .chat_window import ChatWindow
from .nearby_devices_window import NearbyDevicesWindow
import qasync
import asyncio


class MainWindow(QMainWindow):
    def __init__(self, db_manager, chat_manager, group_manager, scanner, server):
        super().__init__()
        self.db = db_manager
        self.chat_manager = chat_manager
        self.group_manager = group_manager
        self.scanner = scanner
        self.server = server

        self.setWindowTitle("BLE Proximity Chat")
        self.resize(1000, 700)
        self.setStyleSheet("background-color: #121212; color: #ffffff;")

        self.chat_windows = {}  # chat_id -> ChatWindow

        self._setup_ui()
        self._load_chats()

        # Connect signals
        self.chat_manager.message_received.connect(self.on_message_received)
        self.chat_manager.connection_status.connect(self.on_connection_change)
        self.chat_manager.connection_request_received.connect(self.on_connection_request)
        self.chat_manager.message_status_changed.connect(self.on_message_status_changed)
        self.chat_manager.typing_indicator_received.connect(self.on_typing_indicator)
        
        # Start offline delivery queue
        asyncio.get_event_loop().create_task(self.chat_manager.process_queue())

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- LEFT SIDEBAR ---
        sidebar = QWidget()
        sidebar.setFixedWidth(350)
        sidebar.setStyleSheet(
            "background-color: #1e1e24; border-right: 1px solid #333333;"
        )
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)

        # Header
        header = QWidget()
        header.setStyleSheet("background-color: #2b2b36; padding: 15px;")
        header_layout = QHBoxLayout(header)

        title_label = QLabel("Chats")
        title_label.setStyleSheet("font-size: 20px; font-weight: bold; color: #ffffff;")
        header_layout.addWidget(title_label)

        nearby_btn = QPushButton("📡 Nearby")
        nearby_btn.setStyleSheet(
            """
            QPushButton { background-color: #3a3b45; color: #ffffff; border-radius: 15px; padding: 8px 15px; font-weight: bold; border: none; }
            QPushButton:hover { background-color: #4a4b59; }
        """
        )
        nearby_btn.clicked.connect(self.show_nearby_devices)
        header_layout.addWidget(nearby_btn)

        sidebar_layout.addWidget(header)

        # Chat List
        self.chat_list = QListWidget()
        self.chat_list.setStyleSheet(
            """
            QListWidget { border: none; background: transparent; color: #e4e4e7; }
            QListWidget::item { padding: 15px; border-bottom: 1px solid #333333; }
            QListWidget::item:selected { background-color: #3a3b45; color: #ffffff; }
        """
        )
        self.chat_list.itemClicked.connect(self.on_chat_selected)
        sidebar_layout.addWidget(self.chat_list)

        main_layout.addWidget(sidebar)

        # --- RIGHT AREA (Chat View) ---
        self.right_area = QStackedWidget()
        self.right_area.setStyleSheet("background-color: #121212;")

        # Welcome screen
        welcome = QLabel("Select a chat or find nearby devices to start messaging")
        welcome.setAlignment(Qt.AlignmentFlag.AlignCenter)
        welcome.setStyleSheet("font-size: 16px; color: #a1a1aa;")
        self.right_area.addWidget(welcome)

        main_layout.addWidget(self.right_area)

    def _load_chats(self):
        self.chat_list.clear()
        chats = self.db.get_chats()
        for chat_id, chat_name, chat_type, last_msg, last_time in chats:
            self._add_chat_to_list(chat_id, chat_name, last_msg, last_time)

    def _add_chat_to_list(self, chat_id, chat_name, last_msg="", last_time=""):
        display_text = f"{chat_name}"
        if last_msg:
            snippet = last_msg[:30] + "..." if len(last_msg) > 30 else last_msg
            display_text += f"\n{snippet}"

        item = QListWidgetItem(display_text)
        item.setData(Qt.ItemDataRole.UserRole, chat_id)
        self.chat_list.addItem(item)

    def show_nearby_devices(self):
        self.dialog = NearbyDevicesWindow(self.scanner, self.chat_manager, self)
        
        # start scan in background
        asyncio.create_task(self.scanner.start_scanning())
        self.dialog.scan_btn.setText("Stop Scan")
        
        self.dialog.finished.connect(self._on_nearby_dialog_finished)
        self.dialog.open()

    def _on_nearby_dialog_finished(self, result):
        asyncio.create_task(self.scanner.stop_scanning())
        self._load_chats()
        if hasattr(self.dialog, 'connected_address'):
            self._open_chat_by_id(self.dialog.connected_address)

    def _open_chat_by_id(self, chat_id):
        for i in range(self.chat_list.count()):
            item = self.chat_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == chat_id:
                self.chat_list.setCurrentItem(item)
                self.on_chat_selected(item)
                break

    def on_chat_selected(self, item):
        chat_id = item.data(Qt.ItemDataRole.UserRole)

        chats = self.db.get_chats()
        chat_info = next((c for c in chats if c[0] == chat_id), None)
        if not chat_info:
            return

        chat_name = chat_info[1]
        is_group = chat_info[2] == "group"

        if chat_id not in self.chat_windows:
            win = ChatWindow(chat_id, chat_name, self.chat_manager, is_group, self)
            self.chat_windows[chat_id] = win
            self.right_area.addWidget(win)

        self.right_area.setCurrentWidget(self.chat_windows[chat_id])

    def on_message_received(self, chat_id, msg_id, sender_id, text):
        if chat_id in self.chat_windows:
            import datetime

            now = datetime.datetime.now().isoformat()
            self.chat_windows[chat_id].display_message(sender_id, text, now)

        self._load_chats()

    def on_connection_change(self, device_address, is_connected):
        status = "Connected" if is_connected else "Disconnected"
        print(f"Device {device_address} is now {status}")
        
        user_id = None
        for uid, mac in self.chat_manager.user_to_mac.items():
            if mac == device_address:
                user_id = uid
                break
        chat_id = user_id or device_address
        
        if chat_id in self.chat_windows:
            self.chat_windows[chat_id].update_status(is_connected)

    def on_connection_request(self, user_id, user_name, text, msg_id):
        from PyQt6.QtWidgets import QMessageBox
        
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle('Connection Request')
        msg_box.setText(f"{user_name} wants to connect and sent:\n\n{text}\n\nAccept connection?")
        msg_box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        msg_box.setDefaultButton(QMessageBox.StandardButton.Yes)
        
        # Use open() instead of exec() to strictly prevent qasync event loop freezes
        def on_finished(result):
            if result == QMessageBox.StandardButton.Yes:
                self.chat_manager.accept_connection(user_id, user_name, text, msg_id)
                self._load_chats()
                self._open_chat_by_id(user_id)
                
        msg_box.finished.connect(on_finished)
        msg_box.open()

    def on_message_status_changed(self, chat_id, msg_id, status):
        # Reload chat history for the affected window to update ticks
        if chat_id in self.chat_windows:
            self.chat_windows[chat_id]._load_history()

    def on_typing_indicator(self, user_id):
        if user_id in self.chat_windows:
            self.chat_windows[user_id].show_typing_indicator()

    def closeEvent(self, event):
        # Prevent multiple close tasks if user clicks X repeatedly
        if hasattr(self, '_is_closing') and self._is_closing:
            event.ignore()
            return
            
        self._is_closing = True
        
        # Hide window instantly so it feels responsive
        self.hide()
        event.ignore()
        
        import asyncio
        from PyQt6.QtWidgets import QApplication
        import sys
        import os
        
        async def safely_shutdown():
            try:
                if self.server:
                    await self.server.stop_server()
                if self.scanner.is_scanning:
                    await self.scanner.stop_scanning()
            finally:
                QApplication.quit()
                os._exit(0) # Force hard exit to prevent bless from keeping python alive
            
        asyncio.get_event_loop().create_task(safely_shutdown())
