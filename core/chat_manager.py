from PyQt6.QtCore import pyqtSignal, QObject
from ble.gatt_client import BLEGattClient
from messaging.message_handler import MessageHandler

class ChatManager(QObject):
    message_received = pyqtSignal(str, str, str, str) # (chat_id, message_id, sender_id, text)
    connection_status = pyqtSignal(str, bool)
    connection_request_received = pyqtSignal(str, str, str, str) # (user_id, user_name, text, msg_id)
    message_status_changed = pyqtSignal(str, str, str) # (chat_id, msg_id, status)
    typing_indicator_received = pyqtSignal(str) # (user_id)

    def __init__(self, db_manager, current_user_id, current_user_name="", crypto_manager=None, server=None):
        super().__init__()
        self.db = db_manager
        self.crypto = crypto_manager
        self.server = server
        self.current_user_id = current_user_id
        self.current_user_name = current_user_name
        self.pending_handshakes = {}
        
        # map of device_address (chat_id for 1-on-1) -> BLEGattClient (Legacy)
        self.active_clients = {}
        # map of user_id -> mac_address for seamless reversing
        self.user_to_mac = {}
        
        # Dict to track cooldowns for scanning
        self.attempted_reconnects = {}
        
        # Single message handler for incoming chunks
        self.message_handler = MessageHandler()

    def process_incoming_chunk(self, sender_address, chunk_bytes):
        """Called when gatt_server receives a chunk from a connected client"""
        msg_id, payload_str = self.message_handler.process_chunk(chunk_bytes)
        if not payload_str:
            return
            
        import json
        try:
            payload = json.loads(payload_str)
            msg_type = payload.get("type", "msg")
            user_id = payload.get("sender_id", sender_address)
            user_name = payload.get("sender_name", "Unknown")
            text = payload.get("text", "")
        except Exception:
            # Fallback for old/corrupted messages
            msg_type = "msg"
            user_id = sender_address
            user_name = "Unknown"
            text = payload_str

        chat_id = user_id
        str_msg_id = str(msg_id)
        
        if msg_type == "conn_req":
            peer_pub_key = payload.get("pub_key")
            self.pending_handshakes[user_id] = peer_pub_key
            user = self.db.get_user(user_id)
            if not user:
                self.connection_request_received.emit(user_id, user_name, "Connection Request (Secured)", "0")
            else:
                self.accept_connection(user_id, user_name, "", "0")
                
        elif msg_type == "conn_ack":
            peer_pub_key = payload.get("pub_key")
            if peer_pub_key and self.crypto:
                secret = self.crypto.compute_shared_secret(peer_pub_key)
                self.db.update_chat_secret(user_id, secret)
                
            # Connect back to ensure two-way communication is active
            import asyncio
            asyncio.create_task(self.connect_to_user(user_id))

        elif msg_type == "msg":
            if payload.get("encrypted") and self.crypto:
                secret = self.db.get_chat_secret(chat_id)
                if secret:
                    text = self.crypto.decrypt_message(text, secret)
                else:
                    text = "[Encrypted message but no shared secret found!]"
                    
            # Check if this user is known in DB or active
            user = self.db.get_user(user_id)
            if not user and chat_id not in self.active_clients:
                # Prompt user to accept connection
                self.connection_request_received.emit(user_id, user_name, text, str_msg_id)
                return
            
            # Known user, save and emit
            self.db.add_or_update_user(user_id, user_name)
            self.db.create_chat(chat_id, user_name)
            self.db.save_message(str_msg_id, chat_id, user_id, text)
            self.message_received.emit(chat_id, str_msg_id, user_id, text)
            
            # Send ack back
            import asyncio
            if "msg_id" in payload:
                asyncio.create_task(self.send_ack(user_id, payload["msg_id"]))
                
        elif msg_type == "typing":
            self.typing_indicator_received.emit(user_id)
            
        elif msg_type == "ack":
            ack_msg_id = payload.get("msg_id")
            if ack_msg_id:
                self.db.update_message_status(ack_msg_id, "delivered")
                self.message_status_changed.emit(chat_id, ack_msg_id, "delivered")
            
    def accept_connection(self, user_id, user_name, text, str_msg_id):
        # Save user and message
        self.db.add_or_update_user(user_id, user_name)
        self.db.create_chat(user_id, user_name)
        if text: # Might be empty if pure conn_req
            self.db.save_message(str_msg_id, user_id, user_id, text)
            self.message_received.emit(user_id, str_msg_id, user_id, text)
            
        # Compute secret if pending
        peer_pub_key = self.pending_handshakes.pop(user_id, None)
        if peer_pub_key and self.crypto:
            secret = self.crypto.compute_shared_secret(peer_pub_key)
            self.db.update_chat_secret(user_id, secret)

        # Connect back and send conn_ack
        import asyncio
        asyncio.create_task(self._connect_and_ack(user_id))
        
    async def _connect_and_ack(self, user_id):
        success = await self.connect_to_user(user_id)
        if success and self.crypto:
            import json
            payload = json.dumps({
                "type": "conn_ack",
                "sender_id": self.current_user_id,
                "sender_name": self.current_user_name,
                "pub_key": self.crypto.get_public_key_b64()
            })
            
            # Send backwards over client if avail, else broadcast over server
            device_address = self.user_to_mac.get(user_id, user_id)
            client = self.active_clients.get(device_address)
            if client and client.client.is_connected:
                await client.send_message(payload, 0)
            elif self.server:
                from messaging.packet_protocol import PacketProtocol
                _, chunks = PacketProtocol.create_chunks(payload, 0)
                for chunk in chunks:
                    await self.server.send_notification(chunk)
                    await asyncio.sleep(0.05)

    async def connect_to_user(self, target_id):
        device_address = target_id
        
        # Check if we ALREADY have an active, connected client for this user_id
        if target_id in self.user_to_mac:
            known_mac = self.user_to_mac[target_id]
            if known_mac in self.active_clients and self.active_clients[known_mac].client.is_connected:
                return True

        # MAC addresses usually have : or -
        if ":" not in target_id and "-" not in target_id and len(target_id) == 8:
            print(f"Connecting to user {target_id}. Scanning for current MAC address...")
            from bleak import BleakScanner
            devices_dict = await BleakScanner.discover(timeout=6.0, return_adv=True)
            found = False
            for address, (d, adv) in devices_dict.items():
                name = d.name or adv.local_name or ""
                if target_id in name:
                    device_address = address
                    self.user_to_mac[target_id] = device_address
                    found = True
                    break
            if not found:
                print(f"No active device found for user {target_id} in scan")
                return False
                
        if device_address in self.active_clients and self.active_clients[device_address].client.is_connected:
            return True
            
        client = BLEGattClient(device_address)
        client.connection_state_changed.connect(self._handle_connection_change)
        client.notification_received.connect(lambda data: self.process_incoming_chunk(device_address, data))
        
        self.active_clients[device_address] = client
        success = await client.connect()
        return success

    async def disconnect_from_user(self, device_address):
        if device_address in self.active_clients:
            await self.active_clients[device_address].disconnect()
            del self.active_clients[device_address]

    def _handle_connection_change(self, device_address, is_connected):
        self.connection_status.emit(device_address, is_connected)

    async def process_queue(self):
        """Background loop to send pending messages when devices reconnect."""
        import asyncio
        import json
        import time
        while True:
            await asyncio.sleep(5)
            pending = self.db.get_pending_messages()
            
            for msg_id, chat_id, text in pending:
                device_address = chat_id
                if ":" not in chat_id and "-" not in chat_id:
                    device_address = self.user_to_mac.get(chat_id, chat_id)
                
                is_connected = False
                now = time.time()
                
                if device_address in self.active_clients and self.active_clients[device_address].client.is_connected:
                    is_connected = True
                elif now - self.attempted_reconnects.get(chat_id, 0) > 60:
                    self.attempted_reconnects[chat_id] = now
                    is_connected = await self.connect_to_user(chat_id)
                
                if is_connected:
                    payload_dict = {
                        "type": "msg",
                        "msg_id": msg_id,
                        "sender_id": self.current_user_id,
                        "sender_name": self.current_user_name,
                        "text": text
                    }
                    
                    secret = self.db.get_chat_secret(chat_id)
                    if secret and self.crypto:
                        payload_dict["text"] = self.crypto.encrypt_message(text, secret)
                        payload_dict["encrypted"] = True
                        
                    payload = json.dumps(payload_dict)
                    
                    device_address = self.user_to_mac.get(chat_id, chat_id)
                    client = self.active_clients.get(device_address)
                    msg_id_int = int(msg_id) if msg_id.isdigit() else 0
                    
                    success = False
                    if client and client.client.is_connected:
                        success = await client.send_message(payload, msg_id_int)
                    elif self.server:
                        from messaging.packet_protocol import PacketProtocol
                        _, chunks = PacketProtocol.create_chunks(payload, msg_id_int)
                        for chunk in chunks:
                            await self.server.send_notification(chunk)
                            await asyncio.sleep(0.05)
                        success = True # Assume success if broadcasted via Server

                    if success:
                        self.db.update_message_status(msg_id, "sent")
                        self.message_status_changed.emit(chat_id, msg_id, "sent")

    async def send_message(self, chat_id, text):
        """Sends a message to the specified chat_id (device address)"""
        import uuid
        msg_id_int = uuid.uuid4().int & 0x7FFFFFFF
        str_msg_id = str(msg_id_int)
        
        self.db.save_message(str_msg_id, chat_id, self.current_user_id, text, status="pending")
        self.message_received.emit(chat_id, str_msg_id, self.current_user_id, text)

        import json
        payload = {
            "type": "msg",
            "msg_id": str_msg_id,
            "sender_id": self.current_user_id,
            "sender_name": self.current_user_name,
            "text": text
        }
        
        # Encrypt text if we have a shared secret
        secret = self.db.get_chat_secret(chat_id)
        if secret and self.crypto:
            payload["text"] = self.crypto.encrypt_message(text, secret)
            payload["encrypted"] = True
            
        payload_str = json.dumps(payload)

        # Resolve MAC and connection
        device_address = chat_id
        if ":" not in chat_id and "-" not in chat_id and len(chat_id) == 8:
            device_address = self.user_to_mac.get(chat_id, chat_id)

        if device_address not in self.active_clients or not self.active_clients[device_address].client.is_connected:
            if device_address == "unknown_sender":
                return False
                
            # Try to connect
            success = await self.connect_to_user(chat_id)
            if not success:
                print(f"Failed to connect to {chat_id} to send message. Queued offline.")
                return False
                
            # Re-resolve MAC in case it changed during scan
            if ":" not in chat_id and "-" not in chat_id and len(chat_id) == 8:
                device_address = self.user_to_mac.get(chat_id, chat_id)
                
        client = self.active_clients.get(device_address)
        
        success = False
        if client and client.client.is_connected:
            success = await client.send_message(payload_str, msg_id_int)
        elif self.server:
            from messaging.packet_protocol import PacketProtocol
            _, chunks = PacketProtocol.create_chunks(payload_str, msg_id_int)
            for chunk in chunks:
                await self.server.send_notification(chunk)
                await asyncio.sleep(0.05)
            success = True
            
        if success:
            self.db.update_message_status(str_msg_id, "sent")
            self.message_status_changed.emit(chat_id, str_msg_id, "sent")
        return success

    async def send_typing(self, chat_id):
        device_address = chat_id
        if ":" not in chat_id and "-" not in chat_id and len(chat_id) == 8:
            device_address = self.user_to_mac.get(chat_id, chat_id)
        if device_address in self.active_clients and self.active_clients[device_address].client.is_connected:
            import json
            payload = json.dumps({"type": "typing", "sender_id": self.current_user_id})
            client = self.active_clients[device_address]
            await client.send_message(payload, 0)
        elif self.server:
            import json
            from messaging.packet_protocol import PacketProtocol
            payload = json.dumps({"type": "typing", "sender_id": self.current_user_id})
            _, chunks = PacketProtocol.create_chunks(payload, 0)
            for chunk in chunks:
                await self.server.send_notification(chunk)
                await asyncio.sleep(0.02)

    async def send_conn_req(self, chat_id):
        device_address = chat_id
        if ":" not in chat_id and "-" not in chat_id and len(chat_id) == 8:
            device_address = self.user_to_mac.get(chat_id, chat_id)
        if device_address in self.active_clients and self.active_clients[device_address].client.is_connected and self.crypto:
            import json
            payload = json.dumps({
                "type": "conn_req",
                "sender_id": self.current_user_id,
                "sender_name": self.current_user_name,
                "pub_key": self.crypto.get_public_key_b64()
            })
            client = self.active_clients[device_address]
            await client.send_message(payload, 0)
        elif self.server and self.crypto:
            import json
            from messaging.packet_protocol import PacketProtocol
            payload = json.dumps({
                "type": "conn_req",
                "sender_id": self.current_user_id,
                "sender_name": self.current_user_name,
                "pub_key": self.crypto.get_public_key_b64()
            })
            _, chunks = PacketProtocol.create_chunks(payload, 0)
            for chunk in chunks:
                await self.server.send_notification(chunk)
                await asyncio.sleep(0.05)

    async def send_ack(self, chat_id, msg_id):
        device_address = chat_id
        if ":" not in chat_id and "-" not in chat_id and len(chat_id) == 8:
            device_address = self.user_to_mac.get(chat_id, chat_id)
        if device_address in self.active_clients and self.active_clients[device_address].client.is_connected:
            import json
            payload = json.dumps({"type": "ack", "msg_id": msg_id, "sender_id": self.current_user_id})
            client = self.active_clients[device_address]
            await client.send_message(payload, 0)
        elif self.server:
            import json
            from messaging.packet_protocol import PacketProtocol
            payload = json.dumps({"type": "ack", "msg_id": msg_id, "sender_id": self.current_user_id})
            _, chunks = PacketProtocol.create_chunks(payload, 0)
            for chunk in chunks:
                await self.server.send_notification(chunk)
                await asyncio.sleep(0.02)
