from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QListWidget,
    QListWidgetItem,
)
from PyQt6.QtCore import Qt
from qasync import asyncSlot
import qasync
import asyncio


class NearbyDevicesWindow(QDialog):
    def __init__(self, scanner, chat_manager, parent=None):
        super().__init__(parent)
        self.scanner = scanner
        self.chat_manager = chat_manager

        self.setWindowTitle("Nearby Devices")
        self.setFixedSize(400, 500)
        self.setStyleSheet("background-color: white;")

        self.devices = {}  # address -> name

        self._setup_ui()

        # Connect scanner signal
        self.scanner.device_found.connect(self.on_device_found)

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        title = QLabel("Scanning for nearby devices...")
        title.setStyleSheet(
            "font-size: 16px; font-weight: bold; color: #333; padding: 10px;"
        )
        layout.addWidget(title)

        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet(
            """
            QListWidget { border: 1px solid #ccc; border-radius: 5px; }
            QListWidget::item { padding: 10px; border-bottom: 1px solid #eee; }
            QListWidget::item:selected { background-color: #f0f2f5; color: black; }
        """
        )
        layout.addWidget(self.list_widget)

        btn_layout = QHBoxLayout()

        self.scan_btn = QPushButton("Stop Scan")
        self.scan_btn.setStyleSheet(
            "padding: 10px; background-color: #f0f2f5; border-radius: 5px;"
        )
        self.scan_btn.clicked.connect(self.toggle_scan)
        btn_layout.addWidget(self.scan_btn)

        self.connect_btn = QPushButton("Connect")
        self.connect_btn.setStyleSheet(
            """
            QPushButton { background-color: #00a884; color: white; padding: 10px; font-weight: bold; border-radius: 5px; }
            QPushButton:hover { background-color: #008f6f; }
            QPushButton:disabled { background-color: #ccc; }
        """
        )
        self.connect_btn.clicked.connect(self.connect_to_selected)
        self.connect_btn.setEnabled(False)
        btn_layout.addWidget(self.connect_btn)

        self.list_widget.itemSelectionChanged.connect(
            lambda: self.connect_btn.setEnabled(
                len(self.list_widget.selectedItems()) > 0
            )
        )

        layout.addLayout(btn_layout)

    def on_device_found(self, device, adv_data, user_id):
        if device.address not in self.devices:
            if user_id:
                name = f"User {user_id}"
            else:
                name = device.name or "Unknown Device"
                
            rssi = adv_data.rssi if adv_data else "N/A"
            display_text = f"{name} ({device.address})   [RSSI: {rssi}]"

            self.devices[device.address] = {"name": name, "user_id": user_id}

            item = QListWidgetItem(display_text)
            item.setData(Qt.ItemDataRole.UserRole, device.address)
            self.list_widget.addItem(item)

    @asyncSlot()
    async def toggle_scan(self):
        if self.scanner.is_scanning:
            await self.scanner.stop_scanning()
            self.scan_btn.setText("Start Scan")
        else:
            self.list_widget.clear()
            self.devices.clear()
            await self.scanner.start_scanning()
            self.scan_btn.setText("Stop Scan")


    def connect_to_selected(self):
        asyncio.create_task(self._connect_to_selected())


    async def _connect_to_selected(self):
        selected = self.list_widget.selectedItems()
        if not selected:
            return

        address = selected[0].data(Qt.ItemDataRole.UserRole)
        device_info = self.devices.get(address, {})
        if isinstance(device_info, dict):
            name = device_info.get("name", "Unknown")
            user_id = device_info.get("user_id")
        else:
            name = str(device_info)
            user_id = None
            
        if not user_id:
            user_id = address # fallback

        self.connect_btn.setText("Connecting...")
        self.connect_btn.setEnabled(False)

    # Stop scanning before connecting
        await self.scanner.stop_scanning()
        self.scan_btn.setText("Start Scan")

        success = await self.chat_manager.connect_to_user(address)

        if success:
            if user_id != address:
                self.chat_manager.user_to_mac[user_id] = address
                
            await self.chat_manager.send_conn_req(user_id)
            
            self.chat_manager.db.add_or_update_user(user_id, name)
            self.chat_manager.db.create_chat(user_id, name)
            self.connected_address = user_id
            self.accept()   # close dialog
        else:
            self.connect_btn.setText("Failed. Try Again")
            self.connect_btn.setEnabled(True)

    def closeEvent(self, event):
        if self.scanner.is_scanning:
            asyncio.create_task(self.scanner.stop_scanning())
        super().closeEvent(event)
