'''This script demonstrates a Fault Injection Resistance Measure - FIRM test on Pinata. In this demo we
use three different test types trying to observe fault resistance in: register access, memory access
and branching in the CPU of Pinata. For each of these fault resistance models a Test Application is
designed to capture specific fault effects. The Pinata produces a trigger on its "PC2" pin.
For more information on the pins of the Pinata, please refer to its manual.

Pinata should contain a special firmware that can be found in the `scripts/FIRM` directory.

To setup this demo you need:

1. Spider
2. Glitch Amplifier
3. Pinata with modified FIRM firmware
4. A serial adapter to connect the Pinata to your PC

To build this setup:

* Connect Core 1 GPIO 0 (``TRIGGER_IN``) to Pinata's trigger pin
* Connect Core 1 GPIO 2 (``RESET_OUT``) to Pinata's reset pin
* Connect a ground of Core 1 to a ground of Pinata
* Connect the serial adapter to the TX, RX and ground of the Pinata
* Connect the Glitch Amplifier input to "glitch out 1" (use the 50 ohm adapter!)
* Connect the + and - of the Glitch Amplifier to 3.3V VBAT and ground respectively
* Optionally use Core 1 GPIO 8 to observe the setup with an oscilloscope
'''

from time import time, sleep
from pathlib import Path

import serial

from fipy.parameters import *
from fipy.plugins.firm.scriptutils import firm_run
from fipy.scriptutils import ResultColor, fipy_script
from spidersdk.chronology import Chronology
from spidersdk.spider import Spider

from firm import Condition, TestType, get_condition, TestProperties

PARAMETERS = Parameters(
    ('attempts', AttemptsParameter('Attempts')),
    ('test_type', IntParameter(
        'Test types 1=Register, 2=Memory, 3=Branch', validate_min=1, validate_max=3, random=True)),
    ('glitch_delay_1', IntParameter('Glitch delay test 1', unit='ns')),
    ('glitch_delay_2', IntParameter('Glitch delay test 2', unit='ns')),
    ('glitch_delay_3', IntParameter('Glitch delay test 3', unit='ns')),
    ('glitch_length', IntParameter('Glitch length', unit='ns')),
    ('glitch_voltage', FloatParameter('Glitch voltage', unit='V')),
    ('normal_voltage', FloatParameter('Normal voltage', unit='V')),
    ('spider_com_port', SerialPortParameter('Spider COM')),
    ('serial_com_port', SerialPortParameter('Pinata COM')),
    ('serial_baudrate', IntParameter('Pinata Baudrate')),
    ('serial_timeout', FloatParameter('Pinata read timeout')),
)

GLITCH_OUT = Spider.GLITCH_OUT1
TRIGGER_IN = 0
RESET_OUT = 2
TRIGGER_OUT = 8
TRIGGER_EDGE = Spider.RISING_EDGE


READ_MARGIN = 1024  # Number of additional bytes to check for.
RESPONSE_LENGTH = 136  # Length of the expected/success response

def reset(glitcher, normal_vcc):
    glitcher.set_vcc_now(GLITCH_OUT, 0)
    glitcher.set_gpio_now(RESET_OUT, 0)
    sleep(1e-3)
    glitcher.set_vcc_now(GLITCH_OUT, normal_vcc)
    glitcher.set_gpio_now(RESET_OUT, 1)
    sleep(100e-3)

@firm_run
@fipy_script
def execute_script(util):
    util.set_termination_timeout(5)
    util.parameter_init(PARAMETERS)

    script_name = Path(__file__).stem
    db = util.create_database_table(
        'logs/{}.sqlite'.format(script_name), script_name)
    util.add_to_cleanup(util.close_database)

    # Hardware initialization (Spider)
    spider_com_port = serial.Serial()
    spider_com_port.port = str(PARAMETERS['spider_com_port'])
    spider_com_port.open()
    spider_core1 = Spider(Spider.CORE1, spider_com_port)
    spider_core1.reset_settings()
    util.add_to_cleanup(spider_com_port.close)

    # Hardware initialization (Riscuberry)
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

    # Forget any previous added events
    glitcher.forget_events()
    normal_vcc = float(PARAMETERS['normal_voltage'])

    # Reset the device before gathering data about normal operation.
    reset(glitcher, float(PARAMETERS['normal_voltage']))
    # Get test properties from device. This includes reading expected data and setting the test commands.
    test_properties = TestProperties.get_test_properties(serial_target)

    counter = 0
    do_reset = True

    for p in PARAMETERS:
        t = time()
        if not util.process_commands():
            break

        # Clear states from previous iteration
        glitcher.forget_events()

        # Get a random test_type and its associated test
        test_type = TestType.from_int(p['test_type'])
        test = test_properties[test_type]

        if do_reset or test_type == TestType.REGISTER:
            reset(glitcher, normal_vcc)
            do_reset = False
            serial_target.reset_input_buffer()
            serial_target.reset_output_buffer()

        # Configure state machine for glitch with current parameters
        glitcher.set_gpio(TRIGGER_OUT, 1)
        glitcher.wait_trigger(TRIGGER_IN, TRIGGER_EDGE, count=1)
        # Glitch delay can vary between tests.
        glitch_delay = p[f'glitch_delay_{test_type.value}']
        glitcher.glitch(
            GLITCH_OUT,
            p['glitch_voltage'],
            glitch_delay / 1e9,
            p['glitch_length'] / 1e9)
        glitcher.set_gpio(TRIGGER_OUT, 0)

        glitcher.start()

        # Send the command to perform the specific test application
        serial_target.write(test.cmd)
        received = serial_target.read(len(test.expected))

        # Block for 1 second or until Spider reaches final state.
        spider_timeout = glitcher.wait_until_finish(1000)

        if spider_timeout:
            color = ResultColor.PINK  # no trigger, check setup
        else:
            # Check if there are more bytes
            received += serial_target.read(READ_MARGIN)
            if received == test.expected:
                color = ResultColor.GREEN
            elif len(received) <= 1:
                color = ResultColor.YELLOW
            elif len(received) != RESPONSE_LENGTH:
                # faults with different length than the RESPONSE_LENGTH are not used
                # in the FIRM analysis at all.
                color = ResultColor.MAGENTA
            else:
                color = ResultColor.RED

        condition = Condition.NO_FAULT
        if color != ResultColor.GREEN:
            # get_condition() determines what type of fault occurred during this iteration. This information is stored
            # to help track of which FI parameters lead to which faults, but it is not used in the FIRM analysis
            condition = get_condition(test_type, received, test.expected)
            # Force TRIGGER_OUT to 0 in case there was a problem
            glitcher.set_gpio_now(TRIGGER_OUT, 0)
            do_reset = True

        # Adding the test_type to the result database is vital for running the FIRM analysis
        result = [("id", counter),
                  ("iter_t (ms)", int((time() - t) * 1000)),
                  ("test_type", test_type.value),
                  ("glitch_voltage", p['glitch_voltage']),
                  ("glitch_delay", glitch_delay),
                  ("glitch_length", p['glitch_length']),
                  ("normal_voltage", normal_vcc),
                  ("spider_timeout", spider_timeout),
                  ("reset", do_reset),
                  ("condition_name", condition.name),
                  ("Color", int(color)),
                  ("Data_length", len(received))]

        util.monitor(Parameters(*result))

        result.extend([
            ("timestamp", int(t)),
            ("Data", received)])

        counter += 1
        db.add(Parameters(*result))
