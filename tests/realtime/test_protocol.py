# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import unittest
import gzip
import json
from veadk.realtime import protocol


class TestProtocolFunctions(unittest.TestCase):
    def test_generate_header_default(self):
        """Test generate_header with default parameters"""
        header = protocol.generate_header()
        self.assertEqual(len(header), 4)  # Default header size is 1 (4 bytes)
        self.assertEqual(header[0] >> 4, protocol.PROTOCOL_VERSION)
        self.assertEqual(header[0] & 0x0F, 1)  # header_size
        self.assertEqual(header[1] >> 4, protocol.CLIENT_FULL_REQUEST)
        self.assertEqual(header[1] & 0x0F, protocol.MSG_WITH_EVENT)
        self.assertEqual(header[2] >> 4, protocol.JSON)
        self.assertEqual(header[2] & 0x0F, protocol.GZIP)
        self.assertEqual(header[3], 0x00)

    def test_generate_header_with_extension(self):
        """Test generate_header with extension header"""
        extension = b"\x01\x02\x03\x04"
        header = protocol.generate_header(extension_header=extension)
        self.assertEqual(len(header), 8)  # header_size=2 (8 bytes)
        self.assertEqual(header[0] & 0x0F, 2)  # header_size
        self.assertEqual(header[4:], extension)

    def test_generate_header_various_combinations(self):
        """Test generate_header with various parameter combinations"""
        # Test different message types
        for msg_type in [
            protocol.CLIENT_FULL_REQUEST,
            protocol.CLIENT_AUDIO_ONLY_REQUEST,
        ]:
            header = protocol.generate_header(message_type=msg_type)
            self.assertEqual(header[1] >> 4, msg_type)

        # Test different flags
        for flag in [
            protocol.NO_SEQUENCE,
            protocol.POS_SEQUENCE,
            protocol.NEG_SEQUENCE,
            protocol.MSG_WITH_EVENT,
        ]:
            header = protocol.generate_header(message_type_specific_flags=flag)
            self.assertEqual(header[1] & 0x0F, flag)

        # Test different serialization methods
        for serial in [
            protocol.NO_SERIALIZATION,
            protocol.JSON,
            protocol.THRIFT,
            protocol.CUSTOM_TYPE,
        ]:
            header = protocol.generate_header(serial_method=serial)
            self.assertEqual(header[2] >> 4, serial)

        # Test different compression types
        for comp in [
            protocol.NO_COMPRESSION,
            protocol.GZIP,
            protocol.CUSTOM_COMPRESSION,
        ]:
            header = protocol.generate_header(compression_type=comp)
            self.assertEqual(header[2] & 0x0F, comp)

    def test_parse_response_invalid_input(self):
        """Test parse_response with invalid inputs"""
        # Test with string input
        self.assertEqual(protocol.parse_response("invalid"), {})

        # Test with too short response
        self.assertEqual(
            protocol.parse_response(b"\x01"), {"error": "Response too short"}
        )

        # Test with invalid header size
        invalid_header = (
            bytes([(protocol.PROTOCOL_VERSION << 4) | 0x00]) + b"\x00\x00\x00"
        )  # header_size=0
        self.assertEqual(
            protocol.parse_response(invalid_header), {"error": "Invalid header size: 0"}
        )

        # Test with response shorter than header indicates
        short_response = (
            bytes([(protocol.PROTOCOL_VERSION << 4) | 0x02]) + b"\x00\x00\x00"
        )  # header_size=2 but only 1 byte
        self.assertEqual(
            protocol.parse_response(short_response),
            {"error": "Response shorter than header indicates"},
        )

    def test_parse_response_server_full_response(self):
        """Test parse_response with SERVER_FULL_RESPONSE"""
        # Create test data
        test_data = json.dumps({"key": "value"}).encode("utf-8")
        compressed_data = gzip.compress(test_data)

        # Build response
        header = bytes(
            [
                (protocol.PROTOCOL_VERSION << 4) | 0x01,  # version + header_size=1
                (protocol.SERVER_FULL_RESPONSE << 4)
                | (protocol.NEG_SEQUENCE | protocol.MSG_WITH_EVENT),  # type + flags
                (protocol.JSON << 4) | protocol.GZIP,  # serial + compression
                0x00,  # reserved
            ]
        )

        # Add payload
        seq_num = 1234
        event = 5678
        session_id = b"session123"
        payload = (
            seq_num.to_bytes(4, "big")
            + event.to_bytes(4, "big")
            + len(session_id).to_bytes(4, "big", signed=True)
            + session_id
            + len(compressed_data).to_bytes(4, "big")
            + compressed_data
        )
        response = header + payload

        # Parse and verify
        result = protocol.parse_response(response)
        self.assertEqual(result["message_type"], "SERVER_FULL_RESPONSE")
        self.assertEqual(result["seq"], seq_num)
        # self.assertEqual(result['event'], event)
        self.assertEqual(result["session_id"], "b'session123'")
        self.assertEqual(result["payload_size"], len(compressed_data))
        self.assertEqual(result["payload_msg"], {"key": "value"})

    def test_parse_response_server_ack(self):
        """Test parse_response with SERVER_ACK"""
        # Build response with no sequence, no event
        header = bytes(
            [
                (protocol.PROTOCOL_VERSION << 4) | 0x01,
                (protocol.SERVER_ACK << 4) | protocol.NO_SEQUENCE,  # type + flags
                (protocol.JSON << 4) | protocol.NO_COMPRESSION,
                0x00,
            ]
        )

        session_id = b"session456"
        test_data = json.dumps({"status": "ok"}).encode("utf-8")
        payload = (
            len(session_id).to_bytes(4, "big", signed=True)
            + session_id
            + len(test_data).to_bytes(4, "big")
            + test_data
        )
        response = header + payload

        result = protocol.parse_response(response)
        self.assertEqual(result["message_type"], "SERVER_ACK")
        self.assertNotIn("seq", result)
        self.assertNotIn("event", result)
        self.assertEqual(result["session_id"], "b'session456'")
        self.assertEqual(result["payload_msg"], {"status": "ok"})

    def test_parse_response_server_error(self):
        """Test parse_response with SERVER_ERROR_RESPONSE"""
        header = bytes(
            [
                (protocol.PROTOCOL_VERSION << 4) | 0x01,
                (protocol.SERVER_ERROR_RESPONSE << 4) | 0x00,
                (protocol.JSON << 4) | protocol.NO_COMPRESSION,
                0x00,
            ]
        )

        error_code = 404
        error_msg = json.dumps({"error": "Not found"}).encode("utf-8")
        payload = (
            error_code.to_bytes(4, "big")
            + len(error_msg).to_bytes(4, "big")
            + error_msg
        )
        response = header + payload

        result = protocol.parse_response(response)
        self.assertEqual(result["code"], error_code)
        self.assertEqual(result["payload_msg"], {"error": "Not found"})
        self.assertEqual(result["payload_size"], len(error_msg))

    def test_parse_response_no_serialization(self):
        """Test parse_response with NO_SERIALIZATION"""
        header = bytes(
            [
                (protocol.PROTOCOL_VERSION << 4) | 0x01,
                (protocol.SERVER_FULL_RESPONSE << 4) | 0x00,
                (protocol.NO_SERIALIZATION << 4) | protocol.NO_COMPRESSION,
                0x00,
            ]
        )

        session_id = b"session456"
        test_data = b"raw binary data"
        payload = (
            len(session_id).to_bytes(4, "big", signed=True)
            + session_id
            + len(test_data).to_bytes(4, "big")
            + test_data
        )
        response = header + payload

        result = protocol.parse_response(response)
        self.assertEqual(result["payload_msg"], test_data)


if __name__ == "__main__":
    unittest.main()
