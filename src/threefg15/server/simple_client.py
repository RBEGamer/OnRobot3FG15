#!/usr/bin/env python3
"""
Minimal Modbus TCP client to verify connection to simple_modbus_server.

Usage:
  python -m threefg15.server.simple_client --host 127.0.0.1 --port 15020
"""

import argparse
from typing import List, Optional
from pymodbus.client import ModbusTcpClient


def parse_args():
    p = argparse.ArgumentParser(description="Simple Modbus TCP client connectivity + write HR")
    p.add_argument("--host", default="127.0.0.1", help="Server host (default: 127.0.0.1)")
    p.add_argument("--port", type=int, default=15020, help="Server port (default: 15020)")
    p.add_argument("--unit", type=int, default=1, help="Modbus unit id (default: 1)")
    p.add_argument("--addr-hr", type=int, default=0, help="Holding register address for writes (default: 0)")
    p.add_argument("--write-hr", type=int, help="Write single holding register (FC6) value")
    p.add_argument("--write-hrs", type=str, help="Write multiple holding registers (FC16) as comma-separated list, e.g. 10,20,30")
    # Unified open/close coil support
    p.add_argument("--oc-coil", type=int, help="Unified open/close coil index (1=open, 0=close)")
    p.add_argument("--oc-value", type=int, choices=[0,1], help="Value to write to --oc-coil (1=open, 0=close)")
    p.add_argument("--status-coil", type=int, help="Read this coil as status after write (e.g., READY)")
    p.add_argument("--pulse-delay", type=float, default=0.0, help="Optional delay after open pulse before reading status")
    return p.parse_args()


def _parse_multi(values: Optional[str]) -> Optional[List[int]]:
    if not values:
        return None
    parts = [s.strip() for s in values.split(',') if s.strip()]
    return [max(0, min(0xFFFF, int(p))) for p in parts]


def main():
    args = parse_args()
    client = ModbusTcpClient(host=args.host, port=args.port)
    ok = client.connect()
    print(f"Connect to {args.host}:{args.port}: {'OK' if ok else 'FAILED'}")

    if not ok:
        return

    try:
        unit = args.unit

        # Optional writes to holding registers
        if args.write_hr is not None:
            val = max(0, min(0xFFFF, int(args.write_hr)))
            print(f"Writing HR[{args.addr_hr}] = {val}")
            try:
                wr = client.write_register(args.addr_hr, val, slave=unit)
            except TypeError:
                wr = client.write_register(args.addr_hr, val, unit=unit)
            print(f"Write single HR resp: {wr}")

        multi_vals = _parse_multi(args.write_hrs)
        if multi_vals:
            print(f"Writing HRs starting at {args.addr_hr}: {multi_vals}")
            try:
                wrr = client.write_registers(args.addr_hr, multi_vals, slave=unit)
            except TypeError:
                wrr = client.write_registers(args.addr_hr, multi_vals, unit=unit)
            print(f"Write multiple HR resp: {wrr}")

        # Optional unified open/close coil write and read status
        if args.oc_coil is not None and args.oc_value is not None:
            val = bool(args.oc_value)
            action = "OPEN" if val else "CLOSE"
            print(f"Writing OC coil {args.oc_coil} = {args.oc_value} ({action})")
            try:
                wco = client.write_coil(args.oc_coil, val, slave=unit)
            except TypeError:
                wco = client.write_coil(args.oc_coil, val, unit=unit)
            print(f"Write OC coil resp: {wco}")
            if args.pulse_delay > 0:
                import time as _t
                _t.sleep(args.pulse_delay)
            if args.status_coil is not None:
                try:
                    rco = client.read_coils(args.status_coil, count=1, slave=unit)
                except TypeError:
                    rco = client.read_coils(args.status_coil, count=1, unit=unit)
                print(f"Status coil[{args.status_coil}] -> {rco.bits[0] if rco and hasattr(rco, 'bits') else rco}")

        # Simple read of 1 coil and holding registers for verification
        try:
            rc = client.read_coils(0, count=1, slave=unit)
        except TypeError:
            rc = client.read_coils(0, count=1, unit=unit)
        print(f"Read Coils: {rc if rc else 'None'}")

        # Read back the just-written holding registers
        try:
            rr = client.read_holding_registers(args.addr_hr, count=max(1, len(multi_vals) if multi_vals else 1), slave=unit)
        except TypeError:
            rr = client.read_holding_registers(args.addr_hr, count=max(1, len(multi_vals) if multi_vals else 1), unit=unit)
        print(f"Read HR(s) from {args.addr_hr}: {rr if rr else 'None'}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
