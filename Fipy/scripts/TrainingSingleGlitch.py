from time import sleep, time
from pathlib import Path

import serial
import os

from fipy.parameters import *
from fipy.scriptutils import ResultColor, fipy_script
from spidersdk.chronology import Chronology
from spidersdk.spider import Spider


PARAMETERS = Parameters(
    ('attempts', AttemptsParameter('Attempts')),
    ('glitch_delay', IntParameter('Glitch delay', unit='ns')),
    ('glitch_length', IntParameter('Glitch length', unit='ns')),
    ('glitch_voltage', FloatParameter('Glitch voltage', unit='V')),
    ('normal_voltage', FloatParameter('Normal voltage', unit='V')),
    ('spider_com_port', SerialPortParameter('Spider COM')),
    ('serial_com_port', SerialPortParameter('Target COM')),
    ('serial_baudrate', IntParameter('Target Baudrate')),
    ('serial_timeout', FloatParameter('Target read timeout'))
)

GLITCH_OUT = Spider.GLITCH_OUT1
TRIGGER_IN = 31
RESET_OUT  = 0
TRIGGER_OUT = 8
TRIGGER_EDGE = Spider.RISING_EDGE


@fipy_script
def execute_script(util):
    util.set_termination_timeout(5)
    util.parameter_init(PARAMETERS)

    script_name = Path(__file__).stem
    db = util.create_database_table('logs/{}.sqlite'.format(script_name),
                                    '{}'.format(script_name))
    util.add_to_cleanup(util.close_database)

    # Hardware initialization (Spider)
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
        
    normal_voltage = float(PARAMETERS['normal_voltage'])/2

    glitcher.set_vcc_now(GLITCH_OUT, normal_voltage)
    glitcher.set_gpio_now(RESET_OUT, 1)
    counter = 0
    do_reset = True
    
    for p in PARAMETERS:
        t = time()
        if not util.process_commands():
            break
            
        serial_target.reset_input_buffer()
        serial_target.reset_output_buffer()
        glitcher.forget_events()  

        glitcher.set_gpio(RESET_OUT, 0)
        glitcher.set_vcc(GLITCH_OUT, 0)
        
        glitcher.wait_time(0.1e-3)
        glitcher.set_gpio(RESET_OUT, 1)

        glitcher.set_vcc(GLITCH_OUT, normal_voltage)            

        glitcher.wait_trigger(TRIGGER_IN, TRIGGER_EDGE, count=1)
        glitcher.glitch(
            GLITCH_OUT,
            p['glitch_voltage']/2,
            p['glitch_delay'] / 1e9,
            p['glitch_length'] / 1e9)
            
        glitcher.start()  

        response = serial_target.read(31)
        
        if b'\x00' in response:# this was added after minimal test case because it happened pretty frequently and i wanted to get rid before running the first campaign
            response = response+serial_target.read(1)
        print(response)
        print(len(response))
        # Block for 1 second or until Spider reaches final state.
        spider_timeout = glitcher.wait_until_finish(2000)

        if spider_timeout:
            color = ResultColor.PINK  # no trigger, check setup
        elif len(response)==0 or response==b'\x00': 
            color = ResultColor.YELLOW # no or weird noticed response
        elif b'1,aaa6,aaa5' in response: 
            color = ResultColor.GREEN # contains expected answer
        else:
            color = ResultColor.RED # anything else
      
        result = Parameters(
            ("id", counter),
            ("timestamp", int(t)),
            ("iter_t (ms)", int((time() - t) * 1000)),
            ("glitch_voltage", p['glitch_voltage']),
            ("glitch_delay", p['glitch_delay']),
            ("glitch_length", p['glitch_length']),
            ("normal_voltage", normal_voltage),
            ("spider_timeout", spider_timeout),
            ("do_reset", do_reset),
            ("Data", response),
            ("Color", int(color))
        )

        util.monitor(result)

        counter += 1
        db.add(result)
