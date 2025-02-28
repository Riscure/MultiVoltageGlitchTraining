'''This script demonstrates a typical VCC fault injection setup with a Spider. In this demo we 
target the PIN verification command of the Pinata. We send the command (A2) along with a PIN guess 
(4 random bytes) to the Pinata as input, and it replies with two status bytes. 6986 means incorrect 
PIN, 9000 means correct PIN. The Pinata produces a trigger on its "PC2" pin. For more information on
the pins of the Pinata, please refer to its manual.

To setup this demo you need:

1. Spider
2. Glitch Amplifier
3. Pinata
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


from time import sleep, time
from pathlib import Path
from shapely.geometry import Point  
from shapely.geometry.polygon import Polygon 
import serial
import os

from fipy.parameters import *
from fipy.scriptutils import ResultColor, fipy_script
from spidersdk.chronology import Chronology
from spidersdk.spider import Spider


PARAMETERS = Parameters(
    ('glitches', IntParameter(
        'Glitches', validate_min=0, validate_max=3)),
    ('attempts', AttemptsParameter('Attempts')),
    ('glitch_delay', IntParameter('Glitch delay 1', unit='ns')),
    ('glitch_length', IntParameter('Glitch length 1', unit='ns')),
    ('glitch_voltage', FloatParameter('Glitch voltage 1', unit='V')),
    ('glitch_delay2', IntParameter('Glitch delay 2', unit='ns')),
    ('glitch_length2', IntParameter('Glitch length 2', unit='ns')),
    ('glitch_voltage2', FloatParameter('Glitch voltage 2', unit='V')),
    ('glitch_delay3', IntParameter('Glitch delay 3', unit='ns')),
    ('glitch_length3', IntParameter('Glitch length 3', unit='ns')),
    ('glitch_voltage3', FloatParameter('Glitch voltage 3', unit='V')),
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

polygon_points=[(0.03245327621211658, -2.993695811849991), (26.318397565247437, -2.9982900398827823), (35.08037899492587, -1.5694851216847727), (63.34483521969503, -0.6092914628314481), (155.76960707469016, -0.2233763080770017), (316.0290738691313, -0.3382320088967772), (451.1331746235279, -0.4347107975853888), (500.31332845462623, -0.4530877097165531), (499.74803933013084, 0.1579446186446538), (235.7580181907869, 0.19469844290698202), (87.36962301074881, 0.180915758808609), (15.860548762082843, -0.0901436951260619), (-0.5328358482832662, -0.8435970925037903), (0.03245327621211658, -2.993695811849991)]
polygon = Polygon(polygon_points)
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
        
    normal_vcc = float(PARAMETERS['normal_voltage'])

    glitcher.set_vcc_now(GLITCH_OUT, normal_vcc)
    glitcher.set_gpio_now(RESET_OUT, 1)
    counter = 0
    do_reset = True
    
    for p in PARAMETERS:
        #if not polygon.contains(Point(p["glitch_length2"], p["glitch_voltage2"])):            
        #    continue
        t = time()
        if not util.process_commands():
            break
            
        serial_target.reset_input_buffer()
        serial_target.reset_output_buffer()
        glitcher.forget_events()  

        if do_reset:
            # Perform reset "Now", instead of in the state machine
            # sleeps might require manual tuning, based on device
            glitcher.set_gpio(RESET_OUT, 0)
            glitcher.set_vcc(GLITCH_OUT, 0)
            
            glitcher.wait_time(0.1e-3)
            glitcher.set_gpio(RESET_OUT, 1)

            #glitcher.wait_time(10e-3)

            glitcher.set_vcc(GLITCH_OUT, normal_vcc)


            #do_reset = False
            

        # Clear states from previous iteration

        #glitcher.set_gpio(TRIGGER_OUT, 1)
        glitcher.wait_trigger(TRIGGER_IN, TRIGGER_EDGE, count=1)
        if p['glitches']>0:
            glitcher.glitch(
                GLITCH_OUT,
                p['glitch_voltage'],
                p['glitch_delay'] / 1e9,
                p['glitch_length'] / 1e9)
        if p['glitches']>1:
            glitcher.glitch(
                GLITCH_OUT,
                p['glitch_voltage2'],
                p['glitch_delay2'] / 1e9,
                p['glitch_length2'] / 1e9)
            #glitcher.set_gpio(TRIGGER_OUT, 0)
        if p['glitches']>2:
            glitcher.glitch(
                    GLITCH_OUT,
                    p['glitch_voltage3'],
                    p['glitch_delay3'] / 1e9,
                    p['glitch_length3'] / 1e9)
        #glitcher.wait_trigger(TRIGGER_IN, TRIGGER_EDGE, count=1)

        glitcher.start()  

        pin_response = serial_target.read(45)
        if b'\x00' in pin_response:# this was added after minimal test case because it happened pretty frequently and i wanted to get rid before running the first campaign
            pin_response = pin_response+serial_target.read(1)
        print(pin_response)
        print(len(pin_response))
        # Block for 1 second or until Spider reaches final state.
        spider_timeout = glitcher.wait_until_finish(0.1)

        if spider_timeout:
            color = ResultColor.PINK  # no trigger, check setup
        elif len(pin_response)==0 or pin_response==b'\x00': 
            color = ResultColor.YELLOW
        elif b'0,aaa6,aaa5,' in pin_response:
            color = ResultColor.ORANGE
        elif b'1,aaa6,aaa5,' in pin_response:
            color = ResultColor.GREEN
        elif b'0,aaaa,aaaa,String' in pin_response:
            color = ResultColor.RED
        elif b'0,aaaa,aaaa,' in pin_response:
            color = ResultColor.CYAN
        else:
            color = ResultColor.MAGENTA

      
        result = Parameters(
            ("id", counter),
            ("timestamp", int(t)),
            ("iter_t (ms)", int((time() - t) * 1000)),
            ("glitch_voltage1", p['glitch_voltage']),
            ("glitch_delay1", p['glitch_delay']),
            ("glitch_length1", p['glitch_length']),
            ("normal_voltage", p['normal_voltage']),
            ("glitch_voltage2", p['glitch_voltage2']),
            ("glitch_delay2", p['glitch_delay2']),
            ("glitch_length2", p['glitch_length2']),
            ("glitch_voltage3", p['glitch_voltage3']),
            ("glitch_delay3", p['glitch_delay3']),
            ("glitch_length3", p['glitch_length3']),
            ("normal_voltage", p['normal_voltage']),
            ("spider_timeout", spider_timeout),
            ("do_reset", do_reset),
            ("Data", pin_response),
            ("Color", int(color))
        )

        util.monitor(result)

        counter += 1
        db.add(result)
