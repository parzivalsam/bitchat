import asyncio
from bleak import BleakClient
from PyQt6.QtCore import pyqtSignal, QObject
from messaging.packet_protocol import PacketProtocol

CHAT_SERVICE_UUID = "12345678-1234-5678-1234-56789abcdef0"
MSG_WRITE_UUID =    "12345678-1234-5678-1234-56789abcdef1"  
MSG_NOTIFY_UUID =   "12345678-1234-5678-1234-56789abcdef2"

class BLEGattClient(QObject):
    connection_state_changed = pyqtSignal(str, bool) # (device_address, is_connected)
    notification_received = pyqtSignal(bytes)        

    def __init__(self, device_address):
        super().__init__()
        self.client = BleakClient(device_address, disconnected_callback=self.handle_disconnect)
        self.device_address = device_address

    def handle_disconnect(self, client):
        print(f"Disconnected from {self.device_address}")
        self.connection_state_changed.emit(self.device_address, False)

    def notification_handler(self, sender, data):
        """Called when the server notifies via MSG_NOTIFY_UUID"""
        print(f"Received notification from {sender}: {data}")
        self.notification_received.emit(data)

    async def connect(self):
        try:
            await self.client.connect()
            print(f"Connected to {self.device_address}")
            self.connection_state_changed.emit(self.device_address, True)
            
            # Subscribe to notifications from the target server
            await self.client.start_notify(MSG_NOTIFY_UUID, self.notification_handler)
            return True
        except Exception as e:
            print(f"Failed to connect: {e}")
            return False

    async def disconnect(self):
        try:
            if self.client.is_connected:
                await self.client.stop_notify(MSG_NOTIFY_UUID)
                await self.client.disconnect()
        except Exception as e:
            print(f"Error disconnecting: {e}")

    async def send_message(self, message_text, msg_id=None):
        if not self.client.is_connected:
            print("Cannot send message, not connected!")
            return False
            
        # Chunk message
        out_msg_id, chunks = PacketProtocol.create_chunks(message_text, msg_id)
        
        # Send chunks sequentially
        try:
            for chunk in chunks:
                await self.client.write_gatt_char(MSG_WRITE_UUID, chunk, response=False)
                # Small sleep to allow BLE stack to breathe
                await asyncio.sleep(0.05)
            print(f"Sent message {out_msg_id} in {len(chunks)} chunks.")
            return True
        except Exception as e:
            print(f"Error sending message chunk: {e}")
            return False
