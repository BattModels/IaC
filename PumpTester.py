import serial
import time

# Open the serial port (match your pump communication parameters)
ser = serial.Serial('COM14', 9600, parity=serial.PARITY_NONE, bytesize=8, stopbits=1, timeout=None, xonxoff=0, rtscts=0)

# Run pump clockwise at 20 RPM for 10s
Data = bytearray(b'\xE9\x0E\x08\x57\x4C\x00\x4C\x4B\x40\x01\x00\x5B')
ser.write(Data)

# Clear any old bytes in the buffer
ser.reset_input_buffer()
print('here')
# Wait briefly for the pump to respond
time.sleep(5)
# Read pump speed
Data = bytearray(b'\xE9\x0E\x02\x52\x4C\x12')
ser.write(Data)
# Read expected response (10 bytes)
response = ser.read(10)
print("Raw response:", response)

# Validate response and parse speed
'''
if len(response) >= 8 and response[3:5] == b'RJ':
    speed_hi = response[5]
    speed_lo = response[6]
    speed_raw = (speed_hi << 8) | speed_lo
    speed_rpm = speed_raw / 100.0
    print(f"Pump speed: {speed_rpm:.2f} RPM")
else:
    print("Invalid response")'''

# Stop the pump
Data = bytearray(b'\xE9\x0E\x08\x57\x4C\x00\x4C\x4B\x40\x00\x00\x5A')
ser.write(Data)
time.sleep(5)
ser.reset_input_buffer()
Data = bytearray(b'\xE9\x0E\x02\x52\x4C\x12')
ser.write(Data)
# Read expected response (10 bytes)
response = ser.read(10)
print("Raw response:", response)