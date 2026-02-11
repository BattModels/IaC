from devices.Potentiostat import Potentiostat
from devices.Pump import Pump
import time
'''potentiostat = Potentiostat("PalmSens4", 1, 8, "Potentiostat")
potentiostat.create()
potentiostat.update(method_id='eis')
result = potentiostat.read()
difference = potentiostat.diff()
#potentiostat.update(technique=1)
#result2 = potentiostat.read()
potentiostat.delete()'''

pump = Pump('Pump_Sonicator', 1, 14, "Pump")
pump.create()
pump.update(5, 1, Pump.State2.COUNTER_CLOCKWISE)
time.sleep(1)
pump.read()

time.sleep(15)
pump.delete()