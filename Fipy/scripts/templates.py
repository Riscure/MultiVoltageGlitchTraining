from math import sin, pi, ceil
from random import random
from typing import List

from spidersdk import Spider
from spidersdk.glitchpattern import PATTERN_STATE_LIMIT


def block(min_voltage: float, max_voltage: float, duration: float) -> List[float]:
    """
    Generate new pattern from the selected template

    :param min_voltage:  the minimum voltage level of the template function
    :param max_voltage: the maximum voltage level of the template function
    :param duration: the length of the pattern in seconds
    :return: the resulting pattern as a list of doubles. Every double represents a voltage level with
    a duration of 'Spider.MIN_SEC' seconds.
    """
    result = []

    number_of_segments = int(ceil(duration / Spider.MIN_SEC / 2))
    result.extend([min_voltage] * number_of_segments)
    result.extend([max_voltage] * number_of_segments)

    return result


def sine(min_voltage: float, max_voltage: float, duration: float) -> List[float]:
    """
    Generate new pattern from the selected template

    :param min_voltage:  the minimum voltage level of the template function
    :param max_voltage: the maximum voltage level of the template function
    :param duration: the length of the pattern in seconds
    :return: the resulting pattern as a list of doubles. Every double represents a voltage level with
    a duration of 'Spider.MIN_SEC' seconds.
    """
    result = []

    segment_length = duration / PATTERN_STATE_LIMIT
    number_of_segments = int(duration / Spider.MIN_SEC)
    if number_of_segments > PATTERN_STATE_LIMIT:
        number_of_segments = PATTERN_STATE_LIMIT
    voltage_offset = (max_voltage + min_voltage) / 2.0
    voltage_range = (max_voltage - min_voltage) / 2.0
    for k in range(0, number_of_segments):
        current_length = 0
        while current_length < segment_length:
            result.append(voltage_offset + (sin(2 * pi * (k / float(number_of_segments))) * voltage_range))
            current_length += Spider.MIN_SEC

    return result


def ramp(min_voltage: float, max_voltage: float, duration: float) -> List[float]:
    """
    Generate new pattern from the selected template

    :param min_voltage:  the minimum voltage level of the template function
    :param max_voltage: the maximum voltage level of the template function
    :param duration: the length of the pattern in seconds
    :return: the resulting pattern as a list of doubles. Every double represents a voltage level with
    a duration of 'Spider.MIN_SEC' seconds.
    """
    result = []

    segment_length = duration / PATTERN_STATE_LIMIT
    number_of_segments = int(duration / Spider.MIN_SEC)
    if number_of_segments > PATTERN_STATE_LIMIT:
        number_of_segments = PATTERN_STATE_LIMIT
    increment = (max_voltage - min_voltage) / number_of_segments
    for k in range(0, number_of_segments):
        current_length = 0
        while current_length < segment_length:
            result.append(min_voltage + (k * increment))
            current_length += Spider.MIN_SEC

    return result


def randomized(min_voltage: float, max_voltage: float, duration: float) -> List[float]:
    """
    Generate new pattern from the selected template

    :param min_voltage:  the minimum voltage level of the template function
    :param max_voltage: the maximum voltage level of the template function
    :param duration: the length of the pattern in seconds
    :return: the resulting pattern as a list of doubles. Every double represents a voltage level with
    a duration of 'Spider.MIN_SEC' seconds.
    """
    result = []

    segment_length = duration / PATTERN_STATE_LIMIT
    number_of_segments = int(duration / Spider.MIN_SEC)
    if number_of_segments > PATTERN_STATE_LIMIT:
        number_of_segments = PATTERN_STATE_LIMIT
    voltage_range = max_voltage - min_voltage
    for k in range(0, number_of_segments):
        current_length = 0
        value = (random() * voltage_range) + min_voltage
        while current_length < segment_length:
            result.append(value)
            current_length += Spider.MIN_SEC

    return result