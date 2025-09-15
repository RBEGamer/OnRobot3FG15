#!/usr/bin/env python3
"""
Test client to open/close the 3FG15 gripper in a loop via the simple Modbus server.

- Uses single open/close command coil (1 = open, 0 = close)
- Uses holding register for force
- Waits for READY and OPEN/CLOSED status before continuing

Example:
  python -m threefg15.server.test_open_close \
    --host 127.0.0.1 --port 15020 \
    --force 600 --loops 5 --timeout 15 --poll 0.1 \
    --open-coil 0 --status-ready 2 --status-open 3 --status-closed 4 --status-grip 5 --ir-width 0
"""

import time
import argparse
from typing import Optional
from pymodbus.client import ModbusTcpClient


# Default mappings to simple_modbus_server
REG_TARGET_FORCE = 0  # HR index for force


def _mb_write_register(client, addr: int, val: int, unit: int):
    try:
        return client.write_register(addr, val, slave=unit)
    except TypeError:
        return client.write_register(addr, val, unit=unit)


def _mb_write_coil(client, addr: int, val: bool, unit: int):
    try:
        return client.write_coil(addr, bool(val), slave=unit)
    except TypeError:
        return client.write_coil(addr, bool(val), unit=unit)


def _mb_read_coils(client, addr: int, count: int, unit: int):
    try:
        return client.read_coils(addr, count=count, slave=unit)
    except TypeError:
        return client.read_coils(addr, count=count, unit=unit)


def _mb_read_input_registers(client, addr: int, count: int, unit: int):
    try:
        return client.read_input_registers(addr, count=count, slave=unit)
    except TypeError:
        return client.read_input_registers(addr, count=count, unit=unit)


def assert_ok(resp, what: str):
    if not resp or resp.isError():
        raise RuntimeError(f"{what} failed: {resp}")


def wait_for_coil(client, idx: int, value: bool, unit: int, timeout: float, poll: float, label: str = "") -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        rc = _mb_read_coils(client, idx, 1, unit)
        if rc and not rc.isError() and hasattr(rc, 'bits'):
            if bool(rc.bits[0]) == bool(value):
                return True
        time.sleep(poll)
    print(f"Timeout waiting for coil[{idx}]={value} {label}")
    return False


def parse_args():
    p = argparse.ArgumentParser(description="Loop open/close test for 3FG15 simple Modbus server")
    p.add_argument("--host", default="127.0.0.1", help="Server host (default: 127.0.0.1)")
    p.add_argument("--port", type=int, default=15020, help="Server port (default: 15020)")
    p.add_argument("--unit", type=int, default=1, help="Modbus unit/slave id (default: 1)")
    p.add_argument("--force", type=int, default=500, help="Target force 0-1000 (default: 500)")
    p.add_argument("--loops", type=int, default=5, help="Open/close loops (default: 5)")
    p.add_argument("--timeout", type=float, default=15.0, help="Per-action timeout seconds (default: 15)")
    p.add_argument("--poll", type=float, default=0.1, help="Polling interval seconds (default: 0.1)")
    # Mappings
    p.add_argument("--open-coil", type=int, default=0, help="Unified open/close command coil (1=open, 0=close) (default: 0)")
    p.add_argument("--status-ready", type=int, default=2, help="READY status coil index (default: 2)")
    p.add_argument("--status-open", type=int, default=3, help="OPEN status coil index (default: 3)")
    p.add_argument("--status-closed", type=int, default=4, help="CLOSED status coil index (default: 4)")
    p.add_argument("--status-grip", type=int, default=5, help="OBJECT GRIPPED status coil index (default: 5)")
    p.add_argument("--ir-width", type=int, default=0, help="Input register index for current width 0.1mm (default: 0)")
    return p.parse_args()


def print_status(client, unit: int, args):
    # Read status coils
    rc_ready = _mb_read_coils(client, args.status_ready, 1, unit)
    rc_open = _mb_read_coils(client, args.status_open, 1, unit)
    rc_closed = _mb_read_coils(client, args.status_closed, 1, unit)
    rc_grip = _mb_read_coils(client, args.status_grip, 1, unit)
    ready = bool(rc_ready.bits[0]) if rc_ready and hasattr(rc_ready, 'bits') else None
    is_open = bool(rc_open.bits[0]) if rc_open and hasattr(rc_open, 'bits') else None
    is_closed = bool(rc_closed.bits[0]) if rc_closed and hasattr(rc_closed, 'bits') else None
    gripped = bool(rc_grip.bits[0]) if rc_grip and hasattr(rc_grip, 'bits') else None
    # Read current width
    rrw = _mb_read_input_registers(client, args.ir_width, 1, unit)
    width = rrw.registers[0] if rrw and hasattr(rrw, 'registers') else None
    print(f"Status: ready={ready} open={is_open} closed={is_closed} gripped={gripped} width(0.1mm)={width}")


def main():
    args = parse_args()
    client = ModbusTcpClient(host=args.host, port=args.port)
    if not client.connect():
        raise SystemExit(f"Could not connect to server at {args.host}:{args.port}")

    try:
        print(f"Connected to {args.host}:{args.port}")
        unit = args.unit

        # Clamp and write force
        force = max(0, min(1000, int(args.force)))
        print(f"Writing target force HR[{REG_TARGET_FORCE}] = {force}")
        resp = _mb_write_register(client, REG_TARGET_FORCE, force, unit)
        assert_ok(resp, "write force")

        # Loop open/close
        for i in range(args.loops):
            print(f"\nLoop {i+1}/{args.loops}: OPEN")
            resp = _mb_write_coil(client, args.open_coil, True, unit)
            assert_ok(resp, "write open coil = 1")
            # Wait for ready and open status
            wait_for_coil(client, args.status_ready, True, unit, args.timeout, args.poll, label="(ready after open)")
            wait_for_coil(client, args.status_open, True, unit, args.timeout, args.poll, label="(open status)")
            print_status(client, unit, args)

            print(f"Loop {i+1}/{args.loops}: CLOSE")
            resp = _mb_write_coil(client, args.open_coil, False, unit)
            assert_ok(resp, "write open coil = 0 (close)")
            # Wait for ready and closed status
            wait_for_coil(client, args.status_ready, True, unit, args.timeout, args.poll, label="(ready after close)")
            wait_for_coil(client, args.status_closed, True, unit, args.timeout, args.poll, label="(closed status)")
            print_status(client, unit, args)

        print("\nDone.")
    finally:
        client.close()


if __name__ == "__main__":
    main()
