from devices.Potentiostat import Potentiostat
from devices.Pump import Pump
from devices.Balance import Balance
from devices.Relay import Relay
import time
'''potentiostat = Potentiostat("PalmSens4", 1, 8, "Potentiostat")
potentiostat.create()
potentiostat.update(method_id='eis')
result = potentiostat.read()
difference = potentiostat.diff()
#potentiostat.update(technique=1)
#result2 = potentiostat.read()
potentiostat.delete()'''

'''
pump = Pump('Pump_Valve', 1, 12, "Pump")
pump.create()
for i in range(1, 2):
    pump.update(i / 2, i / 10, Pump.State2.COUNTER_CLOCKWISE)
    time.sleep(1)
    result = pump.read()
    print(result['flow_rate_bytes'])
    time.sleep(12)
pump.delete()'''

'''
balance = Balance('balance', 1, 9, "Balance")
balance.create()
print(balance.read())
balance.delete()'''

PATH = b'\\\\?\\HID#VID_16C0&PID_05DF#8&be40740&0&0000#{4d1e55b2-f16f-11cf-88cb-001111000030}'
relay = Relay(name="Relay", id=11, identifier=PATH, type_name='relay')
relay.create()

relay.update(1, Relay.State_Relay.ON)
relay.update(4, Relay.State_Relay.ON)
time.sleep(12)
print(relay.read())
relay.update(1, Relay.State_Relay.OFF)
relay.update(4, Relay.State_Relay.OFF)
relay.delete()
