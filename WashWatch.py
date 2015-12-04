#!/usr/bin/env python

from datetime import datetime, timedelta
import RPi.GPIO as GPIO
import csv

DEBUG = 1

# change these as desired - they're the pins connected from the
# SPI port on the ADC to the Cobbler
SPICLK = 18
SPIMISO = 23
SPIMOSI = 24
SPICS = 25
WASHER_PORT = 0
DRYER_PORT = 1

# Data Processing Variables
ON_VAL = None

washer_setpt_def = .5  # Default on setpt in Volts COMPLETE GUESS
dryer_setpt_def = .5  # Default on setpt in Volts COMPLETE GUESS

class WashWatch:
    """
    Class to hold port and data processing variables
    """

    def __init__(self, spiclk, spimosi, spimiso, spics, washer_port, dryer_port):
        """
        Initializer with ports for adc and appliances
        :param spiclk: Pin of Clk output
        :param spimosi: Pin of Data Output
        :param spimiso: Pin of Data Input
        :param spics: Pin of Shtdwn (to select chip)
        :param washer_port: Port of washer on ADC
        :param dryer_port: Port of Dryer on ADC
        :return: WashWatch object
        """
        self.spiclk = spiclk
        self.spimosi = spimosi
        self.spimiso = spimiso
        self.spics = spics
        self.washer_port = washer_port
        self.dryer_port = dryer_port
        self.washer_setpt = washer_setpt_def  # On setpt in Volts
        self.dryer_setpt = dryer_setpt_def  # On setpt in Volts

        # Current Values
        self.washer_raw = None
        self.dryer_raw = None
        self.washer_volts = None
        self.dryer_volts = None
        self.washer_on = None
        self.dryer_on = None
        self.washer_in_cycle = None
        self.dryer_in_cycle = None

        # Basic in_cycle variables
        self.last_on_timestamp_w = datetime.timedelta(minutes=3)  # Last recorded on time of the washer

    def read_appliance(self, app):
        """
        Get reading from selected appliance
        :param app: appliace for selection 'w' for washer or 'd' for dryer
        :return: value out of 1024 scaled to Vref of ADC chip
        """
        if app == 'w':
            self.washer_raw = \
                self.read_adc(self.washer_port, self.spiclk, self.spimosi, self.spimiso, self.spics)
            return self.washer_raw
        elif app == 'd':
            self.dryer_raw = self.read_adc(self.dryer_port, self.spiclk, self.spimosi, self.spimiso, self.spics)
            return self.dryer_raw
        else:
            return -1  # Light error checking

    def is_on(self, setpt=None, val=None):
        """
        Check whether appliance is on or val is above custom setpt.
        :param setpt:
        :param val: value to be compared (likely volts)
        :return: Switch point
        """
        if setpt == 'w':
            self.washer_on = self.washer_volts > self.washer_setpt
            return self.washer_on
        elif setpt == 'd':
            self.dryer_on = self.washer_volts > self.dryer_setpt
            self.dryer_in_cycle = self.dryer_on
            return self.dryer_on
        elif is_number(setpt) and is_number(val):  # Unsure of this logic
            return val > setpt
        elif setpt is None:
            return self.is_on('w'), self.is_on('d')
        else:
            return -1

    def in_cycle_washer(self):
        """
        Checks and returns whether washer is in cycle
        :return: is washer in cycle
        """
        if self.washer_on:  # If currently on, definitely in cycle
            self.last_on_timestamp_w = datetime.now()  # Update most recent on timestamp
            self.washer_in_cycle = True  # Set variable accordingly
            return True
        # Though washer is off, wait for time period to expire before declaring it off
        elif not self.washer_on and datetime.now() - self.last_on_timestamp_w < datetime.timedelta(minutes=2):
            return True
        # Washer is off and time period has expired. Declare the cycle off
        elif not self.washer_on and datetime.now() - self.last_on_timestamp_w >= datetime.timedelta(minutes=2):
            self.washer_in_cycle = False
            return False

    def update_values(self, appliance=None):
        """
        Use to update all values for reading
        :param appliance:
        :return:
        """
        if appliance is None or appliance == 'w':
            print("\t\tReading Washer.")
            self.read_appliance('w')

            print("\t\tCalculating/Analyzing Data.")
            self.washer_volts = self.to_volts(self.washer_raw)
            self.is_on('w')
            self.in_cycle_washer()
        if appliance is None or appliance == 'd':
            print("\t\tReading Dryer.")
            self.read_appliance('d')

            print("\t\tCalculating/Analyzing Data.")
            self.dryer_volts = to_volts(self.dryer_raw)
            self.is_on('d')

    # read SPI data from MCP3008 chip, 8 possible adc's (0 thru 7)
    @staticmethod
    def read_adc(adcnum, clockpin, mosipin, misopin, cspin):
        """
        Comm with ADC to get a single reading
        Credit: https://learn.adafruit.com/reading-a-analog-in-and-controlling-audio-volume-with-the-raspberry-pi/script
        :param adcnum: port to read from
        :param clockpin: Pin of Clk output
        :param mosipin: Pin of Data Output
        :param misopin: Pin of Data Input
        :param cspin: Pin of Shtdwn (to select chip)
        :return: value out of 1024 representing voltage between 0V and 5V
        """
        if adcnum > 7 or adcnum < 0:
            return -1
        GPIO.output(cspin, True)

        GPIO.output(clockpin, False)  # start clock low
        GPIO.output(cspin, False)     # bring CS low

        commandout = adcnum
        commandout |= 0x18  # start bit + single-ended bit
        commandout <<= 3    # we only need to send 5 bits here
        for i in range(5):
            if (commandout & 0x80):
                GPIO.output(mosipin, True)
            else:
                GPIO.output(mosipin, False)
            commandout <<= 1
            GPIO.output(clockpin, True)
            GPIO.output(clockpin, False)

        adcout = 0
        # read in one empty bit, one null bit and 10 ADC bits
        for i in range(12):
            GPIO.output(clockpin, True)
            GPIO.output(clockpin, False)
            adcout <<= 1
            if (GPIO.input(misopin)):
                adcout |= 0x1

        GPIO.output(cspin, True)

        adcout >>= 1       # first bit is 'null' so drop it
        return adcout

    @staticmethod
    def to_volts(bits):
        """
        Convert number out of 1024 bits to voltage (assuming Vref is 5V)
        :param bits: whole number out of 1024
        :return: Voltage out of 5V
        """
        return 5 * (bits / 1024.)  # Decimal on 1024. is to force float division


def is_number(num):
    """
    Modified from: http://stackoverflow.com/questions/354038/how-do-i-check-if-a-string-is-a-number-float-in-python
    :param num: number to check
    :return: True if number, False otherwise
    """
    try:
        float(num)
        return True
    except ValueError:
        try:
            int(num)
            return True
        except ValueError:
            return False


def main():
    """
    Main loop: Currently set for information gathering with current logic
    """
    # Use number based on im/outputs
    print("Setting GPIO Mode.")
    GPIO.setmode(GPIO.BCM)

    # Set up the SPI interface pins
    print("Setting up input and output pins.")
    GPIO.setup(SPIMOSI, GPIO.OUT)
    GPIO.setup(SPIMISO, GPIO.IN)
    GPIO.setup(SPICLK, GPIO.OUT)
    GPIO.setup(SPICS, GPIO.OUT)

    # Create WashWatch Object
    print("Creating WashWatch Object.")
    ww = WashWatch(SPICLK, SPIMOSI, SPIMISO, SPICS, WASHER_PORT, DRYER_PORT)

    print("Creating file and csv writer object.")
    f = open("logs/Test-" + datetime.now().strftime("%Y-%m-%d+%H:%M:%S") + ".csv", 'w')
    log = csv.writer(f)
    log.writerow(['date', 'time', 'w value', 'w volts', 'w on', 'w cycle', 'd value', 'd volts', 'd on', 'd cycle'])

    print("Entering main loop:")
    started = False
    while True:
        print("\tUpdating Values.")
        ww.update_values()

        print("Logging to csv.")
        log.writerow([str(datetime.now().date()), str(datetime.now().time()), ww.washer_raw,
                      ww.washer_volts, ww.washer_on, ww.washer_in_cycle, ww.dryer_raw, ww.dryer_volts, ww.dryer_on,
                      ww.dryer_in_cycle])

        # Loop breaking logic
        if ww.dryer_in_cycle or ww.washer_in_cycle:
            started = True
        if not ww.dryer_in_cycle and not ww.washer_in_cycle and started:
            break
        sleep(1)

    f.close()
    GPIO.cleanup()

main()
