import asyncio
from bless import (
    BlessServer,
    BlessGATTCharacteristic,
    GATTCharacteristicProperties,
    GATTAttributePermissions
)
from PyQt6.QtCore import pyqtSignal, QObject
import time

CHAT_SERVICE_UUID = "12345678-1234-5678-1234-56789abcdef0"
MSG_WRITE_UUID =    "12345678-1234-5678-1234-56789abcdef1"  # For receiving chunks
MSG_NOTIFY_UUID =   "12345678-1234-5678-1234-56789abcdef2"  # For sending chunks

class BLEGattServer(QObject):
    chunk_received = pyqtSignal(bytes)
    
    # We emit a list of characteristic uuids read
    read_event = pyqtSignal(str) 

    def __init__(self, device_name):
        super().__init__()
        self.server = None
        self.device_name = device_name

    def read_request(self, characteristic):
        print(f"Read request for {characteristic.uuid}")
        self.read_event.emit(characteristic.uuid)
        return characteristic.value

    def write_request(self, characteristic, value):
        print(f"Write request for {characteristic.uuid}: {value}")
        if characteristic.uuid == MSG_WRITE_UUID:
            # We received a chunk of data from a connected client!
            # Emit it to the Qt Event Loop safely, ensure it's converted to bytes 
            # as bless might return a bytearray
            self.chunk_received.emit(bytes(value))
            
            # Update value locally
            self.server.get_characteristic(MSG_WRITE_UUID).value = value

    async def start_server(self):
        try:
            self.server = BlessServer(name=self.device_name)
        except Exception as e:
            print(f"Failed to initialize BLE Server (Peripheral mode may be unsupported or BT is busy): {e}")
            return
            
        self.server.read_request_func = self.read_request
        self.server.write_request_func = self.write_request

        # Add Service
        await self.server.add_new_service(CHAT_SERVICE_UUID)
        
        # Add Write Characteristic (so other devices can write to us)
        char_flags = GATTCharacteristicProperties.write | GATTCharacteristicProperties.write_without_response
        permissions = GATTAttributePermissions.writeable
        await self.server.add_new_characteristic(
            CHAT_SERVICE_UUID,
            MSG_WRITE_UUID,
            char_flags,
            b"",
            permissions
        )
        
        # Add Notify Characteristic
        char_flags = GATTCharacteristicProperties.notify | GATTCharacteristicProperties.read
        permissions = GATTAttributePermissions.readable
        await self.server.add_new_characteristic(
            CHAT_SERVICE_UUID,
            MSG_NOTIFY_UUID,
            char_flags,
            b"HELLO", # Initial value
            permissions
        )

        # Start Bless Server
        self.server.get_characteristic(MSG_NOTIFY_UUID).value = b"HELLO"
        try:
            print(f"Starting BLE Server: {self.device_name}")
            await self.server.start()
            print("BLE Server Started successfully.")
        except Exception as e:
            print(f"Error starting server: {e}")

    async def stop_server(self):
        if self.server:
            try:
                await self.server.stop()
                print("BLE Server Stopped")
            except Exception as e:
                print(f"Error stopping server: {e}")

    async def send_notification(self, value):
        """Sends data out via Notification to connected clients"""
        if self.server:
            try:
                self.server.get_characteristic(MSG_NOTIFY_UUID).value = value
                self.server.update_value(CHAT_SERVICE_UUID, MSG_NOTIFY_UUID)
                await asyncio.sleep(0.05) # Yield
            except Exception as e:
                print(f"Notification error: {e}")

