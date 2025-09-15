from abc import ABC, abstractmethod
from enum import Enum
from typing import List, Optional

# Handle both package import and direct execution
try:
    # When imported as a package
    from .status import ThreeFG15Status
except ImportError:
    # When run directly as a script
    from status import ThreeFG15Status

class GripType(Enum):
    EXTERNAL = 0
    INTERNAL = 1

class GripperBase(ABC):
    """
    Abstract base class for gripper implementations.
    
    This class defines the interface that all gripper implementations must follow,
    whether they are real hardware, simulators, or other implementations.
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

    @abstractmethod
    def open_connection(self) -> bool:
        """Open connection to the gripper."""
        pass

    @abstractmethod
    def close_connection(self) -> None:
        """Close the gripper connection."""
        pass

    @abstractmethod
    def write_register(self, reg: int, value: int) -> None:
        """Write a single register."""
        pass

    @abstractmethod
    def write_registers(self, start_reg: int, values: List[int]) -> None:
        """Write multiple registers starting at start_reg."""
        pass

    @abstractmethod
    def read_registers(self, reg: int, count: int = 1) -> List[int]:
        """Read holding registers."""
        pass

    # High-level commands with default implementations
    def set_target_force(self, force_val: int) -> None:
        """
        Set grip force (0-1000 = 0-100%).

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

    # Convenience methods with default implementations
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