#!/usr/bin/env python3
from typing import Optional, List, Union
from dataclasses import dataclass
from enum import Enum
from pymodbus.client.sync import ModbusTcpClient, ModbusSerialClient


@dataclass
class ThreeFG15Status:
    """
    Data class representing the status bits of the 3FG15 gripper.
    """
    busy: bool
    grip_detected: bool
    force_grip_detected: bool
    calibration_ok: bool

    @classmethod
    def from_register(cls, reg_value: int) -> "ThreeFG15Status":
        """
        Create a ThreeFG15Status instance from a 16-bit register value.

        Args:
            reg_value (int): 16-bit integer status register.

        Returns:
            ThreeFG15Status: Parsed status object.
        """
        status = format(reg_value, '016b')
        return cls(
            busy=bool(int(status[-1])),
            grip_detected=bool(int(status[-2])),
            force_grip_detected=bool(int(status[-3])),
            calibration_ok=bool(int(status[-4]))
        )


class GripType(Enum):
    EXTERNAL = 0
    INTERNAL = 1


class ThreeFG15:
    """
    OnRobot 3FG15 Modbus interface (TCP or RTU).

    Provides methods to control and monitor the 3FG15 gripper via Modbus TCP or RTU.

    Args:
        mode (str): "tcp" or "rtu" to select communication mode.
        ip (Optional[str]): IP address for TCP mode.
        port (int): TCP port number (default 502).
        serial_port (Optional[str]): Serial port name for RTU mode.
        slave_addr (int): Modbus slave address (default 65).
        timeout (float): Communication timeout in seconds (default 1).

    Raises:
        ValueError: If required parameters for selected mode are missing.
    """

    # Register map (from Connectivity Guide v1.20)
    REG_TARGET_FORCE      = 0     # write, 0–1000 (% of max force)
    REG_TARGET_DIAMETER   = 1     # write, 0.1 mm units
    REG_GRIP_TYPE         = 2     # write, 0=external, 1=internal
    REG_CONTROL           = 3     # write, control command
    REG_STATUS            = 256   # read, bitfield
    REG_RAW_DIAMETER      = 257   # read, 0.1 mm
    REG_DIAMETER_OFFSET   = 258   # read, 0.1 mm
    REG_FORCE_APPLIED     = 259   # read, 0.1 %
    REG_FINGER_LENGTH     = 270   # read, 0.1 mm
    REG_FINGER_POSITION   = 272   # read, enum 1–3
    REG_FINGERTIP_OFFSET  = 273   # read, 0.01 mm
    REG_MIN_DIAMETER      = 513   # read, 0.1 mm
    REG_MAX_DIAMETER      = 514   # read, 0.1 mm

    # Control values
    CMD_GRIP              = 1
    CMD_MOVE              = 2
    CMD_STOP              = 4
    CMD_FLEXIBLE_GRIP     = 5

    def __init__(self, mode: str = "tcp", ip: Optional[str] = None, port: int = 502,
                 serial_port: Optional[str] = None, slave_addr: int = 65, timeout: float = 1.0) -> None:
        self.mode = mode
        self.slave_addr = slave_addr
        self.client: Optional[Union[ModbusTcpClient, ModbusSerialClient]] = None

        if mode == "tcp":
            if not ip:
                raise ValueError("IP address required for TCP mode")
            self.client = ModbusTcpClient(ip, port=port, timeout=timeout)

        elif mode == "rtu":
            if not serial_port:
                raise ValueError("Serial port required for RTU mode")
            self.client = ModbusSerialClient(
                method="rtu",
                port=serial_port,
                baudrate=1000000,
                stopbits=1,
                bytesize=8,
                parity='E',
                timeout=timeout
            )
        else:
            raise ValueError("Mode must be 'tcp' or 'rtu'")

    def open_connection(self) -> bool:
        """
        Open connection to the Modbus client.

        Returns:
            bool: True if connection was successful, False otherwise.
        """
        if self.client is None:
            raise RuntimeError("Modbus client not initialized")
        return self.client.connect()

    def close_connection(self) -> None:
        """
        Close the Modbus client connection.
        """
        if self.client is None:
            raise RuntimeError("Modbus client not initialized")
        self.client.close()

    # ------------------ Low-level access ------------------
    def write_register(self, reg: int, value: int) -> None:
        """
        Write a single register.

        Args:
            reg (int): Register address.
            value (int): Value to write.

        Raises:
            RuntimeError: If write operation fails.
        """
        if self.client is None:
            raise RuntimeError("Modbus client not initialized")
        result = self.client.write_register(reg, value, unit=self.slave_addr)
        if result.isError():
            raise RuntimeError(f"Failed to write register {reg} with value {value}")

    def write_registers(self, start_reg: int, values: List[int]) -> None:
        """
        Write multiple registers starting at start_reg.

        Args:
            start_reg (int): Starting register address.
            values (List[int]): List of values to write.

        Raises:
            RuntimeError: If write operation fails.
        """
        if self.client is None:
            raise RuntimeError("Modbus client not initialized")
        result = self.client.write_registers(start_reg, values, unit=self.slave_addr)
        if result.isError():
            raise RuntimeError(f"Failed to write registers starting at {start_reg} with values {values}")

    def read_registers(self, reg: int, count: int = 1) -> List[int]:
        """
        Read holding registers.

        Args:
            reg (int): Starting register address.
            count (int): Number of registers to read.

        Returns:
            List[int]: List of register values.

        Raises:
            RuntimeError: If read operation fails.
        """
        if self.client is None:
            raise RuntimeError("Modbus client not initialized")
        result = self.client.read_holding_registers(reg, count, unit=self.slave_addr)
        if result.isError() or not hasattr(result, 'registers'):
            raise RuntimeError(f"Failed to read {count} registers starting at {reg}")
        return result.registers

    # ------------------ High-level commands ------------------
    def set_target_force(self, force_val: int) -> None:
        """
        Set grip force (0–1000 = 0–100%).

        Args:
            force_val (int): Force value to set.
        """
        self.write_register(self.REG_TARGET_FORCE, force_val)

    def set_target_diameter(self, diameter: int) -> None:
        """
        Set target diameter in 0.1 mm units.

        Args:
            diameter (int): Target diameter.
        """
        self.write_register(self.REG_TARGET_DIAMETER, diameter)

    def set_grip_type(self, grip_type: GripType) -> None:
        """
        Set grip type.

        Args:
            grip_type (GripType): Grip type enum value (EXTERNAL or INTERNAL).
        """
        self.write_register(self.REG_GRIP_TYPE, grip_type.value)

    def set_control(self, cmd: int) -> None:
        """
        Send control command (grip, move, stop, flexible grip).

        Args:
            cmd (int): Command code.
        """
        self.write_register(self.REG_CONTROL, cmd)

    def get_status(self) -> Optional[ThreeFG15Status]:
        """
        Get the status of the gripper.

        Returns:
            Optional[ThreeFG15Status]: Status object if read succeeds, None otherwise.
        """
        try:
            regs = self.read_registers(self.REG_STATUS, 1)
            if not regs:
                return None
            return ThreeFG15Status.from_register(regs[0])
        except RuntimeError:
            return None

    def get_raw_diameter(self) -> Optional[float]:
        """
        Get the raw diameter in mm.

        Returns:
            Optional[float]: Diameter in mm if read succeeds, None otherwise.
        """
        try:
            r = self.read_registers(self.REG_RAW_DIAMETER, 1)
            return r[0] / 10.0 if r else None
        except RuntimeError:
            return None

    def get_diameter_with_offset(self) -> Optional[float]:
        """
        Get the diameter with offset in mm.

        Returns:
            Optional[float]: Diameter in mm if read succeeds, None otherwise.
        """
        try:
            r = self.read_registers(self.REG_DIAMETER_OFFSET, 1)
            return r[0] / 10.0 if r else None
        except RuntimeError:
            return None

    def get_force_applied(self) -> Optional[float]:
        """
        Get the applied force in percent.

        Returns:
            Optional[float]: Force percent if read succeeds, None otherwise.
        """
        try:
            r = self.read_registers(self.REG_FORCE_APPLIED, 1)
            return r[0] / 10.0 if r else None
        except RuntimeError:
            return None

    # ------------------ Convenience methods ------------------
    def open_gripper(self, force_val: int = 500) -> None:
        """
        Open gripper fully with given force (default 50%).

        Args:
            force_val (int): Force value to use.
        """
        try:
            max_d = self.read_registers(self.REG_MAX_DIAMETER, 1)
            if not max_d:
                raise RuntimeError("Could not read max diameter")
            self.set_target_force(force_val)
            self.set_target_diameter(max_d[0])
            self.set_grip_type(GripType.EXTERNAL)  # external grip
            self.set_control(self.CMD_GRIP)
        except RuntimeError as e:
            print(f"Error in open_gripper: {e}")

    def close_gripper(self, force_val: int = 500) -> None:
        """
        Close gripper fully with given force (default 50%).

        Args:
            force_val (int): Force value to use.
        """
        try:
            min_d = self.read_registers(self.REG_MIN_DIAMETER, 1)
            if not min_d:
                raise RuntimeError("Could not read min diameter")
            self.set_target_force(force_val)
            self.set_target_diameter(min_d[0])
            self.set_grip_type(GripType.EXTERNAL)  # external grip
            self.set_control(self.CMD_GRIP)
        except RuntimeError as e:
            print(f"Error in close_gripper: {e}")

    def move_gripper(self, diameter: int, force_val: int = 500, grip_type: GripType = GripType.INTERNAL) -> None:
        """
        Move gripper to target diameter.

        Args:
            diameter (int): Target diameter in 0.1 mm units.
            force_val (int): Force value to use.
            grip_type (GripType): Grip type enum (EXTERNAL or INTERNAL).
        """
        self.set_target_force(force_val)
        self.set_target_diameter(diameter)
        self.set_grip_type(grip_type)
        self.set_control(self.CMD_GRIP)

    def flex_grip(self, diameter: int, force_val: int = 100, grip_type: GripType = GripType.INTERNAL) -> None:
        """
        Perform a flexible grip with specified force, diameter, and grip type.

        Args:
            force_val (int): Force value to use.
            diameter (int): Target diameter in 0.1 mm units.
            grip_type (GripType): Grip type enum (EXTERNAL or INTERNAL).
        """
        self.set_target_force(force_val)
        self.set_target_diameter(diameter)
        self.set_grip_type(grip_type)
        self.set_control(self.CMD_FLEXIBLE_GRIP)

    def detect_object(self) -> bool:
        """
        Detect if an object is detected or firmly gripped.

        Returns:
            bool: True if an object is detected or firmly gripped, False otherwise.
        """
        status = self.get_status()
        if status is None:
            return False
        return status.grip_detected or status.force_grip_detected



class ThreeFG15TCP(ThreeFG15):
    def __init__(self, ip: str, port: int = 502, timeout: float = 1.0) -> None:
        super().__init__(mode="tcp", ip=ip, port=port, timeout=timeout)
    
    
class ThreeFG15RTU(ThreeFG15):
    def __init__(self, serial_port: str, timeout: float = 1.0) -> None:
        super().__init__(mode="rtu", serial_port=serial_port, timeout=timeout)



if __name__ == "__main__":
    # --- Example 1: TCP (Ethernet) ---
    #gripper = ThreeFG15(mode="tcp", ip="192.168.178.22", port=5020)
    
    # --- Example 2: RTU (USB/serial RS485) ---
    gripper = ThreeFG15(mode="rtu", serial_port="/dev/tty.usbserial-A5052NB6")

    if gripper.open_connection():
        print("Connected to gripper")

        # Open gripper
        gripper.open_gripper(force_val=500)

        # Wait a bit (robot program usually checks busy flag)
        import time; time.sleep(2)

        # Close gripper
        gripper.close_gripper(force_val=700)

        # Check status
        status = gripper.get_status()
        print("Status:", status)

        gripper.close_connection()
    else:
        print("Failed to connect")