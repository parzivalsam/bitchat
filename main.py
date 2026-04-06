import sys
import asyncio
from PyQt6.QtWidgets import QApplication
import qasync
import uuid
import os
import json

from database.db_manager import DBManager
from core.chat_manager import ChatManager
from core.group_manager import GroupManager
from core.crypto_manager import CryptoManager
from ble.scanner import BLEScanner
from ble.gatt_server import BLEGattServer
from ui.main_window import MainWindow


def get_or_create_profile():
    config_path = "config.json"
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                config = json.load(f)
                if "user_id" in config and "device_name" in config:
                    return config["user_id"], config["device_name"]
        except Exception:
            pass
            
    # Generate new if missing or corrupt
    user_id = str(uuid.uuid4())[:8]
    hostname = os.environ.get('COMPUTERNAME', 'WindowsPC')
    device_name = f"{hostname}-{user_id[-4:]}"
    with open(config_path, "w") as f:
        json.dump({"user_id": user_id, "device_name": device_name}, f)
    return user_id, device_name

def main():
    app = QApplication(sys.argv)
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    # Initialize Components
    db = DBManager("chat_history.db")

    # Persistent User Profile
    my_user_id, my_device_name = get_or_create_profile()
    db.add_or_update_user(my_user_id, my_device_name)
    
    crypto_mgr = CryptoManager()

    scanner = BLEScanner()
    # Advertise privacy-first string
    adv_name = f"BLECHAT_{my_user_id}"
    server = BLEGattServer(adv_name)

    chat_manager = ChatManager(db, my_user_id, my_device_name, crypto_mgr)
    group_manager = GroupManager(db, chat_manager)

    # Since we can't easily get the MAC address of the remote device writing to us,
    # we will use a generic "unknown_sender" ID. If the active device replies,
    # we can try to guess the sender or we just show the message in a generic chat.
    # Note: bless module does not trivially expose the remote client's MAC on a write event.
    server.chunk_received.connect(
        lambda data: chat_manager.process_incoming_chunk("unknown_sender", data)
    )

    main_window = MainWindow(db, chat_manager, group_manager, scanner, server)
    main_window.show()

    # Start BLE Server asynchronously
    loop.create_task(server.start_server())

    with loop:
        loop.run_forever()


if __name__ == "__main__":
    main()
