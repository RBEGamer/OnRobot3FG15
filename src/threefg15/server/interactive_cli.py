#!/usr/bin/env python3
"""
Interactive CLI to control the simple Modbus server.

Prompts for commands to open/close the gripper, set force, and read status.

Usage:
  python -m threefg15.server.interactive_cli --host 127.0.0.1 --port 15020

Commands:
  open                    -> write 1 to unified OC coil; waits until READY
  close                   -> write 0 to unified OC coil; waits until READY
  force <0-1000>          -> set HR force; reads back
  diam <value(0.1mm)>     -> set HR diameter; reads back
  griptype <0|1|ext|int>  -> set HR grip type; reads back
  move                    -> pulse MOVE coil (uses HR force/diam/griptype), waits READY
  flex                    -> pulse FLEXGRIP coil (uses HR force/diam/griptype), waits READY
  stop                    -> pulse STOP coil
  status                  -> print READY/OPEN/CLOSED/GRIPPED and width (0.1mm)
  help                    -> show this help
  quit / exit             -> leave
"""

import argparse
import sys
import time
from typing import Optional

from pymodbus.client import ModbusTcpClient


def _wr_hr(client, addr: int, val: int, unit: int):
    try:
        return client.write_register(addr, val, slave=unit)
    except TypeError:
        return client.write_register(addr, val, unit=unit)


def _rd_hr(client, addr: int, count: int, unit: int):
    try:
        return client.read_holding_registers(addr, count=count, slave=unit)
    except TypeError:
        return client.read_holding_registers(addr, count=count, unit=unit)


def _wr_coil(client, addr: int, val: bool, unit: int):
    try:
        return client.write_coil(addr, bool(val), slave=unit)
    except TypeError:
        return client.write_coil(addr, bool(val), unit=unit)


def _rd_coils(client, addr: int, count: int, unit: int):
    try:
        return client.read_coils(addr, count=count, slave=unit)
    except TypeError:
        return client.read_coils(addr, count=count, unit=unit)


def _rd_ir(client, addr: int, count: int, unit: int):
    try:
        return client.read_input_registers(addr, count=count, slave=unit)
    except TypeError:
        return client.read_input_registers(addr, count=count, unit=unit)


def wait_for_coil(client, idx: int, value: bool, unit: int, timeout: float, poll: float, label: str = "") -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        rc = _rd_coils(client, idx, 1, unit)
        if rc and not rc.isError() and hasattr(rc, 'bits'):
            if bool(rc.bits[0]) == bool(value):
                return True
        time.sleep(poll)
    print(f"Timeout waiting for coil[{idx}]={value} {label}")
    return False


def print_status(client, unit: int, ready_idx: int, open_idx: int, closed_idx: int, gripped_idx: int, width_ir: int):
    rc_ready = _rd_coils(client, ready_idx, 1, unit)
    rc_open = _rd_coils(client, open_idx, 1, unit)
    rc_closed = _rd_coils(client, closed_idx, 1, unit)
    rc_grip = _rd_coils(client, gripped_idx, 1, unit)
    rrw = _rd_ir(client, width_ir, 1, unit)
    ready = bool(rc_ready.bits[0]) if rc_ready and hasattr(rc_ready, 'bits') else None
    is_open = bool(rc_open.bits[0]) if rc_open and hasattr(rc_open, 'bits') else None
    is_closed = bool(rc_closed.bits[0]) if rc_closed and hasattr(rc_closed, 'bits') else None
    gripped = bool(rc_grip.bits[0]) if rc_grip and hasattr(rc_grip, 'bits') else None
    width = rrw.registers[0] if rrw and hasattr(rrw, 'registers') else None
    print(f"Status => ready={ready} open={is_open} closed={is_closed} gripped={gripped} width(0.1mm)={width}")


def parse_args():
    p = argparse.ArgumentParser(description="Interactive CLI for simple Modbus server")
    p.add_argument("--host", default="127.0.0.1", help="Server host (default: 127.0.0.1)")
    p.add_argument("--port", type=int, default=15020, help="Server port (default: 15020)")
    p.add_argument("--unit", type=int, default=1, help="Modbus unit/slave id (default: 1)")
    p.add_argument("--timeout", type=float, default=15.0, help="Wait timeout seconds (default: 15)")
    p.add_argument("--poll", type=float, default=0.1, help="Polling interval seconds (default: 0.1)")
    # Mapping
    p.add_argument("--force-index", type=int, default=0, help="Holding register index for force (default: 0)")
    p.add_argument("--diameter-index", type=int, default=1, help="Holding register index for diameter 0.1mm (default: 1)")
    p.add_argument("--griptype-index", type=int, default=2, help="Holding register index for grip type 0=ext,1=int (default: 2)")
    p.add_argument("--oc-coil", type=int, default=0, help="Unified open/close coil index (default: 0)")
    p.add_argument("--move-coil", type=int, default=-1, help="MOVE command coil index; -1 to disable (default: -1)")
    p.add_argument("--flex-coil", type=int, default=-1, help="FLEXGRIP command coil index; -1 to disable (default: -1)")
    p.add_argument("--stop-coil", type=int, default=-1, help="STOP command coil index; -1 to disable (default: -1)")
    p.add_argument("--ready-coil", type=int, default=2, help="READY status coil index (default: 2)")
    p.add_argument("--open-coil", type=int, default=3, help="OPEN status coil index (default: 3)")
    p.add_argument("--closed-coil", type=int, default=4, help="CLOSED status coil index (default: 4)")
    p.add_argument("--gripped-coil", type=int, default=5, help="GRIPPED status coil index (default: 5)")
    p.add_argument("--width-index", type=int, default=0, help="Input register index for width 0.1mm (default: 0)")
    return p.parse_args()


HELP_TEXT = (
    "Commands:\n"
    "  open               -> open gripper (waits for READY)\n"
    "  close              -> close gripper (waits for READY)\n"
    "  force <0-1000>     -> set force HR and read back\n"
    "  diam <value>       -> set diameter HR (0.1mm) and read back\n"
    "  griptype <0|1|ext|int> -> set grip type HR and read back\n"
    "  move               -> pulse MOVE coil\n"
    "  flex               -> pulse FLEXGRIP coil\n"
    "  stop               -> pulse STOP coil\n"
    "  status             -> read READY/OPEN/CLOSED/GRIPPED and width\n"
    "  help               -> this help\n"
    "  quit | exit        -> leave\n"
)


def main():
    args = parse_args()
    client = ModbusTcpClient(host=args.host, port=args.port)
    if not client.connect():
        raise SystemExit(f"Could not connect to server at {args.host}:{args.port}")

    unit = args.unit
    print("Interactive CLI connected. Type 'help' for commands.")
    try:
        while True:
            try:
                line = input(
                    f"[{args.host}:{args.port} u={unit}] (open/close/force N/status/help/quit)> "
                ).strip()
            except EOFError:
                print()
                break
            if not line:
                continue
            parts = line.split()
            cmd = parts[0].lower()

            if cmd in ("quit", "exit"):
                break
            elif cmd == "help":
                print(HELP_TEXT)
            elif cmd == "status":
                print_status(
                    client,
                    unit,
                    args.ready_coil,
                    args.open_coil,
                    args.closed_coil,
                    args.gripped_coil,
                    args.width_index,
                )
            elif cmd == "force":
                if len(parts) < 2:
                    print("Usage: force <0-1000>")
                    continue
                try:
                    val = int(parts[1])
                except ValueError:
                    print("Invalid number.")
                    continue
                val = max(0, min(1000, val))
                r = _wr_hr(client, args.force_index, val, unit)
                rb = _rd_hr(client, args.force_index, 1, unit)
                print(f"Force set resp={r}, readback={rb.registers[0] if rb and hasattr(rb,'registers') else rb}")
            elif cmd == "diam":
                if len(parts) < 2:
                    print("Usage: diam <value (0.1mm)>")
                    continue
                try:
                    val = int(parts[1])
                except ValueError:
                    print("Invalid number.")
                    continue
                r = _wr_hr(client, args.diameter_index, val, unit)
                rb = _rd_hr(client, args.diameter_index, 1, unit)
                print(f"Diameter set resp={r}, readback={rb.registers[0] if rb and hasattr(rb,'registers') else rb}")
            elif cmd == "griptype":
                if len(parts) < 2:
                    print("Usage: griptype <0|1|ext|int>")
                    continue
                raw = parts[1].lower()
                if raw in ("0", "ext", "external"):
                    val = 0
                elif raw in ("1", "int", "internal"):
                    val = 1
                else:
                    print("Invalid griptype; use 0/1/ext/int")
                    continue
                r = _wr_hr(client, args.griptype_index, val, unit)
                rb = _rd_hr(client, args.griptype_index, 1, unit)
                print(f"GripType set resp={r}, readback={rb.registers[0] if rb and hasattr(rb,'registers') else rb}")
            elif cmd == "open":
                r = _wr_coil(client, args.oc_coil, True, unit)
                print(f"Open resp={r}")
                wait_for_coil(client, args.ready_coil, True, unit, args.timeout, args.poll, "(ready)")
                print_status(
                    client,
                    unit,
                    args.ready_coil,
                    args.open_coil,
                    args.closed_coil,
                    args.gripped_coil,
                    args.width_index,
                )
            elif cmd == "close":
                r = _wr_coil(client, args.oc_coil, False, unit)
                print(f"Close resp={r}")
                wait_for_coil(client, args.ready_coil, True, unit, args.timeout, args.poll, "(ready)")
                print_status(
                    client,
                    unit,
                    args.ready_coil,
                    args.open_coil,
                    args.closed_coil,
                    args.gripped_coil,
                    args.width_index,
                )
            elif cmd == "move":
                if args.move_coil < 0:
                    print("MOVE coil not configured (--move-coil)")
                    continue
                r = _wr_coil(client, args.move_coil, True, unit)
                print(f"Move resp={r}")
                wait_for_coil(client, args.ready_coil, True, unit, args.timeout, args.poll, "(ready after move)")
                print_status(
                    client,
                    unit,
                    args.ready_coil,
                    args.open_coil,
                    args.closed_coil,
                    args.gripped_coil,
                    args.width_index,
                )
            elif cmd == "flex":
                if args.flex_coil < 0:
                    print("FLEX coil not configured (--flex-coil)")
                    continue
                r = _wr_coil(client, args.flex_coil, True, unit)
                print(f"Flex resp={r}")
                wait_for_coil(client, args.ready_coil, True, unit, args.timeout, args.poll, "(ready after flex)")
                print_status(
                    client,
                    unit,
                    args.ready_coil,
                    args.open_coil,
                    args.closed_coil,
                    args.gripped_coil,
                    args.width_index,
                )
            elif cmd == "stop":
                if args.stop_coil < 0:
                    print("STOP coil not configured (--stop-coil)")
                    continue
                r = _wr_coil(client, args.stop_coil, True, unit)
                print(f"Stop resp={r}")
            else:
                print("Unknown command. Type 'help' for commands.")
    except KeyboardInterrupt:
        print("\nBye")
    finally:
        client.close()


if __name__ == "__main__":
    main()
