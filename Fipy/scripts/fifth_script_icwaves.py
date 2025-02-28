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
ICW_TRIG_1= 15

polygon_points=[(68.56966642835827, -0.09875319275962799), (77.79473930467995, -0.08229298470840235), (85.93450948966968, -0.058590285114637444), (87.56246352666761, -0.017768969147597874), (88.64776621799957, 0.005933730446167032), (111.98177408163679, 0.014931977514170386), (134.230479253942, 0.007470016530948087), (153.76592769791733, -0.019524724673061947), (169.50281672223082, -0.04893362972458508), (177.64258690722053, -0.0675885321826408), (190.6662192032041, -0.09809478443757896), (203.68985149918763, -0.09941160108167701), (222.68264859749698, -0.099192131640994), (241.67544569580633, -0.09348592618323578), (247.10195915246615, -0.07943988197952324), (256.8696833744538, -0.04981150748731711), (272.6065723987673, -0.03444864663950652), (290.5140668057447, -0.05244514077551321), (307.87890986705605, -0.07329473764039901), (330.1276150393613, -0.08251245414908537), (355.63222828566245, -0.08953547625094163), (379.5088874949656, -0.08448767911523244), (404.47084939560074, -0.06319914336898062), (420.2077384199142, -0.04256901594477783), (437.02993013555965, -0.03642387160565359), (447.88295704887923, -0.044544240910924904), (457.1080299252009, -0.06144338784351656), (475.5581756778443, -0.07153898211493495), (486.95385393682994, -0.07592837092859511), (517.8849806397909, -0.06714959330127478), (564.5529963670652, -0.05595665182644134), (601.453287872352, -0.061004448962150536), (623.1593416989913, -0.06934428770810486), (657.889027821614, -0.06912481826742184), (682.3083383765833, -0.06363808225034664), (713.2394650795442, -0.059907101758735495), (760.4501321524846, -0.06561330721649372), (793.0092128924434, -0.06056551008078452), (828.8242017063982, -0.05793187679258842), (853.2435122613673, -0.057492937911222404), (872.2363093596767, -0.06210179616556558), (898.2835739516438, -0.06429649057239567), (952.006057172576, -0.06034604064010151), (985.6504406038669, -0.054200896300977276), (998.1314215541844, -0.04827522140253605), (1000.3020269368483, 0.04763292417593862), (46.86361260171901, 0.038854146548618296), (46.32096125605303, -0.09897266220031099), (68.56966642835827, -0.09875319275962799)]
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
        if not polygon.contains(Point(p["glitch_length2"], p["glitch_voltage2"])):            
            continue
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
            glitcher.set_gpio(TRIGGER_OUT, 0)

            glitcher.wait_time(0.1e-3)
            glitcher.set_gpio(RESET_OUT, 1)

            #glitcher.wait_time(10e-3)

            glitcher.set_vcc(GLITCH_OUT, normal_vcc)
            
            glitcher.set_gpio(TRIGGER_OUT, 1)

            #do_reset = False
            

        # Clear states from previous iteration

        #glitcher.set_gpio(TRIGGER_OUT, 1)
        glitcher.wait_trigger(ICW_TRIG_1, TRIGGER_EDGE, count=1)
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
        glitcher.wait_trigger(TRIGGER_IN, TRIGGER_EDGE, count=1)
        glitcher.wait_trigger(TRIGGER_IN, TRIGGER_EDGE, count=1)

        glitcher.start()  

        pin_response = serial_target.read(45)
        if b'\x00' in pin_response:# this was added after minimal test case because it happened pretty frequently and i wanted to get rid before running the first campaign
            pin_response = pin_response+serial_target.read(1)
        print(pin_response)
        print(len(pin_response))
        # Block for 1 second or until Spider reaches final state.
        spider_timeout = glitcher.wait_until_finish(0.001)
        state=glitcher.get_current_state()
        if spider_timeout:
            if len(pin_response)==0 or pin_response==b'\x00': 
                color = ResultColor.YELLOW
            elif b'0,aaa6,aaa5,' in pin_response:
                color = ResultColor.ORANGE
            elif b'1,aaa6,aaa5,' in pin_response:
                color = ResultColor.GREEN
            elif b'0,aaaa,aaaa,' in pin_response:
                color = ResultColor.CYAN
            else:
                color = ResultColor.MAGENTA
        elif b'0,aaaa,aaaa' in pin_response:
                color = ResultColor.RED
        else:  
                color = ResultColor.WHITE

      
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
            ("state",state),
            ("Data", pin_response),
            ("Color", int(color))
        )

        util.monitor(result)

        counter += 1
        db.add(result)
