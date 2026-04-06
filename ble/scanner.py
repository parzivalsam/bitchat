import asyncio
from bleak import BleakScanner
from PyQt6.QtCore import pyqtSignal, QObject

# Define the UUID that our app will advertise
CHAT_SERVICE_UUID = "12345678-1234-5678-1234-56789abcdef0"

class BLEScanner(QObject):
    device_found = pyqtSignal(object, object, str)  # Emits (device, advertisement_data, user_id) 

    def __init__(self):
        super().__init__()
        self.scanner = None
        self.is_scanning = False

    def detection_callback(self, device, advertisement_data):
        # Check if the device is advertising our chosen Chat Service UUID
        if CHAT_SERVICE_UUID.lower() in [u.lower() for u in advertisement_data.service_uuids]:
            name = device.name or advertisement_data.local_name or ""
            user_id = None
            if name.startswith("BLECHAT_"):
                parts = name.split("_")
                if len(parts) >= 2:
                    user_id = parts[1]
            self.device_found.emit(device, advertisement_data, user_id or "")

    async def start_scanning(self):
        if self.is_scanning:
            return
        
        self.is_scanning = True
        self.scanner = BleakScanner(self.detection_callback)
        try:
            await self.scanner.start()
        except Exception as e:
            print(f"Failed to start scanner: {e}")
            self.is_scanning = False

    async def stop_scanning(self):
        if not self.is_scanning or not self.scanner:
            return
            
        try:
            await self.scanner.stop()
        except Exception as e:
            print(f"Failed to stop scanner: {e}")
        finally:
            self.is_scanning = False
