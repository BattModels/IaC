import os
import time
import numpy as np
import pandas as pd
from datetime import datetime
from pathlib import Path

try:
    from .Instrument import Instrument, ConnectionType
    from .Resource import Status
    from .Utils import RETRY_LIMIT, sanitize_filename, save_dict_to_json
except Exception as e:
    from Instrument import Instrument, ConnectionType
    from Resource import Status
    from Utils import RETRY_LIMIT, sanitize_filename, save_dict_to_json

from pspython import pspyinstruments, pspymethods, pspyfiles


SIGNIFICANT_DIGITS = 8
FREQ_THRESHOLD = 1.5E5


class Potentiostat(Instrument):
    """
    PalmSens potentiostat controller.
    Handles connection, EIS/conductivity measurement, and data processing.
    """

    def __init__(self, name: str, identifier: int, status, baud_rate: int = 9600, **kwargs):
        super().__init__(name=name, connection_type=ConnectionType.SERIAL,
                         identifier=identifier, status=status)
        self.manager = None
        self.instrument = None
        self.method = None
        self.baud_rate = baud_rate
        self._initialize_manager()

    # ---------- Initialization ----------

    def _initialize_manager(self):
        """Initialize the PalmSens instrument manager with a callback."""
        def new_data_callback(new_data):
            for dtype, value in new_data.items():
                self.log(f"{dtype} = {value}")
        self.manager = pspyinstruments.InstrumentManager(new_data_callback=new_data_callback)

    # ---------- Core Methods ----------

    def connect(self):
        """Connect to the PalmSens potentiostat."""
        available = pspyinstruments.discover_instruments()
        print(available)
        for device in available:
            if device.name.startswith(self.name):
                self.instrument = device
                break

        if not self.instrument:
            self.status = Status.ERROR
            raise RuntimeError(f"Cannot find potentiostat {self.name}")

        try:
            success = self.manager.connect(self.instrument)
            if success == 1:
                self.status = Status.IN_USE
                self.log(f"Connected to {self.instrument.name}")
                return
        except Exception as e:
            self.status = Status.ERROR
            raise ConnectionError(f"Failed to connect to potentiostat {self.name}")

    def disconnect(self):
        """Disconnect the instrument safely."""
        if self.manager and self.instrument:
            try:
                success = self.manager.disconnect()
                if success == 1:
                    self.status = Status.AVAILABLE
                    self.log(f"Disconnected from {self.instrument.name}")
                else:
                    raise RuntimeError("Error while disconnecting.")
            except Exception as e:
                self.status = Status.ERROR
                self.log(f"Error during disconnect: {e}", level="ERROR")

    # ---------- Measurement Logic ----------

    def action(self,
            mux_channel: int = 4,
            use_mux: bool = True,
            amplitude: float = 0.25,
            freq_min: float = 2.0e4,
            freq_max: float = 5.92e5,
            n_freq: int = 10,
            freq_type: int = 1,
            e_begin: float = 0.0,
            e_end: float = 0.0,
            e_step: float = 6e-5,
            scantype: int = 2,
            freq_mode: int = 0,
            pgstat_mode: int = 8,
            t_sampling: float = 0.5,
            t_maxeq: float = 5.0,
            pret_eachfreqscan: bool = False,
            t_interval: float = 0.1,
            t_run: float = 10.0,
            signal: int = 1,
            reaction: int = 2,
            save_on_device: bool = True):
        """
        Perform a conductivity (EIS) measurement.
        Args:
            method_path: Path to the .psmethod file
        Returns:
            float: Computed resistance value (proxy for conductivity)
        """
        if not self.instrument:
            self.connect()

        try:
            filename = "Temp.psmethod"
            current_dir = os.path.dirname(os.path.abspath(__file__))
            filename = os.path.join(current_dir, filename)
            self.log(f"Loading method file: {filename}")
            generate_psmethod_file(
                filename,
                mux_channel=mux_channel,
                use_mux=use_mux,
                amplitude=amplitude,
                freq_min=freq_min,
                freq_max=freq_max,
                n_freq=n_freq,
                freq_type=freq_type,
                e_begin=e_begin,
                e_end=e_end,
                e_step=e_step,
                scantype=scantype,
                freq_mode=freq_mode,
                pgstat_mode=pgstat_mode,
                t_sampling=t_sampling,
                t_maxeq=t_maxeq,
                pret_eachfreqscan=pret_eachfreqscan,
                t_interval=t_interval,
                t_run=t_run,
                signal=signal,
                reaction=reaction,
                save_on_device=save_on_device)
            self.method = pspyfiles.load_method_file(filename)

            self.log(f"Starting measurement using {os.path.basename(filename)}")
            measurement = self.manager.measure(self.method)

            if measurement is None or isinstance(measurement, str):
                raise RuntimeError(f"Invalid measurement: {measurement}")

            self.log("Measurement finished successfully.")
            try:
                os.remove(filename)
            except Exception as e:
                pass
            return self._process_measurement(measurement)

        except Exception as e:
            time.sleep(1)
            raise BufferError("Error occurred in measuring conductivity.")

    # ---------- Data Processing ----------

    def _process_measurement(self, measurement):
        """Extract resistance from EIS data."""
        real_arrays = []
        imag_arrays = []

        for i in range(len(measurement.freq_arrays[0])):
            freq = measurement.freq_arrays[0][i]
            if freq < FREQ_THRESHOLD:
                real_arrays.append(measurement.zre_arrays[0][i])
                imag_arrays.append(abs(measurement.zim_arrays[0][i]))

        slope, intercept = np.polyfit(real_arrays, imag_arrays, 1)
        result = abs(intercept / slope)

        self.log(f"Processed measurement: slope={slope}, intercept={intercept}, resistance={result:.4f} ohm")
        return result

    # ---------- File Utilities ----------

    def save_to_csv(self, measurement, directory="Results/Potentiostat"):
        """Save measurement data to CSV."""
        timestamp = sanitize_filename(datetime.now().isoformat())
        path = Path(directory) / f"{timestamp}.csv"
        path.parent.mkdir(parents=True, exist_ok=True)

        data = vars(measurement)
        df = {}
        for key, val in data.items():
            if isinstance(val, list) and len(val) > 0 and isinstance(val[0], list):
                df[key] = [round(x, SIGNIFICANT_DIGITS) for x in val[0]]
        pd.DataFrame(df).to_csv(path, index=False)
        self.log(f"Measurement saved to {path}")

    # ---------- Method File Generation ----------

def generate_psmethod_file(
    filename: str,
    mux_channel: int = 4,
    use_mux: bool = True,
    amplitude: float = 0.25,
    freq_min: float = 2.0e4,
    freq_max: float = 5.92e5,
    n_freq: int = 10,
    freq_type: int = 1,
    e_begin: float = 0.0,
    e_end: float = 0.0,
    e_step: float = 6e-5,
    scantype: int = 2,
    freq_mode: int = 0,
    pgstat_mode: int = 8,
    t_sampling: float = 0.5,
    t_maxeq: float = 5.0,
    pret_eachfreqscan: bool = False,
    t_interval: float = 0.1,
    t_run: float = 10.0,
    signal: int = 1,
    reaction: int = 2,
    save_on_device: bool = True,
):

    # Ensure directory exists
    

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    content = f"""#PSTrace 5.8.1704,unknown
#{timestamp}
#{filename}
#Method file version
METHOD_VERSION=1
#Technique and application
METHOD_ID=eis
TECHNIQUE=14
NOTES=
#Pretreatment and standby
E_COND=0.000E+000
T_COND=0.000E+000
E_DEP=0.000E+000
T_DEP=0.000E+000
T_EQUIL=0.000E+000
E_STBY=0.000E+000
T_STBY=0.000E+000
USE_STBY=False
#Peaks or levels
PEAK_HEIGHT_MIN=0.000E+000
PEAK_WIDTH_MIN=1.000E-001
PEAK_OVERLAP=0.000E+000
PEAK_WINDOW=1.000E-001
SMOOTH_LEVEL=0
#Current ranges
IRANGE_MIN_F=-3.000E+000
IRANGE_MAX_F=4.000E+000
IRANGE_START_F=4.000E+000
IRANGE_MIN=0
IRANGE_MAX=7
IRANGE_START=7
#Potential ranges
E_RANGE=3
E_RANGE_MIN=3
E_RANGE_MAX=3
#Auxiliary
EXTRA_VALUES_MSK=0
USE_STIRRER=False
IRANGE_BIPOT=3
E_BIPOT=0.000E+000
#Mux Settings
MUX_METHOD=0
USE_MUX_CH={mux_channel}
MUX_SETTINGS=0|{str(use_mux)}|True|False|False
MUX_NO_TIME_RESET=False
#Plot view
PLOT_BOTTOM=0.000E+000
PLOT_LEFT=0.000E+000
PLOT_RIGHT=0.000E+000
PLOT_TOP=0.000E+000
#Corrosion analysis
AREA=0.000E+000
DENSITY=0.000E+000
BA=0.000E+000
BC=0.000E+000
WEIGHT=0.000E+000
OCP_MODE=0
STAB_CRITERION=0.000E+000
T_OCP_MAX=1.000E+000
#Polypotentiostat
POLY_E=0.000|3|6|6,0.000|3|6|6,0.000|3|6|6,
POLY_MODE=0,0,0,
POLY_CALIB=0|0|0,0|0|0,0|0|0,
#Reference electrode
REF_ELECTRODE_NAME=
REF_ELECTRODE_OFFSET=0.000E+000
#Bipot
BIPOT_MODE=0
POLYSTATMODE=0
ISMAINWE=True
E_BIPOT_WE1_WE2=25
#IR Drop Compensation
USE_IR_DROP_COMP=False
IR_DROP_COMP_RES=1.000E+000
#Options
SAVE_ON_DEVICE={str(save_on_device)}
PGSTAT_MODE={pgstat_mode}
OVERRIDE_PGSTAT_MODE=False
SELECTED_PGSTAT_CHAN=0
OVERRIDE_POTENTIAL_RANGE=False
OVERRIDE_POTENTIAL_RANGE_MIN=0.000E+000
OVERRIDE_POTENTIAL_RANGE_MAX=0.000E+000
#Triggering
USE_TRIGGER_EQUIL=False
USE_TRIGGER_START=False
USE_TRIGGER_DELAY=False
TRIGGER_VALUE_EQUIL=0
TRIGGER_VALUE_START=0
TRIGGER_VALUE_DELAY=0
TRIGGER_DELAY_PERIOD=5.000E-001
#Method overrides
OVERRIDES=
#Impedance method parameters
E_BEGIN={e_begin:.3E}
E_STEP={e_step:.3E}
E_END={e_end:.3E}
AMPLITUDE={amplitude:.3E}
MAXHSTAB=False
#Impedance method generic parameters
SCANTYPE={scantype}
FREQTYPE={freq_type}
FREQ=1.000E+003
FREQ_MODE={freq_mode}
N_FREQ={n_freq}
MIN_FREQ={freq_min:.3E}
MAX_FREQ={freq_max:.3E}
T_SAMPLING={t_sampling:.3E}
T_MAXEQ={t_maxeq:.3E}
PRET_EACHFREQSCAN={str(pret_eachfreqscan)}
#Time method parameters
E={e_begin:.3E}
EOCP=NaN
T_INTERVAL={t_interval:.3E}
T_RUN={t_run:.3E}
VS_PREV_E=False
SIGNAL={signal}
REACTION={reaction}"""
    with open(filename, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"✅ Method file successfully written to {filename}")
    return filename

if __name__ == '__main__':
    generate_psmethod_file("filename.psmethod")