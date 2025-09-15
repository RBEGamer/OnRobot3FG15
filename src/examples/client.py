from pymodbus.client import ModbusTcpClient
c = ModbusTcpClient("127.0.0.1", port=1502)
c.connect()
print(c.read_input_registers(10, 6, unit=1))
c.write_register(1, 120, unit=1)   # HR[1] = force
c.write_register(0, 2, unit=1)     # HR[0] = close
