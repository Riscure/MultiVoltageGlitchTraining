'''This script demonstrates how the VCGlitcher can be used to communicate with a smartcard, how to
parse its output and how to generate VCC glitches. We use the Transparent VCGlitcer implementation
(``tvcg``) to read out an ATR once, and then use the VCGlitcher CPU programming to perform the
attack sequence. This sequence is built in the ``create_vcg_program`` function.

To setup this demo you need:

1. VCGlitcher
2. Training Card 6
3. Optionally an oscilloscope

Signals that are interesting to observe from the oscilloscope:

* trigger out - This is used to trigger the pattern generator
* I/O
* vcc
* reset

To build this setup:

* Insert TC6 in the VCGlitcher
'''


from time import sleep, time
from pathlib import Path

import os

from fipy.parameters import *
from fipy.scriptutils import ResultColor, fipy_script
from fipy.device.vcglitcher import *
from fipy.protocols.smartcard import *


PARAMETERS = Parameters(
    ('atr', StringParameter('ATR')),
    ('attempts', AttemptsParameter('Attempts')),
    ('glitch_delay', IntParameter('Glitch delay', unit='ns')),
    ('glitch_length', IntParameter('Glitch length', unit='ns')),
    ('glitch_voltage', FloatParameter('Glitch voltage', unit='V')),
    ('normal_voltage', FloatParameter('Normal voltage', unit='V')),
    ('cmd_logging', SelectionParameter('Command logging',
        options={True: 'enabled',
            False: 'disabled'},
        param_type=bool)),
)

ADDR_SKIP_RESET  = 0x00
ADDR_LENGTH_ATR  = 0x10
ADDR_LENGTH_CMD  = 0x11
ADDR_LENGTH_RESP = 0x12

def create_vcg_program(cmd_logging):
    vcg_program = VCGlitcherProgram()
    vcg_program.loadm(REG.R0, ADDR_SKIP_RESET)
    vcg_program.cmpz(REG.R0)
    vcg_program.branch0(b"SKIP_RESET")
    # Configure the communication speeds
    vcg_program.loadi(REG.R0, vcg_program.get_tx_inc(BAUD.SPEED_4MHZ))
    vcg_program.loadi(REG.R1, vcg_program.get_rx_inc(BAUD.SPEED_4MHZ))
    vcg_program.txconfig(REG.R0)
    vcg_program.rxconfig(REG.R1)
    # Reset using the reset line
    vcg_program.set_signal(SET.LOGGER_EN, 1)
    vcg_program.set_signal(SET.TRIGGER_OUT, 0)
    vcg_program.set_signal(SET.SC_RST, 0)
    vcg_program.wait_cycles(10000)
    vcg_program.set_signal(SET.SC_RST, 1)
    # Wait to receive ATR
    vcg_program.get_bytes(ADDR_LENGTH_ATR, is_address=True)
    vcg_program.add_label(b"SKIP_RESET")
    # Write command from fifo and toggle trigger to trigger pattern
    if not cmd_logging:
        vcg_program.set_signal(SET.LOGGER_EN, 0)
    vcg_program.send_bytes(ADDR_LENGTH_CMD, is_address=True)
    vcg_program.set_signal(SET.TRIGGER_OUT, 1)
    if not cmd_logging:
        vcg_program.set_signal(SET.LOGGER_EN, 1)
    # Try to read at least the amount of expected bytes
    vcg_program.get_bytes(ADDR_LENGTH_RESP, is_address=True)
    vcg_program.set_signal(SET.TRIGGER_OUT, 0)
    vcg_program.end()
    return vcg_program

def read_one_atr(vcg):
    print('Doing a reset to read out ATR')
    vcg.tvcg_start()
    vcg.tvcg_smartcard_baudrate_update(BAUD.SPEED_4MHZ)
    vcg.tvcg_smartcard_reset()
    sleep(.1)
    atr_bytes = vcg.tvcg_read(0)
    print('Trying to parse ATR:')
    try:
        parsed_atr = ATR(atr_bytes)
        print('\t' + '\n\t'.join(parsed_atr.dump()))
        print('Use this string for ATR: "{}"'.format(atr_bytes.hex()))
    except Exception as e:
        print('Could not parse ATR:')
        print(repr(e))
    raise Exception('Need an ATR to start the script, see console for more info')

@fipy_script
def execute_script(util):
    util.set_termination_timeout(5)
    util.parameter_init(PARAMETERS)

    script_name = Path(__file__).stem
    db = util.create_database_table('logs/{}.sqlite'.format(script_name), script_name)
    util.add_to_cleanup(util.close_database)

    # Set up connection with the vcglitcher
    vcg = VCGlitcher()
    device_count = vcg.device_list()
    if device_count != 1:
        raise Exception('Invalid amount of VCGlitchers detecter {}'.format(device_count))
    vcg.device_get_info(0)
    vcg.open()
    print(vcg.get_version())
    util.add_to_cleanup(vcg.pattern_disable)

    # Set up VCGlitcher for embedded laser/emfi
    vcg.smartcard_set_clock_speed(CLK.SPEED_4MHZ)
    # vcg.set_mode(GLITCH_MODE.EMBEDDED_LASER)
    # vcg.set_laser_glitch_parameter(v_amplitude=0, v_vcc_clk=int(PARAMETERS['normal_voltage'])) # v_amplitude from -9.8 to 4.2
    vcg.set_mode(GLITCH_MODE.EMBEDDED_VCC)
    v_normal = int(PARAMETERS['normal_voltage'])
    # v_glitch gets added to v_normal
    vcg.set_vcc_glitch_parameter(v_vcc=v_normal, v_clk=v_normal, v_glitch=0)
    # need to load any pattern for the VCGlitcher to work, we don't use this functionality though
    vcg.pattern_load([0])
    vcg.pattern_enable()

    vcg.set_read_timeout(1000)

    atr = str(PARAMETERS['atr'])

    if not atr:
        # Perform one reset to read ATR and stop script
        read_one_atr(vcg)

    # configure the trigger source for the glitch pattern
    vcg.evcg_trigger_config(EVCG_TRIGGER_SRC.TRIGGER_OUT, EVCG_TRIGGER_EDGE.RISING)
    vcg.set_smartcard_soft_reset(False)
    vcg.set_program(create_vcg_program(bool(PARAMETERS['cmd_logging'])))

    vcg.cpu_stop()

    # Parse ATR and create a T=1 protocol instance
    atr  = bytes.fromhex(atr)
    parsed_atr = ATR(atr)
    print(parsed_atr.protocols[0])
    assert parsed_atr.protocols[0].name == 'T=1'
    teq1 = TEQ1(parsed_atr.protocols[0].ifsc)
    teq1.reset()

    resp_expected = bytes.fromhex('6985')
    # Four protocol bytes will be added in T=1
    resp_len_expected = 3 + len(resp_expected) + 1

    counter = 0
    skip_reset = 0

    for p in PARAMETERS:
        vcg_timeout = False
        t = time()
        if not util.process_commands():
            break

        vcg.set_vcc_glitch_parameter(v_vcc=v_normal, v_clk=v_normal, v_glitch=p['glitch_voltage'])

        # Verify PIN
        # tpdu = teq1.command(bytes.fromhex('A0 17 0000 04 00000000 00'))
        tpdu = teq1.build_command(cls=0xA0, ins=0x17, data=b'\x00'*4)

        vcg.memory_write(ADDR_SKIP_RESET, skip_reset)
        vcg.memory_write(ADDR_LENGTH_ATR, len(atr))
        vcg.memory_write(ADDR_LENGTH_CMD, len(tpdu))
        vcg.memory_write(ADDR_LENGTH_RESP, resp_len_expected)

        # Put the command in the fifo
        vcg.smartcard_fifo_write(tpdu)
        # Configure and arm the glitch pattern
        vcg.evcg_clear_pattern()
        # Provide multiples of 2ns
        vcg.evcg_add_pattern(p['glitch_delay'] // 2, p['glitch_length'] // 2)
        vcg.evcg_set_pattern()
        vcg.evcg_set_arm(True)
        # Run the vcg program
        vcg.cpu_start()

        t0 = time()
        while(not vcg.is_cpu_stopped()):
            if time() - t0 > 2:
                vcg_timeout = True
                break

        data = b''
        card_atr = b''
        card_tpdu = b''
        card_resp = b''

        if not skip_reset:
            card_atr = bytes(vcg.smartcard_fifo_read(len(atr)))
            data += card_atr
            skip_reset = 1

        if bool(PARAMETERS['cmd_logging']):
            card_tpdu = bytes(vcg.smartcard_fifo_read(len(tpdu)))
            data += card_tpdu

        card_resp = bytearray(vcg.smartcard_fifo_read(resp_len_expected))
        data += card_resp

        parsed_resp = TEQ1.response(b'')
        try:
            parsed_resp = TEQ1.response(card_resp)
        except Exception as e:
            print('error parsing response: "{}"'.format(repr(e)))

        if vcg_timeout:
            color = ResultColor.WHITE
        elif parsed_resp.status == resp_expected:
            color = ResultColor.GREEN
        else:
            # Wait a little and check if card sent more data then
            sleep(.5)
            extra_bytes = bytes(vcg.smartcard_fifo_read(0))
            data += extra_bytes

            if parsed_resp.status == resp_expected:
              color = ResultColor.CYAN
            elif parsed_resp.status == bytes.fromhex('9000'):
                color = ResultColor.RED
            else:
                color = ResultColor.YELLOW

        vcg.cpu_stop()

        if color != ResultColor.GREEN:
            # Do a reset next iteration
            skip_reset = 0
            # Reset the T=1 state
            teq1.reset()
            # Power down for a cold reset
            vcg.set_vcc_glitch_parameter(v_vcc=v_normal, v_clk=v_normal, v_glitch=p['glitch_voltage'])
            # Keep it off for a few miliseconds, can be optimized based on device
            sleep(100e-3)



        result = Parameters(
            ("id", counter),
            ("timestamp", int(t)),
            ("iter_t", int((time() - t) * 1000)),
            ("normal_voltage", p['normal_voltage']),
            ("glitch_voltage", p['glitch_voltage']),
            ("glitch_delay", p['glitch_delay']),
            ("glitch_length", p['glitch_length']),
            ("vcg_timeout", vcg_timeout),
            ("atr", bytes(card_atr)),
            ("tpdu", bytes(tpdu)),
            ("r_data", bytes(parsed_resp.data)),
            ("r_status", bytes(parsed_resp.status)),
            ("Data", bytes(data)),
            ("Color", int(color))
        )

        util.monitor(result)

        counter += 1
        db.add(result)
