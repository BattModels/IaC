import os
import time
import numpy as np
import pandas as pd
from datetime import datetime
from pathlib import Path
import logging

from core.Instrument import Instrument, ConnectionType
from core.Resource import Resource
from Utils import RETRY_LIMIT, sanitize_filename, save_dict_to_json

from devices.pspython import pspyinstruments, pspymethods, pspyfiles
SIGNIFICANT_DIGITS = 8
FREQ_THRESHOLD = 1.5E5
CELL_CONSTANT = 10.0236965757
current_dir = os.path.dirname(os.path.abspath(__file__))
from core.Register import register_resource

def get_or_default(obj, attr, default):
    if obj is None:
        return default
    try:
        return getattr(obj, attr)
    except Exception as e:
        return default

@register_resource("potentiostat")
class Potentiostat(Instrument):
    """
    PalmSens potentiostat controller.
    Handles connection, EIS/conductivity measurement, and data processing.
    """

    def __init__(self, name: str, id, identifier: int, type_name, baud_rate: int = 9600, **kwargs):
        super().__init__(name=name, id=id, type_name=type_name, connection_type=ConnectionType.SERIAL,
                         identifier=identifier)
        self.instrument = None
        self.method = None
        self.baud_rate = baud_rate
        self.filename = None
        self.measurement = None
        self.conductivity = 0
        def new_data_callback(new_data):
                for type, value in new_data.items():
                    logging.info(type + ' = ' + str(value))
                return

        self.manager = pspyinstruments.InstrumentManager(new_data_callback=new_data_callback)
        self.filename = os.path.join(current_dir, 'pspython', 'COND_Ch=2.psmethod')
        self.method = pspyfiles.load_method_file(self.filename)


    # ---------- Core Methods ----------

    def create(self):
        """Connect to the PalmSens potentiostat."""
        available = pspyinstruments.discover_instruments()
        for device in available:
            lowercased_name = device.name.lower()
            if lowercased_name.startswith(self.name.lower()):
                self.instrument = device
                break

        if not self.instrument:
            self.status = Resource.Status.ERROR
            raise RuntimeError(f"Cannot find potentiostat {self.name}")

        try:
            
            success = self.manager.connect(self.instrument)
            if success == 1:
                self.status = Resource.Status.IN_USE
                self.log(f"Connected to {self.instrument.name}")
                return
        except Exception as e:
            self.status = Resource.Status.ERROR
            raise ConnectionError(f"Failed to connect to potentiostat {self.name}")

    def delete(self):
        """Disconnect the instrument safely."""
        try:
            os.remove(self.filename)
            self.filename = None
        except Exception as e:
            pass
        if self.manager and self.instrument:
            try:
                success = self.manager.disconnect()
                if success == 1:
                    self.status = Resource.Status.AVAILABLE
                    self.log(f"Disconnected from {self.instrument.name}")
                else:
                    raise RuntimeError("Error while disconnecting.")
            except Exception as e:
                self.status = Resource.Status.ERROR
                self.log(f"Error during disconnect: {e}", level="ERROR")
        self.status = Resource.Status.AVAILABLE

    # ---------- Measurement Logic ----------

    def update(self,
        
    notes: str = '',
    method_id: str = 'eis',
    # --- MUX ---
    #mux_channel: int = 4,
    #use_mux: bool = True,
    #mux_method: int = 0,
    #mux_no_time_reset: bool = False,

    # --- Corrosion Analysis ---
    area: float = 0,
    density: float = 0,
    ba: float = 0,
    bc: float = 0,
    weight: float = 0,
    ocp_mode: int = 0,
    stab_criterion: float = 0,
    t_ocp_max: float = 1,

    # --- Current Ranges ---
    irange_min: float = 0,
    irange_max: float = 7,
    irange_start: float = 7,

    # --- EIS Core ---
    eac: float = 0.25,
    iac: float = 0.01,
    freq_min: float = 2.0e4,
    freq_max: float = 5.92e5,
    n_freq: int = 10,
    freq_type: int = 1,
    freq_mode: int = 0,
    fixed_frequency: float = 1000,
    vs_prev_e: bool = True,

    # --- Potential Control ---
    e_begin: float = 0.0,
    e_end: float = 0.0,
    e_step: float = 6e-5,
    scantype: int = 2,

    # --- Potential Ranges ---
    erange_min: float = 3,
    erange_max: float = 3,
    erange_start: float = 3,

    # --- Timing ---
    t_sampling: float = 0.5,
    t_maxeq: float = 5.0,
    t_interval: float = 0.1,
    t_run: float = 10.0,

    # --- Pretreatment ---
    e_cond: float = 0.0,
    t_cond: float = 0.0,
    e_dep: float = 0.0,
    t_dep: float = 0.0,
    e_stby: float = 0.0,
    t_stby: float = 0.0,
    t_equil: float = 0.0,

    # --- Triggering ---
    use_trigger_on_delay: bool = False,
    use_trigger_on_equil: bool = False,
    use_trigger_on_start: bool = False,
    trigger_value_equil: float = 0,
    trigger_value_start: float = 0,
    trigger_value_delay: float = 0,
    trigger_delay_period: float = 0.5,

    # --- Peaks or levels ---
    peak_height_min: float = 0.0,
    peak_width_min: float = 0.1,
    peak_window: float = 0.1,

    pret_eachfreqscan: bool = False,

    # --- Reference electrode ---
    ref_electrode_name: str = '',
    ref_electrode_offset: float = 0,

    #IR Drop Compensation
    use_ir_drop_comp: bool = False,
    ir_drop_comp_res: float = 1,

    # --- bipot ---
    bipot_mode: int = 0,
    poly_stat_mode: int = 0,
    is_main_we: bool = True,
    #e_bipot_we1_we2: int = 25,

    # --- Auxiliary ---
    e_bipot: float = 0.0,
    extra_values_msk: int = 0,

    # --- Instrument / mode ---
    pgstat_mode: int = 8,
    signal: int = 1,
    reaction: int = 2,
    save_on_device: bool = True,
    override_pgstat_mode: bool = False,
    selected_pgstat_chan: bool = False,
    override_potential_range: bool = False,
    override_potential_range_min: float = 0.000E+000,
    override_potential_range_max: float = 0.000E+000
    ):
        """
        Perform a conductivity (EIS) measurement.
        Args:
            method_path: Path to the .psmethod file
        Returns:
            float: Computed resistance value (proxy for conductivity)
        """
        if not self.instrument:
            self.create()

        try:
            filename = "Temp.psmethod"
            
            self.filename = os.path.join(current_dir, filename)
            self.log(f"Loading method file: {self.filename}")
            generate_psmethod_file(
                self.filename,
                notes=notes,
                method_id=method_id,
                # --- MUX ---
                #mux_channel=mux_channel,
                #use_mux=use_mux,
                #mux_method=mux_method,
                #mux_no_time_reset=mux_no_time_reset,

                # --- Corrosion Analysis ---
                area=area,
                density=density,
                ba=ba,
                bc=bc,
                weight=weight,
                ocp_mode=ocp_mode,
                stab_criterion=stab_criterion,
                t_ocp_max=t_ocp_max,

                # --- Current Range ---
                irange_min=irange_min,
                irange_max=irange_max,
                irange_start=irange_start,

                # --- EIS core ---
                eac=eac,
                iac=iac,
                freq_min=freq_min,
                freq_max=freq_max,
                n_freq=n_freq,
                freq_type=freq_type,
                freq_mode=freq_mode,
                fixed_frequency=fixed_frequency,
                vs_prev_e=vs_prev_e,

                # --- Potential control ---
                e_begin=e_begin,
                e_end=e_end,
                e_step=e_step,
                scantype=scantype,

                # --- Current Range ---
                erange_min=erange_min,
                erange_max=erange_max,
                erange_start=erange_start,

                # --- Timing ---
                t_sampling=t_sampling,
                t_maxeq=t_maxeq,
                t_interval=t_interval,
                t_run=t_run,

                # --- Pretreatment ---
                e_cond=e_cond,
                t_cond=t_cond,
                e_dep=e_dep,
                t_dep=t_dep,
                e_stby=e_stby,
                t_stby=t_stby,
                t_equil=t_equil,

                # --- Triggering ---
                use_trigger_on_delay=use_trigger_on_delay,
                use_trigger_on_equil=use_trigger_on_equil,
                use_trigger_on_start=use_trigger_on_start,
                trigger_value_equil=trigger_value_equil,
                trigger_value_start=trigger_value_start,
                trigger_value_delay=trigger_value_delay,
                trigger_delay_period=trigger_delay_period,

                # --- Peaks or levels ---
                peak_height_min=peak_height_min,
                peak_width_min=peak_width_min,
                peak_window=peak_window,

                pret_eachfreqscan=pret_eachfreqscan,

                # --- Reference electrode ---
                ref_electrode_name=ref_electrode_name,
                ref_electrode_offset=ref_electrode_offset,

                #IR Drop Compensation
                use_ir_drop_comp=use_ir_drop_comp,
                ir_drop_comp_res=ir_drop_comp_res,

                # --- bipot ---
                bipot_mode=bipot_mode,
                poly_stat_mode=poly_stat_mode,
                is_main_we=is_main_we,
                #e_bipot_we1_we2=e_bipot_we1_we2,

                # --- Auxiliary ---
                e_bipot=e_bipot,
                extra_values_msk=extra_values_msk,

                # --- Instrument / mode ---
                pgstat_mode=pgstat_mode,
                signal=signal,
                reaction=reaction,
                save_on_device=save_on_device,
                override_pgstat_mode=override_pgstat_mode,
                selected_pgstat_chan=selected_pgstat_chan,
                override_potential_range=override_potential_range,
                override_potential_range_min=override_potential_range_min,
                override_potential_range_max=override_potential_range_max

            )

            self.desired_state = {'filename':self.filename, 
                'status':Resource.Status.IN_USE,
                'notes':notes,
                'method_id':method_id,
                # --- MUX ---
                #'mux_channel':mux_channel,
                #'use_mux':use_mux,
                #'mux_method':mux_method,
                #'mux_no_time_reset':mux_no_time_reset,

                # --- Corrosion Analysis ---
                'area':area,
                'density':density,
                'ba':ba,
                'bc':bc,
                'weight':weight,
                'ocp_mode':ocp_mode,
                'stab_criterion':stab_criterion,
                't_ocp_max':t_ocp_max,

                # --- Current Range ---
                'irange_min':irange_min,
                'irange_max':irange_max,
                'irange_start':irange_start,

                # --- EIS core ---
                'eac':eac,
                'iac':iac,
                'freq_min':freq_min,
                'freq_max':freq_max,
                'n_freq':n_freq,
                'freq_type':freq_type,
                'freq_mode':freq_mode,
                'fixed_frequency':fixed_frequency,
                'vs_prev_e':vs_prev_e,

                # --- Potential control ---
                'e_begin':e_begin,
                'e_end':e_end,
                'e_step':e_step,
                'scantype':scantype,

                # --- Current Range ---
                'erange_min':erange_min,
                'erange_max':erange_max,
                'erange_start':erange_start,

                # --- Timing ---
                't_sampling':t_sampling,
                't_maxeq':t_maxeq,
                't_interval':t_interval,
                't_run':t_run,

                # --- Pretreatment ---
                'e_cond':e_cond,
                't_cond':t_cond,
                'e_dep':e_dep,
                't_dep':t_dep,
                'e_stby':e_stby,
                't_stby':t_stby,
                't_equil':t_equil,

                # --- Triggering ---
                'use_trigger_on_delay':use_trigger_on_delay,
                'use_trigger_on_equil':use_trigger_on_equil,
                'use_trigger_on_start':use_trigger_on_start,
                'trigger_value_equil':trigger_value_equil,
                'trigger_value_start':trigger_value_start,
                'trigger_value_delay':trigger_value_delay,
                'trigger_delay_period':trigger_delay_period,

                # --- Peaks or levels ---
                'peak_height_min':peak_height_min,
                'peak_width_min':peak_width_min,
                'peak_window':peak_window,

                'pret_eachfreqscan':pret_eachfreqscan,

                # --- Reference electrode ---
                'ref_electrode_name':ref_electrode_name,
                'ref_electrode_offset':ref_electrode_offset,

                #IR Drop Compensation
                'use_ir_drop_comp':use_ir_drop_comp,
                'ir_drop_comp_res':ir_drop_comp_res,

                # --- bipot ---
                'bipot_mode':bipot_mode,
                'poly_stat_mode':poly_stat_mode,
                'is_main_we':is_main_we,
                #'e_bipot_we1_we2':e_bipot_we1_we2,

                # --- Auxiliary ---
                'e_bipot':e_bipot,
                'extra_values_msk':extra_values_msk,

                # --- Instrument / mode ---
                'pgstat_mode':pgstat_mode,
                'signal':signal,
                'reaction':reaction,
                'save_on_device':save_on_device,
                'override_pgstat_mode':override_pgstat_mode,
                'selected_pgstat_chan':selected_pgstat_chan,
                'override_potential_range':override_potential_range,
                'override_potential_range_min':override_potential_range_min,
                'override_potential_range_max':override_potential_range_max}
            self.method = pspyfiles.load_method_file(self.filename)
            self.log(f"Starting measurement using {os.path.basename(self.filename)}")
                
            self.measurement = self.manager.measure(self.method)
            if self.measurement is None or isinstance(self.measurement, str):
                raise RuntimeError(f"Invalid measurement: {self.measurement}")

            self.log("Measurement finished successfully.")
            resistance = self._process_measurement(self.measurement)
            self.conductivity = 1000 * CELL_CONSTANT / resistance
            
        except Exception as e:
            time.sleep(1)
            raise BufferError("Error occurred in measuring conductivity.")
        
    def read(self):
        
        super().read()
        self.update_actual_state()
        return {'state_diff':self.diff(), 'conductivity':self.conductivity, 'measurement':self.measurement, 
                'state':{'status':self.actual_state['status'], 
                         'method_id':self.actual_state['method_id'],
                         'freq_min':self.actual_state['freq_min'],
                         'freq_max':self.actual_state['freq_max'],
                         'n_freq':self.actual_state['n_freq'],
                         'conductivity':self.conductivity}}
    
    def update_actual_state(self) -> dict:
        """
        Update and return the full instrument actual_state:
        A) Connection state
        B) Measurement lifecycle state
        C) Live electrochemical signals
        """

        self.actual_state = {'filename':self.filename, 
                'status':self.status,
                'notes':self.method.Notes,
                'method_id':self.method.MethodID,
                # --- MUX ---
                #'mux_channel':mux_channel,
                #'use_mux':use_mux,
                #'mux_method':self.method.MuxMethod,
                #'mux_no_time_reset':self.method.MuxNoTimeResetForNextChannel,

                # --- Corrosion Analysis ---
                'area':self.method.Area,
                'density':self.method.Density,
                'ba':self.method.Ba,
                'bc':self.method.Bc,
                'weight':self.method.Weight,
                'ocp_mode':self.method.OCPmode,
                'stab_criterion':self.method.OCPStabilityCriterion,
                't_ocp_max':self.method.OCPMaxOCPTime,

                # --- Current Range ---
                'irange_min':self.method.Ranging.get_MinimumCurrentRange().CRbyte,
                'irange_max':self.method.Ranging.get_MaximumCurrentRange().CRbyte,
                'irange_start':self.method.Ranging.get_StartCurrentRange().CRbyte,

                # --- EIS core ---
                'eac':get_or_default(self.method, 'Eac', 0),
                'iac':get_or_default(self.method, 'Iac', 0),
                'edc':get_or_default(self.method, 'Edc', 0),
                'idc':get_or_default(self.method, 'Idc', 0),
                'freq_min':self.method.MinFrequency,
                'freq_max':self.method.MaxFrequency,
                'n_freq':self.method.nFrequencies,
                'freq_type':self.method.FreqType,
                'freq_mode':self.method.FrequencyMode,
                'fixed_frequency':self.method.FixedFrequency,
                'vs_prev_e':self.method.VsPrevEI,

                # --- Potential control ---
                'e_begin':get_or_default(self.method, 'BeginPotential', 0),
                'e_end':get_or_default(self.method, 'EndPotential', 0),
                'e_step':get_or_default(self.method, 'StepPotential', 0),

                # --- Current control ---
                'i_begin':get_or_default(self.method, 'BeginCurrent', 0),
                'i_end':get_or_default(self.method, 'EndCurrent', 0),
                'i_step':get_or_default(self.method, 'StepCurrent', 0),

                'scantype':self.method.ScanType,

                # --- Potential Range ---
                'erange_min':self.method.RangingPotential.get_MinimumPotentialRange().get_PR().value__,
                'erange_max':self.method.RangingPotential.get_MaximumPotentialRange().get_PR().value__,
                'erange_start':self.method.RangingPotential.get_StartPotentialRange().get_PR().value__,

                # --- Timing ---
                't_sampling':self.method.SamplingTime,
                't_maxeq':self.method.MaxEqTime,
                't_interval':self.method.IntervalTime,
                't_run':self.method.RunTime,

                # --- Pretreatment ---
                'e_cond':self.method.ConditioningPotential,
                't_cond':self.method.ConditioningTime,
                'e_dep':self.method.DepositionPotential,
                't_dep':self.method.DepositionTime,
                'e_stby':self.method.StandbyPotential,
                't_stby':self.method.StandbyTime,
                't_equil':self.method.EquilibrationTime,

                # --- Triggering ---
                'use_trigger_on_delay':self.method.UseTriggerOnDelay,
                'use_trigger_on_equil':self.method.UseTriggerOnEquil,
                'use_trigger_on_start':self.method.UseTriggerOnStart,
                'trigger_value_equil':self.method.TriggerValueOnEquil,
                'trigger_value_start':self.method.TriggerValueOnStart,
                'trigger_value_delay':self.method.TriggerValueOnDelay,
                'trigger_delay_period':self.method.TriggerDelayPeriod,

                # --- Peaks or levels ---
                'peak_height_min':self.method.MinPeakHeight,
                'peak_width_min':self.method.MinPeakWidth,
                'peak_window':self.method.PeakWindow,

                'pret_eachfreqscan':self.method.PretreatEachScan,

                # --- Reference electrode ---
                'ref_electrode_name':self.method.ReferenceElectrodeName,
                'ref_electrode_offset':self.method.ReferenceElectrodeOffset,

                #IR Drop Compensation
                'use_ir_drop_comp':self.method.UseIRDropComp,
                'ir_drop_comp_res':self.method.IRDropCompRes,

                # --- bipot ---
                'bipot_mode':self.method.BipotModePS,
                'poly_stat_mode':self.method.PolyStatMode,
                'is_main_we':self.method.IsMainWE,
                'e_bipot_we1_we2':self.method.BiPotPotential,

                # --- Auxiliary ---
                'e_bipot':self.method.BiPotPotential,
                'extra_values_msk':self.method.ExtraValueMsk,

                # --- Instrument / mode ---
                'pgstat_mode':self.method.PGStatMode,
                'signal':self.method.Signal,
                'reaction':self.method.Reaction,
                'save_on_device':self.method.SaveOnDevice,
                'override_pgstat_mode':self.method.OverridePGStatMode,
                'selected_pgstat_chan':self.method.SelectedPotentiostatChannel,
                'override_potential_range':self.method.OverridePotentialRange,
                'override_potential_range_min':self.method.OverridePotentialRangeMin,
                'override_potential_range_max':self.method.OverridePotentialRangeMax}
        

        self.actual_state["connected"] = self.instrument is not None
        return self.actual_state

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
    notes: str = '',
    method_id: str = 'eis',
    # --- MUX ---
    #mux_channel: int = 4,
    #use_mux: bool = True,
    #mux_method: int = 0,
    #mux_no_time_reset: bool = False,

    # --- Corrosion Analysis ---
    area: float = 0,
    density: float = 0,
    ba: float = 0,
    bc: float = 0,
    weight: float = 0,
    ocp_mode: int = 0,
    stab_criterion: float = 0,
    t_ocp_max: float = 1,

    # --- Current Ranges ---
    irange_min: float = 0,
    irange_max: float = 7,
    irange_start: float = 7,

    # --- EIS Core ---
    eac: float = 0.25,
    edc: float = 0,
    iac: float = 0.01,
    idc: float = 0,
    freq_min: float = 2.0e4,
    freq_max: float = 5.92e5,
    n_freq: int = 10,
    freq_type: int = 1,
    freq_mode: int = 0,
    fixed_frequency: float = 1000,
    vs_prev_e: bool = True,

    # --- Potential Control ---
    e_begin: float = 0.0,
    e_end: float = 0.0,
    e_step: float = 6e-5,
    scantype: int = 2,

    # --- Potential Ranges ---
    erange_min: float = 3,
    erange_max: float = 3,
    erange_start: float = 3,

    # --- Timing ---
    t_sampling: float = 0.5,
    t_maxeq: float = 5.0,
    t_interval: float = 0.1,
    t_run: float = 10.0,

    # --- Pretreatment ---
    e_cond: float = 0.0,
    t_cond: float = 0.0,
    e_dep: float = 0.0,
    t_dep: float = 0.0,
    e_stby: float = 0.0,
    t_stby: float = 0.0,
    t_equil: float = 0.0,

    # --- Triggering ---
    use_trigger_on_delay: bool = False,
    use_trigger_on_equil: bool = False,
    use_trigger_on_start: bool = False,
    trigger_value_equil: float = 0,
    trigger_value_start: float = 0,
    trigger_value_delay: float = 0,
    trigger_delay_period: float = 0.5,

    # --- Peaks or levels ---
    peak_height_min: float = 0.0,
    peak_width_min: float = 0.1,
    peak_window: float = 0.1,

    pret_eachfreqscan: bool = False,

    # --- Reference electrode ---
    ref_electrode_name: str = '',
    ref_electrode_offset: float = 0,

    #IR Drop Compensation
    use_ir_drop_comp: bool = False,
    ir_drop_comp_res: float = 1,

    # --- bipot ---
    bipot_mode: int = 0,
    poly_stat_mode: int = 0,
    is_main_we: bool = True,
    #e_bipot_we1_we2: int = 25,

    # --- Auxiliary ---
    e_bipot: float = 0.0,
    extra_values_msk: int = 0,

    # --- Instrument / mode ---
    pgstat_mode: int = 8,
    signal: int = 1,
    reaction: int = 2,
    save_on_device: bool = True,
    override_pgstat_mode: bool = False,
    selected_pgstat_chan: bool = False,
    override_potential_range: bool = False,
    override_potential_range_min: float = 0.000E+000,
    override_potential_range_max: float = 0.000E+000
):

    # Ensure directory exists
    

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    content = f"""#PSTrace 5.8.1704,unknown
#{timestamp}
#{filename}
#Method file version
METHOD_VERSION=1
#Technique and application
METHOD_ID={method_id}
NOTES={notes}
#Pretreatment and standby
E_COND={e_cond:.3E}
T_COND={t_cond:.3E}
E_DEP={e_dep:.3E}
T_DEP={t_dep:.3E}
T_EQUIL={t_equil:.3E}
E_STBY={e_stby}
T_STBY={t_stby}
USE_STBY=False
#Peaks or levels
PEAK_HEIGHT_MIN={peak_height_min}
PEAK_WIDTH_MIN={peak_width_min}
PEAK_WINDOW={peak_window}
SMOOTH_LEVEL=0
#Current ranges
IRANGE_MIN_F={irange_min - 3}
IRANGE_MAX_F={irange_max - 3}
IRANGE_START_F={irange_start - 3}
IRANGE_MIN={irange_min}
IRANGE_MAX={irange_max}
IRANGE_START={irange_start}
#Potential ranges
E_RANGE={erange_start}
E_RANGE_MIN={erange_min}
E_RANGE_MAX={erange_max}
#Auxiliary
EXTRA_VALUES_MSK={extra_values_msk}
USE_STIRRER=False
E_BIPOT={e_bipot}

#Corrosion analysis
AREA={area}
DENSITY={density}
BA={ba}
BC={bc}
WEIGHT={weight}
OCP_MODE={ocp_mode}
STAB_CRITERION={stab_criterion}
T_OCP_MAX={t_ocp_max}
#Polypotentiostat
POLY_E=0.000|3|6|6,0.000|3|6|6,0.000|3|6|6,
POLY_MODE=0,0,0,
POLY_CALIB=0|0|0,0|0|0,0|0|0,
#Reference electrode
REF_ELECTRODE_NAME={ref_electrode_name}
REF_ELECTRODE_OFFSET={ref_electrode_offset}
#Bipot
BIPOT_MODE={bipot_mode}
POLYSTATMODE={poly_stat_mode}
ISMAINWE={is_main_we}
#E_BIPOT_WE1_WE2=
#IR Drop Compensation
USE_IR_DROP_COMP={use_ir_drop_comp}
IR_DROP_COMP_RES={ir_drop_comp_res}
#Options
SAVE_ON_DEVICE={str(save_on_device)}
PGSTAT_MODE={pgstat_mode}
OVERRIDE_PGSTAT_MODE={override_pgstat_mode}
SELECTED_PGSTAT_CHAN={selected_pgstat_chan}
OVERRIDE_POTENTIAL_RANGE={override_potential_range}
OVERRIDE_POTENTIAL_RANGE_MIN={override_potential_range_min}
OVERRIDE_POTENTIAL_RANGE_MAX={override_potential_range_max}
#Triggering
USE_TRIGGER_EQUIL={use_trigger_on_equil}
USE_TRIGGER_START={use_trigger_on_start}
USE_TRIGGER_DELAY={use_trigger_on_delay}
TRIGGER_VALUE_EQUIL={trigger_value_equil}
TRIGGER_VALUE_START={trigger_value_start}
TRIGGER_VALUE_DELAY={trigger_value_delay}
TRIGGER_DELAY_PERIOD={trigger_delay_period}
#Method overrides
OVERRIDES=
#Impedance method parameters
E_BEGIN={e_begin:.3E}
E_STEP={e_step:.3E}
E_END={e_end:.3E}
AMPLITUDE={eac:.3E}
I_BEGIN=3.000E-002
I_STEP=1.000E-002
I_END=1.000E+000
IAMPLITUDE={iac}
MAXHSTAB=False
#Impedance method generic parameters
SCANTYPE={scantype}
FREQTYPE={freq_type}
FREQ={fixed_frequency}
FREQ_MODE={freq_mode}
N_FREQ={n_freq}
MIN_FREQ={freq_min:.3E}
MAX_FREQ={freq_max:.3E}
T_SAMPLING={t_sampling:.3E}
T_MAXEQ={t_maxeq:.3E}
PRET_EACHFREQSCAN={str(pret_eachfreqscan)}
#Time method parameters
E={edc:.3E}
EOCP=NaN
T_INTERVAL={t_interval:.3E}
T_RUN={t_run:.3E}
VS_PREV_E={vs_prev_e}
SIGNAL={signal}
REACTION={reaction}"""
    with open(filename, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"✅ Method file successfully written to {filename}")
    return filename



if __name__ == '__main__':
    potentiostat = Potentiostat("Potentiostat", 1, 8, Potentiostat)
    potentiostat.create()