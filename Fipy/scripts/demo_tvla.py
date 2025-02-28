import datetime
from time import time, sleep
from pathlib import Path
import numpy

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from trsfile import Header, SampleCoding, Trace, TracePadding, trs_open

from trsfile.standardparameters import (
    StandardTraceParameters,
    StandardTraceSetParameters,
)
from trsfile.parametermap import TraceParameterMap
from fipy.device.dummy.scope import DummyScope
from fipy.device.xyz_table import XYZPosition

from fipy.parameters import *
from fipy.sabuild.tools.trace import (
    parameters_add_xyz,
    trace_params_add_tvla,
    trace_params_from_scope,
)
from fipy.scriptutils import ResultColor, fipy_script, Util

from fipy.device.lecroyscope import LecroyScope
from fipy.transformutil import TransformUtil


# Comment out channels you don't want to measure.
CHANNELS_ENABLED = [
    # 'C1',
    "C2",
    # 'C3',
    # 'C4',
]

IN_BYTES = 16
KEY_BYTES = 16

# tu needs to global as it is needed for the PARAMETERS, as well as the script
tu = TransformUtil()


def make_select_bool(name: str, true="yes", false="no"):
    return SelectionParameter(name, options={True: true, False: false}, param_type=bool)


PARAMETERS = Parameters(
    ("tvla_dual_state", make_select_bool("TVLA Semi-Constant Dual State")),
    ("scans", AttemptsParameter("Scans")),
    ("xyz_scanner", MaskedXYZScanParameter("XYZ scanner", transformutil=tu)),
    ("scope_enabled", make_select_bool("Scope is ", "enabled", "disabled")),
    ("lecroy_ip", StringParameter("Lecroy IP")),
    ("attempts", AttemptsParameter("Attempts per spot")),
    ("move_table", make_select_bool("Move table")),
)


@fipy_script
def execute_script(util: Util):
    util.set_termination_timeout(5)
    util.parameter_init(PARAMETERS)

    script_name = Path(__file__).stem
    db = util.create_database_table(f"logs/{script_name}.sqlite", script_name)
    util.add_to_cleanup(util.close_database)

    PROJECT_DIR = util.fipy_args["project_dir"]
    METADATA_PATH = PROJECT_DIR / "metadata"
    TRACE_PATH = PROJECT_DIR / "traces"

    if PARAMETERS["tvla_dual_state"]:
        # TVLA semi-constant dual state

        # TVLA input, import from a file. This file is generated using SABuild module "GenerateData" with the following options:
        # - generator = "TVLA Block Cipher Semi-constant (dual state)"
        # - "Only generate semi-constant TVLA data" = enabled
        # - "Number of targeted intermediate states" = 1
        # If other generators or options are used, the flow below will need to be adapted.
        tvla_data_filename = METADATA_PATH / "10k_aes_dec_hw_r5_0-7_dual_state"
        tvla_data_len = IN_BYTES + KEY_BYTES  # Input + Key
    else:
        AES_ROOT_KEY = "bb6b34f6a4eb3b285098186c60650d91"
        TEST_INPUT_AES_ROOT_KEY = bytes.fromhex(AES_ROOT_KEY)
        key = TEST_INPUT_AES_ROOT_KEY

        # TVLA input, import from a file. This file is generated using SABuild module "GenerateData" with the following options:
        # - generator = "TVLA Block Cipher Semi-constant" (not the dual-state)
        # - "Only generate semi-constant TVLA data" = enabled
        # - "Number of targeted intermediate states" = 1
        # If other generators or options are used, the flow below will need to be adapted.
        tvla_data_filename = METADATA_PATH / f"10k_aes_dec_hw_r5_0-7_key_{AES_ROOT_KEY}"
        tvla_data_len = IN_BYTES  # Input only

    # TODO read from file during sampling
    # Reading in input binary, generated from GenerateData module in inspector
    with open(tvla_data_filename, "rb") as f:
        tvla_data = f.read()  # 10M input = ~153MB
        f.close()
    num_tvla_input = int(len(tvla_data) / tvla_data_len)
    print(
        f"Read TVLA input data {len(tvla_data)} bytes {num_tvla_input} blocks of {tvla_data_len} bytes in total"
    )

    # XYZ
    xyz_interface = util.get_xyz()
    tu.add_system("table", xyz_interface.get_reference_points())

    # Scope
    scope = None
    traceset = None
    num_segments = 1
    num_samples = 0

    scope_enabled = bool(PARAMETERS["scope_enabled"])
    if scope_enabled:
        # scope = LecroyScope (
        scope = DummyScope(
            str(PARAMETERS["lecroy_ip"]),
            # recall_default=bool(PARAMETERS['recall_default']),
            recall_default=False,
            timeout_ms=4000,
        )
        util.add_to_cleanup(scope.close)

        # Stop any operation that might still be running.
        scope.stop()

        # Read lecroy configuration into local variables
        num_segments = scope.num_segments()

        parameter_map = trace_params_from_scope(scope)

        trace_params_add_tvla(parameter_map, tvla_data_filename, num_tvla_input)

        if not PARAMETERS["tvla_dual_state"]:
            parameter_map.add_standard_parameter(StandardTraceSetParameters.KEY, key)

        if bool(PARAMETERS["move_table"]):
            parameters_add_xyz(
                parameter_map, PARAMETERS["xyz_scanner"], PARAMETERS["attempts"]
            )

        headers = {
            Header.SAMPLE_CODING: SampleCoding.BYTE,
            Header.TRACE_SET_PARAMETERS: parameter_map,
        }

        # About live_update=0: this is way faster than a value > 0 here, but it
        # also means that the file is corrupted if not closed correctly. This is
        # purely a header issue and can be fixed easily, for example by using
        # Inspector's "Recover".
        ts_filename = datetime.datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
        traceset = trs_open(
            engine="TrsEngine",
            live_update=0,
            headers=headers,
            path=TRACE_PATH / f"{ts_filename}.trs",
            mode="w",
            padding_mode=TracePadding.AUTO,
        )
        util.add_to_cleanup(traceset.close)

    counter = 0
    color = ResultColor.GREEN
    trace_count = 0
    debug = True

    if not PARAMETERS["tvla_dual_state"]:  # single state, fixed key
        cipher = Cipher(algorithms.AES(key), modes.ECB(), default_backend())

    tvla_counter = 0

    for p in PARAMETERS:
        t = time()

        scope_enabled = bool(p["scope_enabled"])

        if not util.process_commands():
            if scope_enabled:
                scope.stop()
            break

        if counter == 20:
            print("Debug finished")
            debug = False

        if debug:
            print(f"=========== counter = {counter} ===========")

        move_table = bool(p["move_table"])
        if move_table:
            chip_pos = p["xyz_scanner"]
            table_pos = tu.from_chip("table", chip_pos)
            xyz_interface.move_abs(
                table_pos.x, table_pos.y, table_pos.z, hop_height=500
            )
        else:  # get current position, do not move
            pos = xyz_interface.get_current_position()
            table_pos = XYZPosition(pos[0], pos[1], pos[2])
            chip_pos = tu.to_chip("table", table_pos)

        data_good = True

        cmd = b""

        # set data n stage
        tvla_group = numpy.random.randint(0, 2)  # 0 or 1

        if tvla_group == 0:
            # first block tvla input
            data = tvla_data[
                tvla_counter * tvla_data_len : (tvla_counter + 1) * tvla_data_len
            ]
            if debug:
                print("data:", tvla_counter, len(data), data.hex())
            tvla_counter = (tvla_counter + 1) % num_tvla_input

            if PARAMETERS["tvla_dual_state"]:
                key = data[KEY_BYTES:]

            input_data = data[:IN_BYTES]

        elif tvla_group == 1:
            input_data = numpy.random.bytes(IN_BYTES)
            if PARAMETERS["tvla_dual_state"]:
                key = numpy.random.bytes(KEY_BYTES)

        assert len(input_data) == IN_BYTES, "wrong data length"

        # update the key if necessary
        if PARAMETERS["tvla_dual_state"]:
            cipher = Cipher(algorithms.AES(key), modes.ECB(), default_backend())

        # decrypt multiple block
        exp = cipher.decryptor().update(input_data)

        if scope_enabled:
            scope.arm()
            scope.check_if_done()
        # send to device the input data, receives output. Since we don't have a device here, set output to exp.
        output = exp

        data_good = output == exp

        if debug or not data_good:
            print("input:", input_data.hex())
            print("key:", key)
            print("output:", output.hex())
            print("expected:", exp.hex())
            print("data_good:", data_good)

        color = ResultColor.GREEN if data_good else ResultColor.RED
        if scope_enabled:
            for channel in CHANNELS_ENABLED:
                samples, num_samples = scope.read_trace(channel, arm=False)

                if num_samples % num_segments != 0:
                    print(
                        f"num_samples ({num_samples}) not a multiple of num_segments ({num_segments})! Counter = {counter}"
                    )

                if not data_good:
                    print(f"returned data not good, id={counter} not added")
                elif samples == None:
                    print(f"no samples returned, id={counter} not added")
                    scope.force_trigger()
                    scope.stop()
                    sleep(1)

                    color = ResultColor.ORANGE
                elif samples:
                    trace_params = TraceParameterMap()
                    trace_params.add_standard_parameter(
                        StandardTraceParameters.INPUT, input_data[:IN_BYTES]
                    )
                    trace_params.add_standard_parameter(
                        StandardTraceParameters.OUTPUT, output[:IN_BYTES]
                    )
                    if PARAMETERS["tvla_dual_state"]:
                        trace_params.add_standard_parameter(
                            StandardTraceParameters.KEY, key
                        )
                    trace_params.add_standard_parameter(
                        StandardTraceParameters.TVLA_SET_INDEX, tvla_group
                    )

                    for segment in range(num_segments):
                        # Store each segment as a separate trace in the tracefile
                        title = []
                        if move_table:
                            title.append(f"({chip_pos.x:.1f}-{chip_pos.y:.1f})")
                        title.append(f"{channel}-{counter}")
                        if num_segments > 1:
                            title.append(f"{num_segments}")

                        segment_samples = samples[
                            segment
                            * (num_samples // num_segments) : (segment + 1)
                            * (num_samples // num_segments)
                        ]

                        trace = Trace(
                            SampleCoding.BYTE,
                            segment_samples,
                            parameters=trace_params,
                            title="-".join(title),
                        )

                        traceset.append(trace)
                        trace_count += 1

                    if debug:
                        print(f"Collected {trace_count} traces")
                else:
                    print("something is wrong. traces not added.")
                    color = ResultColor.YELLOW

        iter_t_ms = int((time() - t) * 1000)
        result = Parameters(
            ("id", counter),
            ("timestamp", int(t)),
            ("iter_t", iter_t_ms),
            ("scan", p["scans"]),
            ("x", float(chip_pos.x)),
            ("y", float(chip_pos.y)),
            ("z", float(chip_pos.z)),
            ("tvla_group", tvla_group),
            ("trace_count", trace_count),
            ("Data", cmd),
            ("Key", key),
            ("Color", int(color)),
        )

        util.monitor(result)

        # We don't expect broken output, so lower commit frequency
        # for speed.
        db.add(result, commit_frequency=32)

        counter += 1
