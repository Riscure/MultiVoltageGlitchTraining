import logging
import platform
from pathlib import Path

from harvesters.core import Harvester

CURRENT_FILE_PATH = Path(__file__).parent

LOGGER = logging.getLogger()


class DriverActivator:
    def __init__(self, harvester_instance: Harvester):
        self._harvester_instance = harvester_instance

    def activate(self):
        LOGGER.info(f"Using camera driver `{type(self).__name__}`")

    @staticmethod
    def get_platform_subfolder():
        assert platform.system().upper() == "WINDOWS"
        architecture = platform.architecture()[0]
        if architecture == '64bit':
            subfolder = 'Win64'
        elif architecture == '32bit':
            subfolder = 'Win32'
        else:
            raise ValueError(f"Unsupported platform: {platform.architecture()}")
        return subfolder

    @staticmethod
    def create(selected_driver, harvester_instance: Harvester) -> "DriverActivator":
        if selected_driver == AlliedVision.__name__.casefold():
            return AlliedVision(harvester_instance)
        elif selected_driver == MatrixVision.__name__.casefold():
            return MatrixVision(harvester_instance)
        else:  # default is AlliedVision as this is our preferred camera
            return AlliedVision(harvester_instance)


class AlliedVision(DriverActivator):
    def activate(self):
        super().activate()
        platform = self.get_platform_subfolder()
        cti_path = str(CURRENT_FILE_PATH / platform / "VimbaGigETL.cti")
        self._harvester_instance.add_file(cti_path)


class MatrixVision(DriverActivator):
    def activate(self):
        super().activate()
        platform = self.get_platform_subfolder()
        cti_path = str(CURRENT_FILE_PATH / platform / "mvGenTLProducer.cti")
        self._harvester_instance.add_file(cti_path)
