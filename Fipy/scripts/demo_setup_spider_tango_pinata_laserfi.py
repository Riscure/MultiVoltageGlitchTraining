'''This script demonstrates a typical optical fault injection setup with a Spider and a Diode Laser 
Station. In this demo we target the PIN verification command of the Pinata. We send the command (A2) 
along with a PIN guess (4 random bytes) to the Pinata as input, and it replies with two status bytes. 
6986 means incorrect PIN, 9000 means correct PIN. The Pinata produces a trigger on its "PC2" pin.
For more information on the pins of the Pinata, please refer to its manual.

To set up this demo you need:

1. Diode Laser Station
2. Spider
3. Glitch Amplifier (to power the Pinata)
4. A serial adapter to connect the Pinata to your PC

To build this setup:

* Connect Core 1 GPIO 0 (``TRIGGER_IN``) to Pinata's trigger pin
* Connect Core 1 GPIO 2 (``RESET_OUT``) to Pinata's reset pin
* Connect a ground of Core 1 to a ground of Pinata
* Connect the serial adapter to the TX, RX and ground of the Pinata
* Connect the Glitch Amplifier input to "glitch out 1" (use the 50 ohm adapter!)
* Connect the + and - of the Glitch Amplifier to 3.3V VBAT and ground respectively
* Connect "glitch out 2" of the Spider to "digital glitch" of the Diode Laser
* Connect "voltage out 1" of the Spider to "pulse amplitude" of the Diode Laser
* Optionally use Core 1 GPIO 8 to observe the setup with an oscilloscope

Before running the script, use the table coordinates view to configure three reference points.
'''


import random
import os
import serial
from time import time, sleep
from pathlib import Path

from fipy.parameters import *
from fipy.scriptutils import ResultColor, fipy_script
from spidersdk.chronology import Chronology
from spidersdk.spider import Spider
from fipy.transformutil import TransformUtil


tu = TransformUtil()

PARAMETERS = Parameters(
    ('scans', AttemptsParameter('Scans')),
    ('xyz_scanner', MaskedXYZScanParameter('XYZ scanner', transformutil=tu)),
    ('z_offset', IntParameter('Z Offset', unit='um')),
    ('pulse_power', IntParameter('Pulse Power', unit='%')),
    ('pulse_length', IntParameter('Pulse Length', unit='ns')),
    ('pulse_delay', IntParameter('Pulse Delay', unit='ns')),
    ('spider_com_port', SerialPortParameter('Spider COM')),
    ('serial_com_port', SerialPortParameter('Pinata COM')),
    ('serial_baudrate', IntParameter('Pinata Baudrate')),
    ('serial_timeout', FloatParameter('Pinata read timeout')),
    ('normal_voltage', FloatParameter('Pinata normal voltage', unit='V')),
)

TRIGGER_IN = 0
RESET_OUT = 2
TRIGGER_OUT = 8
TARGET_POWER = Spider.GLITCH_OUT1
TRIGGER_EDGE = Spider.RISING_EDGE
DLS_PULSE_AMPLITUDE = Spider.VOLTAGE_OUT1
DLS_DIGITAL_GLITCH = Spider.GLITCH_OUT2
DLS_GLITCH_VOLTAGE = 3.3


@fipy_script
def execute_script(util):
    util.set_termination_timeout(5)
    util.parameter_init(PARAMETERS)

    script_name = Path(__file__).stem
    db = util.create_database_table('logs/{}.sqlite'.format(script_name), script_name)
    util.add_to_cleanup(util.close_database)

    xyz_interface = util.get_xyz()
    tu.add_system('table', xyz_interface.get_reference_points())

    # # Hardware initialization (Spider)
    spider_com_port = serial.Serial()
    spider_com_port.port = str(PARAMETERS['spider_com_port'])
    spider_com_port.open()
    spider_core1 = Spider(Spider.CORE1, spider_com_port)
    spider_core1.reset_settings()
    util.add_to_cleanup(spider_com_port.close)

    # Hardware initialization (Pinata)
    serial_target = serial.Serial()
    serial_target.baudrate = int(PARAMETERS['serial_baudrate'])
    serial_target.timeout = float(PARAMETERS['serial_timeout'])
    serial_target.port = str(PARAMETERS['serial_com_port'])
    serial_target.open()
    serial_target.reset_input_buffer()
    serial_target.reset_output_buffer()
    util.add_to_cleanup(serial_target.close)

    try:
        glitcher = Chronology(spider_core1)
    except IndexError as e:
        raise Exception(str(e) +
                        "\n\nDid you select the right COM port for Spider? Is it powered on?")

    glitcher.forget_events()  # Forget any previous added events
        
    normal_vcc = float(PARAMETERS['normal_voltage'])

    counter = 0
    do_reset = True
    expected_response = bytes.fromhex('6986')
    success_response = bytes.fromhex('9000')

    # Initialize target VCC
    glitcher.set_vcc_now(TARGET_POWER, 0)
    # Initialize the digital glitch output
    glitcher.set_vcc_now(DLS_DIGITAL_GLITCH, 0)
    # Initialize the pulse amplitude output
    glitcher.set_power_now(DLS_PULSE_AMPLITUDE, 0)

    # Transform to chip coordinates using the warping tool.
    # This tools will use chip warping when it is enabled in the project settings,
    # and otherwise perform regular transformations between table and chip coordinates
    transform = util.get_warping_tool()

    for p in PARAMETERS:
        t = time()
        if not util.process_commands():
            break

        glitcher.set_power_now(DLS_PULSE_AMPLITUDE, p['pulse_power'])

        chip_pos = p['xyz_scanner']
        table_pos = transform.from_chip(chip_pos)
        # By default, tango controls are reversed, meaning that adding positive
        # numbers to the z position will move the mounted lens up, increasing
        # the distance between the lens and the table platform.
        z = table_pos.z + p['z_offset']
        xyz_interface.move_abs(table_pos.x, table_pos.y, z)

        glitcher.forget_events()

        if do_reset:
            # Sleeps might require manual tuning, based on device
            glitcher.set_vcc_now(TARGET_POWER, 0)
            glitcher.set_gpio_now(RESET_OUT, 0)
            sleep(1e-3)
            glitcher.set_vcc_now(TARGET_POWER, normal_vcc)
            glitcher.set_gpio_now(RESET_OUT, 1)
            sleep(100e-3)
            do_reset = False

        glitcher.set_gpio(TRIGGER_OUT, 1)
        glitcher.wait_trigger(TRIGGER_IN, TRIGGER_EDGE, count=1)
        glitcher.set_gpio(TRIGGER_OUT, 0)
        glitcher.glitch(
            DLS_DIGITAL_GLITCH,
            DLS_GLITCH_VOLTAGE,
            p['pulse_delay'] / 1e9,
            p['pulse_length'] / 1e9)

        glitcher.start()

        pin_guess = os.urandom(4)

        serial_target.write(b'\xA2' + pin_guess)
        pin_response = serial_target.read(2)

        spider_timeout = glitcher.wait_until_finish(1000)

        if spider_timeout:
            color = ResultColor.PINK  # no trigger, check setup
        elif pin_response == expected_response:
            color = ResultColor.GREEN
        else:
            # Check if there are more bytes
            pin_response += serial_target.read(1024)
            if pin_response == expected_response:
                color = ResultColor.GREEN
            elif pin_response == success_response:
                color = ResultColor.RED
            elif len(pin_response) == 0:
                color = ResultColor.YELLOW
            else:
                color = ResultColor.ORANGE  # some error

        if color != ResultColor.GREEN:
            # Force TRIGGER_OUT to 0 in case there was a problem
            glitcher.set_gpio_now(TRIGGER_OUT, 0)
            do_reset = True

        result = Parameters(
            ("id", counter),
            ("timestamp", int(t)),
            ("iter_t (ms)", int((time() - t) * 1000)),
            ("scan", p['scans']),
            ("x", chip_pos.x),
            ("y", chip_pos.y),
            ("z", p['z_offset']),
            ("pulse_power", p['pulse_power']),
            ("pulse_delay", p['pulse_delay']),
            ("pulse_length", p['pulse_length']),
            ("normal_voltage", p['normal_voltage']),
            ("spider_timeout", spider_timeout),
            ("pin_guess", pin_guess),
            ("do_reset", do_reset),
            ("Data", pin_response),
            ("Color", int(color))
        )

        util.monitor(result)

        counter += 1
        db.add(result)
