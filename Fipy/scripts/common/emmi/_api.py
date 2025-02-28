import logging
from abc import ABC, abstractmethod
from contextlib import contextmanager

from harvesters.core import ImageAcquirer

LOGGER = logging.getLogger()


@contextmanager
def log_exception():
    try:
        yield
    except Exception as e:
        message = "Feature not supported by this camera."
        LOGGER.info(message)
        raise e from Exception(message)


class SingleFrameAcquisitionModeStrategy(ABC):
    """
    Implement a camera type specific subclass of this to define on how to enable/disable single frame acquisition mode
    for that camera type.
    """

    @abstractmethod
    def set_single_frame_acquisition_mode(self, ia: ImageAcquirer, is_enabled):
        pass


class SoftwareTriggerStrategy(ABC):
    """
    Implement a camera type specific subclass of this to define on how to execute a software trigger for that camera type
    """

    @abstractmethod
    def trigger_execute(self, ia: ImageAcquirer):
        pass


class OnEnterStrategy(ABC):
    """
    Implement a camera type specific subclass of this to define commands to be sent in the `__enter__` of the context
    """

    @abstractmethod
    def on_enter(self, ia: ImageAcquirer, state: dict):
        pass


class OnExitStrategy(ABC):
    """
    Implement a camera type specific subclass of this to define commands to be sent in the `__exit__` of the context
    """

    @abstractmethod
    def on_exit(self, ia: ImageAcquirer, state: dict):
        pass


class DefaultOnEnterStrategy(OnEnterStrategy):
    def on_enter(self, ia: ImageAcquirer, state: dict):
        pass


class DefaultOnExitStrategy(OnExitStrategy):
    def on_exit(self, ia: ImageAcquirer, state: dict):
        pass
