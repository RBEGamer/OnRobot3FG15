#!/usr/bin/env python3
"""
Minimal Modbus TCP server that reads/writes coils and holding registers
backed by a simple Python class.

Usage:
  python -m threefg15.server.simple_modbus_server --host 127.0.0.1 --port 15020

Compatible with pymodbus ~= 3.0.0
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path
from typing import List, Optional


import yaml  # type: ignore

from pymodbus.datastore import (
    ModbusSlaveContext,
    ModbusSequentialDataBlock,
    ModbusServerContext,
)
from pymodbus.server import StartAsyncTcpServer


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("simple_modbus_server")

# Import gripper classes (RTU/TCP); default to RTU per request
try:
    from ..ThreeFG15 import ThreeFG15ModbusRTU, ThreeFG15ModbusTCP, ThreeFG15Simulator
    from ..GripperBase import GripType
except Exception:
    # Fallback for direct execution
    from threefg15.ThreeFG15 import ThreeFG15ModbusRTU, ThreeFG15ModbusTCP, ThreeFG15Simulator  # type: ignore
    from threefg15.GripperBase import GripType  # type: ignore


class SimpleDevice:
    """In-memory device backing for Modbus server.

    - coils: read/write booleans
    - holding registers: read/write 16-bit unsigned integers
    - discrete inputs + input registers are read-only mirrors for demo
    """

    def __init__(self, coils: int = 64, holding_registers: int = 128,
                 discrete_inputs: int = 64, input_registers: int = 128,
                 open_cmd_coil: int = 0, status_coil: int = 1):
        self._coils: List[bool] = [False] * coils
        self._hrs: List[int] = [0] * holding_registers
        self._dis: List[bool] = [False] * discrete_inputs
        self._irs: List[int] = [0] * input_registers
        # Simple action mapping: write True to open_cmd_coil to set status_coil True
        self._open_cmd_coil = int(open_cmd_coil)
        self._status_coil = int(status_coil)

    # Coils (rw)
    def get_coils(self, address: int, count: int) -> List[bool]:
        return [self._coils[address + i] for i in range(count)]

    def set_coils(self, address: int, values: List[bool]):
        for i, v in enumerate(values):
            idx = address + i
            self._coils[idx] = bool(v)
            # If this is the designated open command coil and it's set True, set status coil True
            if idx == self._open_cmd_coil and self._coils[idx]:
                if 0 <= self._status_coil < len(self._coils):
                    self._coils[self._status_coil] = True

    # Holding registers (rw)
    def get_holding_registers(self, address: int, count: int) -> List[int]:
        return [self._hrs[address + i] for i in range(count)]

    def set_holding_registers(self, address: int, values: List[int]):
        for i, v in enumerate(values):
            self._hrs[address + i] = int(v) & 0xFFFF

    # Discrete inputs (ro)
    def get_discrete_inputs(self, address: int, count: int) -> List[bool]:
        return [self._dis[address + i] for i in range(count)]

    # Input registers (ro)
    def get_input_registers(self, address: int, count: int) -> List[int]:
        return [self._irs[address + i] for i in range(count)]

    # Demo helpers to update read-only blocks
    def set_discrete_inputs(self, address: int, values: List[bool]):
        for i, v in enumerate(values):
            self._dis[address + i] = bool(v)

    def set_input_registers(self, address: int, values: List[int]):
        for i, v in enumerate(values):
            self._irs[address + i] = int(v) & 0xFFFF


class DelegatingDataBlock(ModbusSequentialDataBlock):
    """Datablock that proxies to the SimpleDevice implementation.

    block_type: 'co' | 'di' | 'hr' | 'ir'
    """

    def __init__(self, device: SimpleDevice, address: int, values: List[int], block_type: str):
        super().__init__(address, values)
        self.device = device
        self.block_type = block_type

    def getValues(self, address, count=1):  # noqa: N802 (pymodbus API)
        # Pymodbus sequential datablock calls here with 1-based address semantics.
        # Convert to 0-based indices for the device API.
        zaddr = max(0, int(address) - 1)
        if self.block_type == 'co':
            return self.device.get_coils(zaddr, count)
        if self.block_type == 'di':
            return self.device.get_discrete_inputs(zaddr, count)
        if self.block_type == 'hr':
            return self.device.get_holding_registers(zaddr, count)
        if self.block_type == 'ir':
            return self.device.get_input_registers(zaddr, count)
        return super().getValues(address, count)

    def setValues(self, address, values):  # noqa: N802 (pymodbus API)
        # Accept single scalar or list for FC5/FC6 and FC15/FC16
        if not isinstance(values, list):
            values = [values]

        # Convert to 0-based index for device
        zaddr = max(0, int(address) - 1)

        if self.block_type == 'co':
            # Normalize 0xFF00/0x0000, 1/0, True/False to bools
            norm = [bool(v == 0xFF00 or v == 1 or v is True) for v in values]
            try:
                log.info(f"COIL write @ {address} (z={zaddr}): {values} -> {norm}")
            except Exception:
                pass
            self.device.set_coils(zaddr, norm)
            # Store echo to backing so read-after-write works
            try:
                super().setValues(address, [1 if b else 0 for b in norm])
            except Exception:
                pass
            return

        if self.block_type == 'hr':
            norm = [int(v) & 0xFFFF for v in values]
            try:
                log.info(f"HR write @ {address} (z={zaddr}): {values} -> {norm}")
            except Exception:
                pass
            self.device.set_holding_registers(zaddr, norm)
            try:
                super().setValues(address, norm)
            except Exception:
                pass
            return

        # Read-only blocks (ignore writes)
        return


class GripperDevice(SimpleDevice):
    """Device backed by a real ThreeFG15 gripper over Modbus.

    Behavior:
      - HR[0]: target force (0-1000)
      - Coil[open_cmd_coil]: when set True, calls open_gripper(force=HR[0])
      - Coil[status_coil]: reads back gripper status (True when not busy and/or grip detected)
    """

    def __init__(
        self,
        gripper,
        open_cmd_coil: int = 0,
        status_coil: int = 1,
        close_cmd_coil: Optional[int] = None,
        move_cmd_coil: Optional[int] = None,
        flex_cmd_coil: Optional[int] = None,
        stop_cmd_coil: Optional[int] = None,
        status_open_coil: int = 3,
        status_closed_coil: int = 4,
        status_grip_coil: int = 5,
        hr_force_index: int = 0,
        hr_diameter_index: int = 1,
        hr_griptype_index: int = 2,
        hr_cmd_index: int = -1,
        ir_width_index: int = 0,
    ):
        super().__init__(open_cmd_coil=open_cmd_coil, status_coil=status_coil)
        self._gripper = gripper
        self._connected = False
        self._close_cmd_coil = int(close_cmd_coil) if close_cmd_coil is not None else None
        self._move_cmd_coil = int(move_cmd_coil) if move_cmd_coil is not None else None
        self._flex_cmd_coil = int(flex_cmd_coil) if flex_cmd_coil is not None else None
        self._stop_cmd_coil = int(stop_cmd_coil) if stop_cmd_coil is not None else None
        self._status_open_coil = int(status_open_coil)
        self._status_closed_coil = int(status_closed_coil)
        self._status_grip_coil = int(status_grip_coil)
        self._hr_force_index = int(hr_force_index)
        self._hr_diameter_index = int(hr_diameter_index)
        self._hr_griptype_index = int(hr_griptype_index)
        self._hr_cmd_index = int(hr_cmd_index) if hr_cmd_index is not None else -1
        self._ir_width_index = int(ir_width_index)
        # Cached geometry
        self._min_d = None  # 0.1 mm units
        self._max_d = None  # 0.1 mm units

    def connect(self) -> bool:
        try:
            self._connected = bool(self._gripper.open_connection())
            if self._connected:
                log.info("Connected to ThreeFG15 gripper")
                # Prime min/max diameters for open/closed decisions
                try:
                    md = self._gripper.read_registers(self._gripper.REG_MIN_DIAMETER, 1)
                    xd = self._gripper.read_registers(self._gripper.REG_MAX_DIAMETER, 1)
                    if md:
                        self._min_d = int(md[0])
                    if xd:
                        self._max_d = int(xd[0])
                    log.info(f"Gripper range (0.1mm): min={self._min_d} max={self._max_d}")
                except Exception as e:
                    log.warning(f"Could not read min/max diameter: {e}")
            else:
                log.error("Failed to connect to ThreeFG15 gripper")
            return self._connected
        except Exception as e:
            log.exception(f"Error connecting to gripper: {e}")
            self._connected = False
            return False

    def close(self):
        try:
            if self._connected:
                self._gripper.close_connection()
        finally:
            self._connected = False

    def set_coils(self, address: int, values: List[bool]):
        log.info(f"GripperDevice.set_coils(addr={address}, values={values}, oc_coil={self._open_cmd_coil}, close_coil={self._close_cmd_coil})")
        # Update in-memory coils WITHOUT changing status coils automatically
        for i, v in enumerate(values):
            idx = address + i
            if 0 <= idx < len(self._coils):
                self._coils[idx] = bool(v)
        # Map unified/separate command coils to real gripper actions
        for i, v in enumerate(values):
            idx = address + i
            if not self._connected:
                continue
            if idx == self._open_cmd_coil:
                force = int(self._hrs[self._hr_force_index]) if self._hrs else 500
                try:
                    if self._close_cmd_coil is None:
                        # Single coil semantics: True=open, False=close
                        if v:
                            self._wait_ready()
                            log.info(f"Trigger OPEN on gripper with force={force}")
                            self._gripper.open_gripper(force_val=force)
                        else:
                            self._wait_ready()
                            log.info(f"Trigger CLOSE on gripper with force={force}")
                            self._gripper.close_gripper(force_val=force)
                    else:
                        # Separate coils semantics: open only on True
                        if v:
                            self._wait_ready()
                            log.info(f"Trigger OPEN on gripper with force={force}")
                            self._gripper.open_gripper(force_val=force)
                except Exception as e:
                    log.error(f"Failed to actuate gripper (open/close via open coil): {e}")
            elif self._close_cmd_coil is not None and idx == self._close_cmd_coil and v:
                force = int(self._hrs[self._hr_force_index]) if self._hrs else 500
                try:
                    self._wait_ready()
                    log.info(f"Trigger CLOSE on gripper with force={force}")
                    self._gripper.close_gripper(force_val=force)
                except Exception as e:
                    log.error(f"Failed to close gripper: {e}")
            # set_force/set_diameter via coils removed; now applied on HR writes
            elif self._move_cmd_coil is not None and idx == self._move_cmd_coil and v:
                # Move to diameter using HR diameter and grip type
                force = int(self._hrs[self._hr_force_index]) if self._hrs else 500
                diameter = int(self._hrs[self._hr_diameter_index]) if self._hrs else 100
                gtv = int(self._hrs[self._hr_griptype_index]) if self._hrs else 0
                # Clamp diameter
                if self._min_d is not None:
                    diameter = max(self._min_d, diameter)
                if self._max_d is not None:
                    diameter = min(self._max_d, diameter)
                grip_type = GripType.INTERNAL if gtv == GripType.INTERNAL.value else GripType.EXTERNAL
                try:
                    self._wait_ready()
                    log.info(f"Trigger MOVE diameter={diameter} force={force} grip_type={grip_type.name}")
                    self._gripper.move_gripper(diameter, force_val=force, grip_type=grip_type)
                except Exception as e:
                    log.error(f"Failed to move gripper: {e}")
            elif self._flex_cmd_coil is not None and idx == self._flex_cmd_coil and v:
                # Flex grip with diameter and grip type
                force = int(self._hrs[self._hr_force_index]) if self._hrs else 100
                diameter = int(self._hrs[self._hr_diameter_index]) if self._hrs else 100
                gtv = int(self._hrs[self._hr_griptype_index]) if self._hrs else 1
                if self._min_d is not None:
                    diameter = max(self._min_d, diameter)
                if self._max_d is not None:
                    diameter = min(self._max_d, diameter)
                grip_type = GripType.INTERNAL if gtv == GripType.INTERNAL.value else GripType.EXTERNAL
                try:
                    self._wait_ready()
                    log.info(f"Trigger FLEXGRIP diameter={diameter} force={force} grip_type={grip_type.name}")
                    self._gripper.flex_grip(diameter, force_val=force, grip_type=grip_type)
                except Exception as e:
                    log.error(f"Failed to flexgrip: {e}")
            elif self._stop_cmd_coil is not None and idx == self._stop_cmd_coil and v:
                try:
                    log.info("Trigger STOP")
                    self._gripper.set_control(self._gripper.CMD_STOP)
                except Exception as e:
                    log.error(f"Failed to stop gripper: {e}")

    def get_coils(self, address: int, count: int) -> List[bool]:
        # For status coil, fetch a live status from the gripper
        out = super().get_coils(address, count)
        try:
            for i in range(count):
                idx = address + i
                if not self._connected:
                    continue
                st = self._gripper.get_status()
                # compute status bits
                grip = False
                busy = True
                if st is not None:
                    grip = bool(getattr(st, 'grip_detected', False) or getattr(st, 'force_grip_detected', False))
                    busy = bool(getattr(st, 'busy', True))
                # current diameter (0.1mm)
                cur_d = None
                try:
                    raw_mm = self._gripper.get_raw_diameter()
                    if raw_mm is not None:
                        cur_d = int(round(raw_mm * 10))
                except Exception:
                    pass
                # thresholds for open/closed
                open_bit = False
                closed_bit = False
                if cur_d is not None:
                    if self._max_d is not None:
                        open_bit = cur_d >= (self._max_d - 5)  # 0.5mm tolerance
                    if self._min_d is not None:
                        closed_bit = cur_d <= (self._min_d + 5)  # 0.5mm tolerance

                # Map to requested coil indices
                if idx == self._status_coil:
                    out[i] = not busy
                elif idx == self._status_grip_coil:
                    out[i] = grip
                elif idx == self._status_open_coil:
                    out[i] = open_bit
                elif idx == self._status_closed_coil:
                    out[i] = closed_bit
        except Exception as e:
            log.debug(f"Status read failed: {e}")
        return out

    def get_input_registers(self, address: int, count: int) -> List[int]:
        out = super().get_input_registers(address, count)
        if not self._connected:
            return out
        try:
            for i in range(count):
                idx = address + i
                if idx == self._ir_width_index:
                    raw_mm = self._gripper.get_raw_diameter()
                    if raw_mm is not None:
                        val = int(round(raw_mm * 10))  # 0.1mm units
                        out[i] = val
                        # mirror into backing so subsequent reads match
                        if 0 <= idx < len(self._irs):
                            self._irs[idx] = val
        except Exception as e:
            log.debug(f"IR width read failed: {e}")
        return out

    def set_holding_registers(self, address: int, values: List[int]):
        """Apply force/diameter/griptype when their HRs are written."""
        super().set_holding_registers(address, values)
        if not self._connected:
            return
        try:
            changed = {address + i for i in range(len(values))}
            # Apply force
            if self._hr_force_index in changed and 0 <= self._hr_force_index < len(self._hrs):
                force = int(self._hrs[self._hr_force_index])
                try:
                    log.info(f"Apply target FORCE={force}")
                    self._gripper.set_target_force(force)
                except Exception as e:
                    log.error(f"Failed to set force: {e}")
            # Apply diameter/grip type
            if (
                (self._hr_diameter_index in changed or self._hr_griptype_index in changed)
                and 0 <= self._hr_diameter_index < len(self._hrs)
                and 0 <= self._hr_griptype_index < len(self._hrs)
            ):
                diameter = int(self._hrs[self._hr_diameter_index])
                if self._min_d is not None:
                    diameter = max(self._min_d, diameter)
                if self._max_d is not None:
                    diameter = min(self._max_d, diameter)
                gtv = int(self._hrs[self._hr_griptype_index])
                grip_type = GripType.INTERNAL if gtv == GripType.INTERNAL.value else GripType.EXTERNAL
                try:
                    log.info(f"Apply target DIAMETER={diameter} GRIPTYPE={grip_type.name}")
                    self._gripper.set_target_diameter(diameter)
                    self._gripper.set_grip_type(grip_type)
                except Exception as e:
                    log.error(f"Failed to set diameter/griptype: {e}")
            # Handle command register to trigger actions
            if self._hr_cmd_index >= 0 and self._hr_cmd_index in changed and 0 <= self._hr_cmd_index < len(self._hrs):
                cmd = int(self._hrs[self._hr_cmd_index])
                try:
                    force = int(self._hrs[self._hr_force_index]) if 0 <= self._hr_force_index < len(self._hrs) else 500
                    diameter = int(self._hrs[self._hr_diameter_index]) if 0 <= self._hr_diameter_index < len(self._hrs) else 100
                    if self._min_d is not None:
                        diameter = max(self._min_d, diameter)
                    if self._max_d is not None:
                        diameter = min(self._max_d, diameter)
                    gtv = int(self._hrs[self._hr_griptype_index]) if 0 <= self._hr_griptype_index < len(self._hrs) else 0
                    grip_type = GripType.INTERNAL if gtv == GripType.INTERNAL.value else GripType.EXTERNAL
                    if cmd == 1:  # MOVE
                        self._wait_ready()
                        log.info(f"CMD MOVE diameter={diameter} force={force} grip_type={grip_type.name}")
                        self._gripper.move_gripper(diameter, force_val=force, grip_type=grip_type)
                    elif cmd == 2:  # FLEX
                        self._wait_ready()
                        log.info(f"CMD FLEX diameter={diameter} force={force} grip_type={grip_type.name}")
                        self._gripper.flex_grip(diameter, force_val=force, grip_type=grip_type)
                    elif cmd == 3:  # STOP
                        log.info("CMD STOP")
                        self._gripper.set_control(self._gripper.CMD_STOP)
                    elif cmd == 4:  # OPEN
                        self._wait_ready()
                        log.info(f"CMD OPEN force={force}")
                        self._gripper.open_gripper(force_val=force)
                    elif cmd == 5:  # CLOSE
                        self._wait_ready()
                        log.info(f"CMD CLOSE force={force}")
                        self._gripper.close_gripper(force_val=force)
                except Exception as e:
                    log.error(f"Failed to handle cmd register ({cmd}): {e}")
                # Clear command register to 0 after handling
                try:
                    self._hrs[self._hr_cmd_index] = 0
                    super().set_holding_registers(self._hr_cmd_index, [0])
                except Exception:
                    pass
        except Exception as e:
            log.debug(f"HR write handling failed: {e}")

    def _is_busy(self) -> bool:
        try:
            st = self._gripper.get_status()
            if st is None:
                return False
            return bool(getattr(st, 'busy', False))
        except Exception:
            return False

    def _wait_ready(self, timeout: float = 10.0, poll: float = 0.1) -> bool:
        import time as _t
        t0 = _t.time()
        while _t.time() - t0 < timeout:
            if not self._is_busy():
                return True
            _t.sleep(poll)
        log.warning("Timeout waiting for gripper to become ready (busy=false)")
        return False


async def run_server(host: str, port: int,
                     open_coil: int, status_coil: int,
                     close_coil: int,
                     move_coil: int,
                     flex_coil: int,
                     stop_coil: int,
                     status_open_coil: int,
                     status_closed_coil: int,
                     status_grip_coil: int,
                     hr_force_index: int,
                     hr_diameter_index: int,
                     hr_griptype_index: int,
                     hr_cmd_index: int,
                     ir_width_index: int,
                     mode: str, serial_port: Optional[str], slave_addr: int,
                     tcp_ip: Optional[str], tcp_port: int):
    # Create gripper instance based on mode
    if mode == 'rtu':
        if not serial_port:
            raise RuntimeError("serial_port is required for RTU mode")
        gripper = ThreeFG15ModbusRTU(serial_port=serial_port, slave_addr=slave_addr)

    elif mode == 'tcp':
        if not tcp_ip:
            raise RuntimeError("ip is required for TCP mode")
        gripper = ThreeFG15ModbusTCP(ip=tcp_ip, port=tcp_port, slave_addr=slave_addr)
    elif mode in ('sim', 'simulator'):
        gripper = ThreeFG15Simulator(simulation_speed=2.0, enable_noise=True)
    else:
        raise RuntimeError("Unsupported mode; use 'rtu', 'tcp' or 'sim'")
    gripper.open_connection()  # Pre-open to catch errors early
    #gripper.open_gripper(force_val=500)
    # Interpret negative close_coil as "single open/close coil"
    close_coil_opt: Optional[int] = None if close_coil is None or close_coil < 0 else close_coil

    device = GripperDevice(
        gripper,
        open_cmd_coil=open_coil,
        status_coil=status_coil,
        close_cmd_coil=close_coil_opt,
        move_cmd_coil=(None if move_coil is None or move_coil < 0 else move_coil),
        flex_cmd_coil=(None if flex_coil is None or flex_coil < 0 else flex_coil),
        stop_cmd_coil=(None if stop_coil is None or stop_coil < 0 else stop_coil),
        status_open_coil=status_open_coil,
        status_closed_coil=status_closed_coil,
        status_grip_coil=status_grip_coil,
        hr_force_index=hr_force_index,
        hr_diameter_index=hr_diameter_index,
        hr_griptype_index=hr_griptype_index,
        hr_cmd_index=hr_cmd_index,
        ir_width_index=ir_width_index,
    )
    if not device.connect():
        log.error("Could not connect to gripper; server will still start but actions will no-op")

    store = ModbusSlaveContext(
        di=DelegatingDataBlock(device, 0, [0] * 64, 'di'),
        co=DelegatingDataBlock(device, 0, [0] * 64, 'co'),
        hr=DelegatingDataBlock(device, 0, [0] * 128, 'hr'),
        ir=DelegatingDataBlock(device, 0, [0] * 128, 'ir'),
    )
    context = ModbusServerContext(slaves=store, single=True)

    log.info(
        f"Starting simple Modbus server on {host}:{port} "
        f"(oc_coil={open_coil}, close_coil={close_coil}, move_coil={move_coil}, flex_coil={flex_coil}, stop_coil={stop_coil}, "
        f"status_coils=[ready:{status_coil}, open:{status_open_coil}, closed:{status_closed_coil}, grip:{status_grip_coil}], "
        f"hr_force={hr_force_index}, hr_diam={hr_diameter_index}, hr_gt={hr_griptype_index}, hr_cmd={hr_cmd_index}, ir_width={ir_width_index}, mode={mode})"
    )
    try:
        await StartAsyncTcpServer(context=context, address=(host, port))
    finally:
        device.close()


def parse_args():
    p = argparse.ArgumentParser(description="Simple Modbus TCP server using a device class")
    # Only support config path and host/port overrides
    p.add_argument("--config", "-c", help="Path to YAML config. If missing, a default is created.")
    p.add_argument("--host", help="Bind host (overrides config)")
    p.add_argument("--port", type=int, help="Bind port (overrides config)")
    return p.parse_args()


async def main():
    args = parse_args()
    # Compute config path (default next to this script)
    default_cfg = Path(__file__).with_name("server_config.yaml")
    cfg_path = Path(args.config) if args.config else default_cfg

    # Default config structure
    default_cfg_dict = {
        'server': {'host': '127.0.0.1', 'port': 15020},
        'connection': {'mode': 'rtu', 'serial_port': '/dev/ttyUSB0', 'slave_addr': 65, 'ip': None, 'gripper_port': 502},
        'mapping': {
            'open_coil': 0,
            'close_coil': -1,
            'move_coil': -1,
            'flex_coil': -1,
            'stop_coil': -1,
            'status_coil': 2,
            'status_open_coil': 3,
            'status_closed_coil': 4,
            'status_grip_coil': 5,
            'hr_force_index': 0,
            'hr_diameter_index': 1,
            'hr_griptype_index': 2,
            'hr_cmd_index': 3,
            'ir_width_index': 0,
        },
    }

    # Create default config if needed (ensure parent dirs exist)
    if not cfg_path.exists():
        try:
            cfg_path.parent.mkdir(parents=True, exist_ok=True)
            cfg_path.write_text(yaml.safe_dump(default_cfg_dict, sort_keys=False))
            log.info(f"Created default config at {cfg_path}")
        except Exception as e:
            log.error(f"Could not create default config at {cfg_path}: {e}")

    # Load config and ensure missing keys are backfilled from defaults
    def _deep_merge(defaults: dict, overrides: dict) -> dict:
        out = {}
        for k, v in defaults.items():
            if isinstance(v, dict):
                ov = overrides.get(k, {}) if isinstance(overrides, dict) else {}
                out[k] = _deep_merge(v, ov if isinstance(ov, dict) else {})
            else:
                out[k] = overrides.get(k, v) if isinstance(overrides, dict) else v
        # Include any extra keys from overrides that are not in defaults
        if isinstance(overrides, dict):
            for k, v in overrides.items():
                if k not in out:
                    out[k] = v
        return out

    # Start from defaults
    cfg = default_cfg_dict.copy()
    if cfg_path.exists() and yaml is not None:
        try:
            loaded = yaml.safe_load(cfg_path.read_text()) or {}
            if not isinstance(loaded, dict):
                loaded = {}
            merged = _deep_merge(default_cfg_dict, loaded)
            cfg = merged
            # If we added defaults for missing keys, persist back to file
            if loaded != merged:
                try:
                    cfg_path.write_text(yaml.safe_dump(merged, sort_keys=False))
                    log.info(f"Updated config with missing defaults at {cfg_path}")
                except Exception as ie:
                    log.warning(f"Could not write back updated config: {ie}")
        except Exception as e:
            log.error(f"Failed to read config {cfg_path}: {e}")

    def pick(val, *path, fallback=None):
        if val is not None:
            return val
        cur = cfg
        for key in path:
            if not isinstance(cur, dict) or key not in cur:
                return fallback
            cur = cur[key]
        return cur if cur is not None else fallback

    host = pick(args.host, 'server', 'host', fallback='127.0.0.1')
    port = pick(args.port, 'server', 'port', fallback=15020)
    mode = pick(None, 'connection', 'mode', fallback='sim')
    serial_port = pick(None, 'connection', 'serial_port', fallback='/dev/tty.usbserial-A5052NB6')
    slave_addr = pick(None, 'connection', 'slave_addr', fallback=65)
    ip = pick(None, 'connection', 'ip', fallback=None)
    gripper_port = pick(None, 'connection', 'gripper_port', fallback=502)

    open_coil = pick(None, 'mapping', 'open_coil', fallback=0)
    close_coil = pick(None, 'mapping', 'close_coil', fallback=-1)
    move_coil = pick(None, 'mapping', 'move_coil', fallback=-1)
    flex_coil = pick(None, 'mapping', 'flex_coil', fallback=-1)
    stop_coil = pick(None, 'mapping', 'stop_coil', fallback=-1)

    status_coil = pick(None, 'mapping', 'status_coil', fallback=2)
    status_open_coil = pick(None, 'mapping', 'status_open_coil', fallback=3)
    status_closed_coil = pick(None, 'mapping', 'status_closed_coil', fallback=4)
    status_grip_coil = pick(None, 'mapping', 'status_grip_coil', fallback=5)

    hr_force_index = pick(None, 'mapping', 'hr_force_index', fallback=0)
    hr_diameter_index = pick(None, 'mapping', 'hr_diameter_index', fallback=1)
    hr_griptype_index = pick(None, 'mapping', 'hr_griptype_index', fallback=2)
    ir_width_index = pick(None, 'mapping', 'ir_width_index', fallback=0)
    hr_cmd_index = pick(None, 'mapping', 'hr_cmd_index', fallback=3)

    await run_server(
        host=host,
        port=port,
        open_coil=open_coil,
        status_coil=status_coil,
        close_coil=close_coil,
        move_coil=move_coil,
        flex_coil=flex_coil,
        stop_coil=stop_coil,
        status_open_coil=status_open_coil,
        status_closed_coil=status_closed_coil,
        status_grip_coil=status_grip_coil,
        hr_force_index=hr_force_index,
        hr_diameter_index=hr_diameter_index,
        hr_griptype_index=hr_griptype_index,
        hr_cmd_index=hr_cmd_index,
        ir_width_index=ir_width_index,
        mode=mode,
        serial_port=serial_port,
        slave_addr=slave_addr,
        tcp_ip=ip,
        tcp_port=gripper_port,
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer stopped by user")
