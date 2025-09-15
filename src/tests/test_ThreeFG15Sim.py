import pytest
import time
from unittest.mock import patch
from threefg15.ThreeFG15Simulator import ThreeFG15Simulator
from threefg15.GripperBase import GripType


class TestThreeFG15Simulator:
    """Test class for ThreeFG15Simulator functionality."""
    
    @pytest.fixture
    def simulator(self):
        """Create a fresh simulator instance for each test."""
        return ThreeFG15Simulator()
    
    @pytest.fixture
    def custom_simulator(self):
        """Create a simulator with custom parameters."""
        return ThreeFG15Simulator(
            min_diameter=100,
            max_diameter=800,
            finger_length=400,
            simulation_speed=2.0,
            enable_noise=False
        )
    
    def test_initialization_default(self, simulator):
        """Test simulator initialization with default parameters."""
        assert simulator._min_diameter == 0
        assert simulator._max_diameter == 1000
        assert simulator._finger_length == 500
        assert simulator._simulation_speed == 1.0
        assert simulator._enable_noise is True
        assert simulator._current_diameter == 1000
        assert simulator._target_diameter == 1000
        assert simulator._current_force == 0
        assert simulator._target_force == 500
        assert simulator._grip_type == GripType.EXTERNAL
        assert simulator._is_busy is False
        assert simulator._grip_detected is False
        assert simulator._force_grip_detected is False
        assert simulator._calibration_ok is True
    
    def test_initialization_custom(self, custom_simulator):
        """Test simulator initialization with custom parameters."""
        assert custom_simulator._min_diameter == 100
        assert custom_simulator._max_diameter == 800
        assert custom_simulator._finger_length == 400
        assert custom_simulator._simulation_speed == 2.0
        assert custom_simulator._enable_noise is False
    
    def test_initialize_registers(self, simulator):
        """Test register initialization."""
        simulator._initialize_registers()
        
        # Check key registers
        assert simulator._registers[simulator.REG_TARGET_FORCE] == 500
        assert simulator._registers[simulator.REG_TARGET_DIAMETER] == 1000
        assert simulator._registers[simulator.REG_GRIP_TYPE] == 0
        assert simulator._registers[simulator.REG_CONTROL] == 0
        assert simulator._registers[simulator.REG_RAW_DIAMETER] == 1000
        assert simulator._registers[simulator.REG_DIAMETER_OFFSET] == 1000
        assert simulator._registers[simulator.REG_FORCE_APPLIED] == 0
        assert simulator._registers[simulator.REG_FINGER_LENGTH] == 500
        assert simulator._registers[simulator.REG_MIN_DIAMETER] == 0
        assert simulator._registers[simulator.REG_MAX_DIAMETER] == 1000
    
    def test_calculate_status_register(self, simulator):
        """Test status register calculation."""
        # Test initial state
        status = simulator._calculate_status_register()
        assert status == 8  # Only calibration_ok is True
        
        # Test busy state
        simulator._is_busy = True
        status = simulator._calculate_status_register()
        assert status == 9  # busy + calibration_ok
        
        # Test grip detected
        simulator._grip_detected = True
        status = simulator._calculate_status_register()
        assert status == 11  # busy + grip_detected + calibration_ok
        
        # Test force grip detected
        simulator._force_grip_detected = True
        status = simulator._calculate_status_register()
        assert status == 15  # All flags set
        
        # Test no calibration
        simulator._calibration_ok = False
        status = simulator._calculate_status_register()
        assert status == 7  # All except calibration_ok
    
    def test_add_noise(self, simulator):
        """Test noise addition functionality."""
        # Test with noise enabled
        value = 100
        noisy_value = simulator._add_noise(value, 5.0)
        assert 95 <= noisy_value <= 105
        
        # Test with noise disabled
        simulator._enable_noise = False
        noisy_value = simulator._add_noise(value, 5.0)
        assert noisy_value == value
        
        # Test minimum value constraint
        noisy_value = simulator._add_noise(0, 10.0)
        assert noisy_value >= 0
    
    def test_connection_operations(self, simulator):
        """Test connection operations."""
        # Test open connection
        assert simulator.open_connection() is True
        
        # Test close connection (should not raise exception)
        simulator.close_connection()
    
    def test_write_register_target_force(self, simulator):
        """Test writing to target force register."""
        simulator.write_register(simulator.REG_TARGET_FORCE, 750)
        assert simulator._target_force == 750
        assert simulator._registers[simulator.REG_TARGET_FORCE] == 750
        
        # Test bounds checking
        simulator.write_register(simulator.REG_TARGET_FORCE, 1500)  # Above max
        assert simulator._target_force == 1000
        
        simulator.write_register(simulator.REG_TARGET_FORCE, -100)  # Below min
        assert simulator._target_force == 0
    
    def test_write_register_target_diameter(self, simulator):
        """Test writing to target diameter register."""
        simulator.write_register(simulator.REG_TARGET_DIAMETER, 500)
        assert simulator._target_diameter == 500
        assert simulator._registers[simulator.REG_TARGET_DIAMETER] == 500
        
        # Test bounds checking
        simulator.write_register(simulator.REG_TARGET_DIAMETER, 1500)  # Above max
        assert simulator._target_diameter == 1000
        
        simulator.write_register(simulator.REG_TARGET_DIAMETER, -100)  # Below min
        assert simulator._target_diameter == 0
    
    def test_write_register_grip_type(self, simulator):
        """Test writing to grip type register."""
        simulator.write_register(simulator.REG_GRIP_TYPE, 1)
        assert simulator._grip_type == GripType.INTERNAL
        assert simulator._registers[simulator.REG_GRIP_TYPE] == 1
        
        simulator.write_register(simulator.REG_GRIP_TYPE, 0)
        assert simulator._grip_type == GripType.EXTERNAL
        assert simulator._registers[simulator.REG_GRIP_TYPE] == 0
    
    def test_write_register_control_commands(self, simulator):
        """Test writing control commands."""
        # Test GRIP command
        simulator.write_register(simulator.REG_CONTROL, simulator.CMD_GRIP)
        assert simulator._is_busy is True
        assert simulator._movement_start_time is not None
        
        # Reset for next test
        simulator._is_busy = False
        simulator._movement_start_time = None
        
        # Test MOVE command
        simulator.write_register(simulator.REG_CONTROL, simulator.CMD_MOVE)
        assert simulator._is_busy is True
        assert simulator._movement_start_time is not None
        
        # Reset for next test
        simulator._is_busy = False
        simulator._movement_start_time = None
        
        # Test FLEXIBLE_GRIP command
        simulator.write_register(simulator.REG_CONTROL, simulator.CMD_FLEXIBLE_GRIP)
        assert simulator._is_busy is True
        assert simulator._movement_start_time is not None
        
        # Test STOP command
        simulator.write_register(simulator.REG_CONTROL, simulator.CMD_STOP)
        assert simulator._is_busy is False
        assert simulator._movement_start_time is None
    
    def test_write_registers_multiple(self, simulator):
        """Test writing multiple registers."""
        values = [600, 400, 1, 2]  # force, diameter, grip_type, control
        simulator.write_registers(simulator.REG_TARGET_FORCE, values)
        
        assert simulator._registers[simulator.REG_TARGET_FORCE] == 600
        assert simulator._registers[simulator.REG_TARGET_DIAMETER] == 400
        assert simulator._registers[simulator.REG_GRIP_TYPE] == 1
        assert simulator._registers[simulator.REG_CONTROL] == 2
    
    def test_read_registers(self, simulator):
        """Test reading registers."""
        # Test reading single register
        result = simulator.read_registers(simulator.REG_TARGET_FORCE, 1)
        assert len(result) == 1
        assert result[0] == 500
        
        # Test reading multiple registers
        result = simulator.read_registers(simulator.REG_TARGET_FORCE, 3)
        assert len(result) == 3
        assert result[0] == 500  # target force
        assert result[1] == 1000  # target diameter
        assert result[2] == 0  # grip type
        
        # Test reading undefined register
        result = simulator.read_registers(999, 1)
        assert len(result) == 1
        assert result[0] == 0
    
    def test_movement_simulation(self, simulator):
        """Test movement simulation functionality."""
        # Set different target diameter to create movement
        simulator._target_diameter = 500
        simulator._current_diameter = 1000
        
        # Start movement
        simulator._start_movement()
        assert simulator._is_busy is True
        assert simulator._movement_start_time is not None
        
        # Simulate time passing
        with patch('time.time') as mock_time:
            mock_time.return_value = simulator._movement_start_time + 0.25  # Halfway
            simulator._update_movement()
            
            # Should still be busy
            assert simulator._is_busy is True
            
            # Should have moved partially
            assert simulator._current_diameter != simulator._target_diameter
            
            # Complete movement
            mock_time.return_value = simulator._movement_start_time + 0.6  # Complete
            simulator._update_movement()
            
            # Should be complete
            assert simulator._is_busy is False
            assert simulator._current_diameter == simulator._target_diameter
    
    def test_grip_detection(self, simulator):
        """Test grip detection logic."""
        # Test no grip at max diameter
        simulator._current_diameter = simulator._max_diameter
        simulator._update_grip_detection()
        assert simulator._grip_detected is False
        assert simulator._force_grip_detected is False
        
        # Test grip detected at 80% of max
        simulator._current_diameter = int(simulator._max_diameter * 0.8)
        simulator._current_force = int(simulator._target_force * 0.9)
        simulator._update_grip_detection()
        assert simulator._grip_detected is True
        assert simulator._force_grip_detected is True
        
        # Test grip detected but not force grip
        simulator._current_force = int(simulator._target_force * 0.5)
        simulator._update_grip_detection()
        assert simulator._grip_detected is True
        assert simulator._force_grip_detected is False
    
    def test_high_level_commands(self, simulator):
        """Test high-level command methods."""
        # Test set_target_force
        simulator.set_target_force(750)
        assert simulator._target_force == 750
        
        # Test set_target_diameter
        simulator.set_target_diameter(400)
        assert simulator._target_diameter == 400
        
        # Test set_grip_type
        simulator.set_grip_type(GripType.INTERNAL)
        assert simulator._grip_type == GripType.INTERNAL
        
        # Test set_control
        simulator.set_control(simulator.CMD_GRIP)
        assert simulator._is_busy is True
    
    def test_open_gripper(self, simulator):
        """Test open_gripper command."""
        simulator.open_gripper(600)
        
        # Should set target force and diameter
        assert simulator._target_force == 600
        assert simulator._target_diameter == simulator._max_diameter
        assert simulator._grip_type == GripType.EXTERNAL
        assert simulator._is_busy is True
    
    def test_close_gripper(self, simulator):
        """Test close_gripper command."""
        simulator.close_gripper(700)
        
        # Should set target force and diameter
        assert simulator._target_force == 700
        assert simulator._target_diameter == simulator._min_diameter
        assert simulator._grip_type == GripType.EXTERNAL
        assert simulator._is_busy is True
    
    def test_move_gripper(self, simulator):
        """Test move_gripper command."""
        simulator.move_gripper(300, 800, GripType.INTERNAL)
        
        # Should set all parameters
        assert simulator._target_force == 800
        assert simulator._target_diameter == 300
        assert simulator._grip_type == GripType.INTERNAL
        assert simulator._is_busy is True
    
    def test_flex_grip(self, simulator):
        """Test flex_grip command."""
        simulator.flex_grip(200, 100, GripType.EXTERNAL)
        
        # Should set all parameters
        assert simulator._target_force == 100
        assert simulator._target_diameter == 200
        assert simulator._grip_type == GripType.EXTERNAL
        assert simulator._is_busy is True
    
    def test_get_status(self, simulator):
        """Test get_status method."""
        status = simulator.get_status()
        assert status is not None
        assert status.busy is False
        assert status.grip_detected is False
        assert status.force_grip_detected is False
        assert status.calibration_ok is True
        
        # Test with busy state
        simulator._is_busy = True
        # Update registers to reflect the new state
        simulator._registers[simulator.REG_STATUS] = simulator._calculate_status_register()
        status = simulator.get_status()
        assert status.busy is True
    
    def test_get_raw_diameter(self, simulator):
        """Test get_raw_diameter method."""
        diameter = simulator.get_raw_diameter()
        assert diameter == 100.0  # 1000 / 10.0 mm
        
        # Test with different value
        simulator._current_diameter = 500
        # Update the register to reflect the new value
        simulator._registers[simulator.REG_RAW_DIAMETER] = 500
        diameter = simulator.get_raw_diameter()
        assert diameter == 50.0  # 500 / 10.0 mm
    
    def test_get_diameter_with_offset(self, simulator):
        """Test get_diameter_with_offset method."""
        diameter = simulator.get_diameter_with_offset()
        assert diameter == 100.0  # 1000 / 10.0 mm
    
    def test_get_force_applied(self, simulator):
        """Test get_force_applied method."""
        force = simulator.get_force_applied()
        assert force == 0.0  # 0 / 10.0 %
        
        # Test with different value
        simulator._current_force = 500
        # Update the register to reflect the new value
        simulator._registers[simulator.REG_FORCE_APPLIED] = 500
        force = simulator.get_force_applied()
        assert force == 50.0  # 500 / 10.0 %
    
    def test_detect_object(self, simulator):
        """Test detect_object method."""
        # Initially no object detected
        assert simulator.detect_object() is False
        
        # Set grip detected
        simulator._grip_detected = True
        # Update registers to reflect the new state
        simulator._registers[simulator.REG_STATUS] = simulator._calculate_status_register()
        assert simulator.detect_object() is True
        
        # Set force grip detected
        simulator._grip_detected = False
        simulator._force_grip_detected = True
        # Update registers to reflect the new state
        simulator._registers[simulator.REG_STATUS] = simulator._calculate_status_register()
        assert simulator.detect_object() is True
    
    def test_simulation_speed_effect(self, custom_simulator):
        """Test that simulation speed affects movement duration."""
        custom_simulator._start_movement()
        expected_duration = 0.5 / 2.0  # 0.5 / simulation_speed
        assert custom_simulator._movement_duration == expected_duration
    
    def test_noise_disabled(self, custom_simulator):
        """Test that noise is properly disabled."""
        value = 100
        noisy_value = custom_simulator._add_noise(value, 10.0)
        assert noisy_value == value  # No noise should be added
    
    def test_register_bounds_enforcement(self, simulator):
        """Test that register writes enforce proper bounds."""
        # Test force bounds
        simulator.write_register(simulator.REG_TARGET_FORCE, 1500)
        assert simulator._target_force == 1000  # Max bound
        
        simulator.write_register(simulator.REG_TARGET_FORCE, -100)
        assert simulator._target_force == 0  # Min bound
        
        # Test diameter bounds
        simulator.write_register(simulator.REG_TARGET_DIAMETER, 1500)
        assert simulator._target_diameter == 1000  # Max bound
        
        simulator.write_register(simulator.REG_TARGET_DIAMETER, -100)
        assert simulator._target_diameter == 0  # Min bound
