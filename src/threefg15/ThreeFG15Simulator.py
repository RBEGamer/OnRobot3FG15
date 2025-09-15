import random
import time
from typing import List

# Handle both package import and direct execution
try:
    # When imported as a package
    from .GripperBase import GripType, GripperBase
except ImportError:
    # When run directly as a script
    from GripperBase import GripType, GripperBase


class ThreeFG15Simulator(GripperBase):
    """
    Simulator for the OnRobot 3FG15 gripper.
    
    This simulator provides realistic behavior for testing and development purposes
    without requiring actual hardware. It simulates the gripper's movement, force
    application, and status changes.
    
    Args:
        min_diameter (int): Minimum diameter in 0.1 mm units (default 0).
        max_diameter (int): Maximum diameter in 0.1 mm units (default 1000).
        finger_length (int): Finger length in 0.1 mm units (default 500).
        simulation_speed (float): Speed factor for movements (default 1.0).
        enable_noise (bool): Whether to add realistic noise to measurements (default True).
    """
    
    def __init__(self, min_diameter: int = 0, max_diameter: int = 1000, 
                 finger_length: int = 500, simulation_speed: float = 1.0,
                 enable_noise: bool = True) -> None:
        # Initialize simulator state
        self._registers = {}
        self._min_diameter = min_diameter
        self._max_diameter = max_diameter
        self._finger_length = finger_length
        self._simulation_speed = simulation_speed
        self._enable_noise = enable_noise
        
        # Current state
        self._current_diameter = max_diameter
        self._target_diameter = max_diameter
        self._current_force = 0
        self._target_force = 500
        self._grip_type = GripType.EXTERNAL
        self._is_busy = False
        self._grip_detected = False
        self._force_grip_detected = False
        self._calibration_ok = True
        
        # Movement simulation
        self._movement_start_time = None
        self._movement_duration = 0.5  # seconds
        
        # Initialize default register values
        self._initialize_registers()
        
    def _initialize_registers(self) -> None:
        """Initialize the simulator's internal register state."""
        self._registers = {
            self.REG_TARGET_FORCE: 500,
            self.REG_TARGET_DIAMETER: self._max_diameter,
            self.REG_GRIP_TYPE: 0,
            self.REG_CONTROL: 0,
            self.REG_STATUS: self._calculate_status_register(),
            self.REG_RAW_DIAMETER: self._current_diameter,
            self.REG_DIAMETER_OFFSET: self._current_diameter,
            self.REG_FORCE_APPLIED: 0,
            self.REG_FINGER_LENGTH: self._finger_length,
            self.REG_FINGER_POSITION: 1,
            self.REG_FINGERTIP_OFFSET: 0,
            self.REG_MIN_DIAMETER: self._min_diameter,
            self.REG_MAX_DIAMETER: self._max_diameter,
        }
    
    def _calculate_status_register(self) -> int:
        """Calculate the status register value from current state."""
        status = 0
        if self._is_busy:
            status |= 1
        if self._grip_detected:
            status |= 2
        if self._force_grip_detected:
            status |= 4
        if self._calibration_ok:
            status |= 8
        return status
    
    def _add_noise(self, value: int, noise_percent: float = 2.0) -> int:
        """Add realistic noise to a value."""
        if not self._enable_noise:
            return value
        noise = random.uniform(-noise_percent/100, noise_percent/100)
        return max(0, int(value * (1 + noise)))
    
    def _update_movement(self) -> None:
        """Update the gripper movement simulation."""
        if not self._is_busy or self._movement_start_time is None:
            return
            
        elapsed = time.time() - self._movement_start_time
        progress = min(1.0, elapsed / self._movement_duration)
        
        # Smooth movement using ease-in-out
        if progress < 0.5:
            t = 2 * progress * progress
        else:
            t = 1 - 2 * (1 - progress) * (1 - progress)
        
        # Update current diameter
        start_diameter = self._registers.get(self.REG_RAW_DIAMETER, self._current_diameter)
        diameter_diff = self._target_diameter - start_diameter
        self._current_diameter = start_diameter + int(diameter_diff * t)
        
        # Update force based on movement
        if abs(diameter_diff) > 0:
            # Simulate force increase during movement
            force_factor = min(1.0, progress * 2)
            self._current_force = int(self._target_force * force_factor)
        else:
            self._current_force = self._target_force
        
        # Check if movement is complete
        if progress >= 1.0:
            self._is_busy = False
            self._movement_start_time = None
            self._current_diameter = self._target_diameter
            self._current_force = self._target_force
            
            # Update grip detection based on final position
            self._update_grip_detection()
        
        # Update registers
        self._registers[self.REG_RAW_DIAMETER] = self._add_noise(self._current_diameter)
        self._registers[self.REG_DIAMETER_OFFSET] = self._add_noise(self._current_diameter)
        self._registers[self.REG_FORCE_APPLIED] = self._add_noise(self._current_force)
        self._registers[self.REG_STATUS] = self._calculate_status_register()
    
    def _update_grip_detection(self) -> None:
        """Update grip detection based on current state."""
        # Simple grip detection logic
        if self._current_diameter < self._max_diameter * 0.9:  # 90% of max
            self._grip_detected = True
            if self._current_force > self._target_force * 0.8:  # 80% of target force
                self._force_grip_detected = True
            else:
                self._force_grip_detected = False
        else:
            self._grip_detected = False
            self._force_grip_detected = False
    
    def _start_movement(self) -> None:
        """Start a new movement simulation."""
        self._is_busy = True
        self._movement_start_time = time.time()
        self._movement_duration = 0.5 / self._simulation_speed
    
    def open_connection(self) -> bool:
        """Simulate opening connection - always succeeds."""
        return True
    
    def close_connection(self) -> None:
        """Simulate closing connection."""
        pass
    
    def write_register(self, reg: int, value: int) -> None:
        """Write a single register and trigger appropriate actions."""
        if reg == self.REG_TARGET_FORCE:
            self._target_force = max(0, min(1000, value))
        elif reg == self.REG_TARGET_DIAMETER:
            self._target_diameter = max(self._min_diameter, min(self._max_diameter, value))
        elif reg == self.REG_GRIP_TYPE:
            self._grip_type = GripType(value)
        elif reg == self.REG_CONTROL:
            if value in [self.CMD_GRIP, self.CMD_MOVE, self.CMD_FLEXIBLE_GRIP]:
                self._start_movement()
            elif value == self.CMD_STOP:
                self._is_busy = False
                self._movement_start_time = None
        
        self._registers[reg] = value
        
        # Update movement if needed
        self._update_movement()
    
    def write_registers(self, start_reg: int, values: List[int]) -> None:
        """Write multiple registers."""
        for i, value in enumerate(values):
            self.write_register(start_reg + i, value)
    
    def read_registers(self, reg: int, count: int = 1) -> List[int]:
        """Read holding registers with current simulation state."""
        # Update movement before reading
        self._update_movement()
        
        result = []
        for i in range(count):
            addr = reg + i
            if addr in self._registers:
                result.append(self._registers[addr])
            else:
                result.append(0)  # Default value for undefined registers
        
        return result




