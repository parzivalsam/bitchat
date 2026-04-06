import time

class MessageHandler:
    def __init__(self):
        # Dictionary to store incoming chunks
        # Format: { msg_id: { 'total': X, 'chunks': {seq_num: chunk_data}, 'timestamp': time.time() } }
        self.incoming_messages = {}
        # Simple cleanup timeout in seconds (to clear incomplete messages)
        self.CLEANUP_TIMEOUT = 60 

    def process_chunk(self, chunk_bytes):
        """
        Processes an incoming chunk.
        If the message is complete, returns the fully reassembled (msg_id, string_message).
        Otherwise returns (None, None).
        """
        from .packet_protocol import PacketProtocol
        
        parsed = PacketProtocol.parse_chunk(chunk_bytes)
        if not parsed:
            return None, None
            
        msg_id, seq_num, total_seq, chunk_data = parsed
        
        if msg_id not in self.incoming_messages:
            self.incoming_messages[msg_id] = {
                'total': total_seq,
                'chunks': {},
                'timestamp': time.time()
            }
            
        msg_record = self.incoming_messages[msg_id]
        msg_record['chunks'][seq_num] = chunk_data
        msg_record['timestamp'] = time.time()
        
        # Check if all chunks received
        if len(msg_record['chunks']) == msg_record['total']:
            # Reassemble
            full_data = bytearray()
            for i in range(1, msg_record['total'] + 1):
                full_data.extend(msg_record['chunks'][i])
            
            # Clean up
            del self.incoming_messages[msg_id]
            
            try:
                decoded_msg = full_data.decode('utf-8')
                return msg_id, decoded_msg
            except UnicodeDecodeError:
                # Corrupted data
                return msg_id, "<corrupted message>"
                
        self._cleanup_old_messages()
        return None, None

    def _cleanup_old_messages(self):
        """Removes incomplete messages that have timed out."""
        current_time = time.time()
        to_delete = []
        for msg_id, record in self.incoming_messages.items():
            if current_time - record['timestamp'] > self.CLEANUP_TIMEOUT:
                to_delete.append(msg_id)
                
        for msg_id in to_delete:
            del self.incoming_messages[msg_id]
