"""Strip the COSMOS5/OpenC3 packet-log wrapper from a raw log, leaving plain CCSDS packets.

Format: https://docs.openc3.com/docs/development/log-structure
"""

import argparse
import struct
from collections import Counter

MAGIC = b"COSMOS5_"
RAW_PACKET = 3


def iter_raw_packets(data):
    """Yield (packet_name, packet_bytes) for every Raw Packet entry in a COSMOS5 log."""
    if data[: len(MAGIC)] != MAGIC:
        raise ValueError(f"Not a COSMOS5 log, starts with {data[:8]!r}")
    pos = len(MAGIC)
    packet_names = []
    while pos + 4 <= len(data):
        (length,) = struct.unpack(">I", data[pos : pos + 4])
        entry = data[pos + 4 : pos + 4 + length]
        pos += 4 + length
        if len(entry) < length:
            print("Warning: log is truncated at the tail, stopping.")
            return

        # Flags are 2 bytes: byte 0 = type(4) cmd(1) stored(1) id(1) cbor(1),
        #                    byte 1 = extra(1) received_time(1) reserved(6)
        entry_type = entry[0] >> 4
        has_id = (entry[0] >> 1) & 1
        has_extra = (entry[1] >> 7) & 1
        has_received_time = (entry[1] >> 6) & 1
        body_end = len(entry) - 32 if has_id else len(entry)  # optional trailing SHA-256

        if entry_type == 2:  # packet declaration: target index (2) + name
            packet_names.append(entry[4:body_end].decode("ascii"))
        elif entry_type == RAW_PACKET:
            (packet_index,) = struct.unpack(">H", entry[2:4])
            offset = 4 + 8  # packet index, then 64-bit packet timestamp
            if has_received_time:
                offset += 8
            if has_extra:
                offset += 4 + struct.unpack(">I", entry[offset : offset + 4])[0]
            yield packet_names[packet_index], entry[offset:body_end]


def strip_cosmos(input_path, output_path, apids=None):
    with open(input_path, "rb") as fh:
        data = fh.read()

    kept = Counter()
    seen = Counter()
    with open(output_path, "wb") as out:
        for name, packet in iter_raw_packets(data):
            apid = struct.unpack(">H", packet[:2])[0] & 0x07FF
            expected_len = struct.unpack(">H", packet[4:6])[0] + 7
            if expected_len != len(packet):
                raise ValueError(
                    f"{name}: CCSDS header says {expected_len} bytes but entry holds {len(packet)}"
                )
            seen[(name, apid)] += 1
            if apids is None or apid in apids:
                out.write(packet)
                kept[apid] += 1

    print(f"Packets in log (name, apid): {dict(seen)}")
    print(f"Wrote {sum(kept.values())} packets to {output_path}: {dict(kept)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input")
    parser.add_argument("output")
    parser.add_argument(
        "--apid",
        type=int,
        nargs="*",
        default=[260, 265],
        help="APIDs to keep (default: 260 265). Pass --apid with no values to keep all.",
    )
    args = parser.parse_args()
    strip_cosmos(args.input, args.output, set(args.apid) or None)
