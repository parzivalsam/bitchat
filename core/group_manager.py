from PyQt6.QtCore import QObject

class GroupManager(QObject):
    def __init__(self, db_manager, chat_manager):
        super().__init__()
        self.db = db_manager
        self.chat_manager = chat_manager
        
    def create_group(self, group_name):
        import uuid
        group_id = str(uuid.uuid4())
        self.db.create_chat(group_id, group_name, chat_type='group')
        return group_id
        
    def add_member(self, group_id, user_id):
        self.db.add_group_member(group_id, user_id)
        
    async def broadcast_message(self, group_id, text, sender_id):
        """Sends message to all connected members of the group"""
        members = self.db.get_group_members(group_id)
        
        # Save to DB once
        import uuid
        msg_id_int = uuid.uuid4().int & 0x7FFFFFFF
        str_msg_id = str(msg_id_int)
        
        self.db.save_message(str_msg_id, group_id, sender_id, text)
        self.chat_manager.message_received.emit(group_id, str_msg_id, sender_id, text)
        
        # Broadcast to others
        for member_id in members:
            # Send message to each member individually via BLE Client
            if member_id != sender_id:
                # We reuse the chat manager's connect and send logic
                if member_id not in self.chat_manager.active_clients or not self.chat_manager.active_clients[member_id].client.is_connected:
                    await self.chat_manager.connect_to_user(member_id)
                    
                if member_id in self.chat_manager.active_clients and self.chat_manager.active_clients[member_id].client.is_connected:
                    # Prepend group_id to message so receiver knows it's for a group (Simple protocol)
                    group_msg = f"[GRP:{group_id}]{text}"
                    await self.chat_manager.active_clients[member_id].send_message(group_msg, msg_id_int)
