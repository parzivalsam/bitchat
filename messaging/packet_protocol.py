import struct
import math
import uuid

# BLE MTU size is typically 23 bytes minimum, 
# 3 bytes are used for ATT header, so 20 bytes payload is safe.
MAX_PAYLOAD_SIZE = 20

# Header: 4 bytes (message_id partial), 2 bytes (seq_num), 2 bytes (total_seq) = 8 bytes
# Max data per chunk: 20 - 8 = 12 bytes
HEADER_FORMAT = "<ihh"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)
MAX_CHUNK_DATA = MAX_PAYLOAD_SIZE - HEADER_SIZE

class PacketProtocol:
    @staticmethod
    def create_chunks(message_text, message_id_int=None):
        """
        Splits a string message into a list of bytes (chunks) fit for BLE.
        Returns (message_id_int, list_of_chunks_bytes)
        """
        if message_id_int is None:
            # Generate a random 4-byte integer ID (signed int for struct 'i')
            # 0x7FFFFFFF is the max positive value for a signed 32-bit int
            message_id_int = uuid.uuid4().int & 0x7FFFFFFF
            
        data_bytes = message_text.encode('utf-8')
        total_chunks = math.ceil(len(data_bytes) / MAX_CHUNK_DATA)
        if total_chunks == 0:
            total_chunks = 1 # Send empty string if data is empty
            
        chunks = []
        for i in range(total_chunks):
            start = i * MAX_CHUNK_DATA
            end = start + MAX_CHUNK_DATA
            chunk_data = data_bytes[start:end]
            
            # Header: msg_id (4 bytes), seq_num (2 bytes, 1-indexed), total_seq (2 bytes)
            header = struct.pack(HEADER_FORMAT, message_id_int, i + 1, total_chunks)
            chunks.append(header + chunk_data)
            
        return message_id_int, chunks

    @staticmethod
    def parse_chunk(chunk_bytes):
        """
        Parses a single BLE chunk.
        Returns (msg_id, seq_num, total_seq, chunk_data_bytes) or None on failure
        """
        if len(chunk_bytes) < HEADER_SIZE:
            return None
            
        header = chunk_bytes[:HEADER_SIZE]
        chunk_data = chunk_bytes[HEADER_SIZE:]
        
        try:
            msg_id, seq_num, total_seq = struct.unpack(HEADER_FORMAT, header)
            return msg_id, seq_num, total_seq, chunk_data
        except struct.error:
            return None
