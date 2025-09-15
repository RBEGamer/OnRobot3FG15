from typing import List, Optional, Union

# Handle both package import and direct execution
try:
    # When imported as a package
    from .GripperBase import GripperBase
except ImportError:
    # When run directly as a script
    from GripperBase import GripperBase

# PyModbus >= 3.0.0
from pymodbus.client import ModbusTcpClient, ModbusSerialClient
from pymodbus.framer.rtu_framer import ModbusRtuFramer


class ThreeFG15Modbus(GripperBase):
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
                port=serial_port,
                framer=ModbusRtuFramer,
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

        result = self.client.write_register(reg, value, slave=self.slave_addr)  # type: ignore[arg-type]
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
       
        result = self.client.write_registers(start_reg, values, slave=self.slave_addr)  # type: ignore[arg-type]
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

        result = self.client.read_holding_registers(reg, count=count, slave=self.slave_addr)  # type: ignore[arg-type]
        if result.isError() or not hasattr(result, 'registers'):
            raise RuntimeError(f"Failed to read {count} registers starting at {reg}")
        return result.registers


if __name__ == "__main__":
    # --- Example 1: TCP (Ethernet) ---
    #gripper = ThreeFG15ModbusTCP(ip="192.168.178.22", port=5020)
    
    # --- Example 2: RTU (USB/serial RS485) ---
    gripper = ThreeFG15Modbus(mode="rtu", serial_port="/dev/tty.usbserial-A5052NB6")
    
    # --- Example 3: Simulator ---
    #gripper = ThreeFG15Simulator(simulation_speed=2.0, enable_noise=True)

    if gripper.open_connection():
        print(f"Connected to gripper {gripper.__class__.__name__}")

        # Open gripper
        gripper.open_gripper(force_val=500)

        # Wait a bit (robot program usually checks busy flag)
        import time; time.sleep(10)

        # Close gripper
        gripper.close_gripper(force_val=700)
        time.sleep(5)
        # Check status
        status = gripper.get_status()
        print("Status:", status)

        gripper.close_connection()
    else:
        print("Failed to connect")