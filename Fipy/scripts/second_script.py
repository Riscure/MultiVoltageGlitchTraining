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
    ('attempts', AttemptsParameter('Attempts')),
    ('glitch_delay', IntParameter('Glitch delay 1', unit='ns')),
    ('glitch_length', IntParameter('Glitch length 1', unit='ns')),
    ('glitch_voltage', FloatParameter('Glitch voltage 1', unit='V')),
    ('glitch_delay2', IntParameter('Glitch delay 2', unit='ns')),
    ('glitch_length2', IntParameter('Glitch length 2', unit='ns')),
    ('glitch_voltage2', FloatParameter('Glitch voltage 2', unit='V')),
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

polygon_points=[(9.340932162142703, -2.9968696344560244), (19.367890393930693, -2.9914877578757255), (19.505245986146967, -2.6901026693789833), (23.282524772094497, -2.6362839035759937), (23.625913752635185, -2.157296887929386), (27.47187033469085, -2.1196237518672936), (27.54054813079899, -1.732128638085768), (31.31782691674652, -1.6944555020236753), (31.72989369339534, -1.425361673008727), (35.301139091018456, -1.3607791540451395), (35.78188366377542, -1.134740337672583), (39.35312906139854, -1.1508859674134801), (39.490484653614814, -0.9679021636833154), (43.611152420103025, -0.9517565339424183), (43.54247462399489, -0.8118277428546454), (47.457109002158695, -0.8118277428546454), (47.6631423904831, -0.6880445815077691), (51.234387788106226, -0.6988083346683669), (51.577776768646906, -0.5965526796426865), (55.42373335070258, -0.5911708030623877), (55.42373335070258, -0.5319701606790992), (67.71705885405908, -0.3651319866898315), (86.67213057990486, -0.096038157674883), (103.01744605364145, -0.036837515291594514), (116.61564968305257, -0.02607376213099677), (131.45005364241015, -0.020691885550697453), (131.58740923462642, 0.7112433293699616), (85.71064143439095, 0.6735701933078686), (59.54440111719079, 0.5874601680230853), (35.644528071559144, 0.4098582408732194), (31.6612158972872, 0.3345119687490339), (27.54054813079899, 0.2753113263657454), (27.26583694636644, 0.18920130108096211), (23.48855816041891, 0.16229191817946687), (23.351202568202638, 0.03850875683259103), (19.64260157836324, 0.006217497350797352), (19.367890393930693, -0.20905756586116153), (15.590611607983163, -0.2144394424414604), (15.315900423550616, -0.558879543580594), (11.469943841494949, -0.5857889264820888), (11.401266045386812, -1.30696038824215), (9.40960995825084, -1.312342264822449), (9.340932162142703, -2.9968696344560244)]
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
        glitcher.glitch(
            GLITCH_OUT,
            p['glitch_voltage'],
            p['glitch_delay'] / 1e9,
            p['glitch_length'] / 1e9)

        glitcher.glitch(
            GLITCH_OUT,
            p['glitch_voltage2'],
            p['glitch_delay2'] / 1e9,
            p['glitch_length2'] / 1e9)
        #glitcher.set_gpio(TRIGGER_OUT, 0)

        glitcher.start()  

        pin_response = serial_target.read(13)
        if b'\x00' in pin_response:# this was added after minimal test case because it happened pretty frequently and i wanted to get rid before running the first campaign
            pin_response = pin_response+serial_target.read(1)
        print(pin_response)
        print(len(pin_response))
        # Block for 1 second or until Spider reaches final state.
        spider_timeout = glitcher.wait_until_finish(2000)

        if spider_timeout:
            color = ResultColor.PINK  # no trigger, check setup
        elif len(pin_response)==0 or pin_response==b'\x00': 
            color = ResultColor.YELLOW
        elif b'0,aaa6,aaa5\r\n' in pin_response:
            color = ResultColor.ORANGE
        elif b'1,aaa6,aaa5\r\n' in pin_response:
            color = ResultColor.GREEN
        elif b'0,aaaa,aaaa\r\n' in pin_response:
            color = ResultColor.RED
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
            ("normal_voltage", p['normal_voltage']),
            ("spider_timeout", spider_timeout),
            ("do_reset", do_reset),
            ("Data", pin_response),
            ("Color", int(color))
        )

        util.monitor(result)

        counter += 1
        db.add(result)
