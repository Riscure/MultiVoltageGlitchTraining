import logging

from genicam.genapi import LogicalErrorException
from genicam.gentl import InvalidParameterException
from harvesters.core import Harvester, Component2DImage

from ._api import SingleFrameAcquisitionModeStrategy, SoftwareTriggerStrategy, OnEnterStrategy, OnExitStrategy, \
    DefaultOnEnterStrategy, DefaultOnExitStrategy
from .drivers import DriverActivator
from .alliedvision import AlliedVisionSingleFrameAcquisitionModeStrategy, AlliedVisionSoftwareTriggerStrategy
from .xenics import XenicsSoftwareTriggerStrategy, XenicsSingleFrameAcquisitionModeStrategy, XenicsOnEnterStrategy, \
    XenicsOnExitStrategy

_logger = logging.getLogger()


class EmmiCamera:
    def __init__(self,
                 single_frame_acquisition_mode_strategy: SingleFrameAcquisitionModeStrategy,
                 software_trigger_strategy: SoftwareTriggerStrategy,
                 on_enter_strategy: OnEnterStrategy,
                 on_exit_strategy: OnExitStrategy,
                 gentl_driver="AlliedVision"):
        """
        This is a small wrapper around the Camera API which provides a small subset of the camera's features.
        Note: Use ``EmmiCamera.create(...)`` instead of the constructor in most cases to create an instance of this class.

        :param gentl_driver: The GenTL driver to use. Possible values are ``["AlliedVision", "MatrixVision"]``,
            defaults to ``"AlliedVision"``

        It brings the camera into a software-triggered single frame acquisition state and provides API to
          - take images
          - set sensor exposure time

        For more control over the camera device
          - consult the Genicam specification (https://www.emva.org/standards-technology/genicam/genicam-downloads/)
          - consult the camera device documentation
          - contact Riscure support

        Usage example:
        >>> camera = EmmiCamera.create() # instantiate camera device and scan for cameras (that may take a while)
        >>> camera.set_exposure_time(1.0) # Set exposure to 1 second.
        >>> with camera: # use the ``with`` statement to prepare the camera for image acquisition
        ...     img = camera.acquire_image() # img contains the image data as numpy array
        ...     img2 = camera.acquire_image() # acquire another image
        >>> # Leaving the scope of the ``with`` context manager will release the image acquirer.
        >>> # To take more images a new instance of ``EmmiCamera`` needs to be created.
        """
        self._software_trigger_strategy = software_trigger_strategy
        self._single_frame_acquisition_mode_strategy = single_frame_acquisition_mode_strategy
        self._on_enter_strategy = on_enter_strategy
        self._on_exit_strategy = on_exit_strategy
        self._state = {}

        self._h = Harvester()

        driver_activator = DriverActivator.create(
            gentl_driver.casefold(),
            self._h)
        driver_activator.activate()

        _logger.info("Scanning for cameras. That may take a while")
        self._h.update()  # This takes a while as it needs to scan the network interfaces for camera devices.
        # Try and open the first (genicam compatible) camera device that has been found.
        try:
            self._ia = self._h.create_image_acquirer(list_index=0)
        except (IndexError, InvalidParameterException) as e:
            message = ("Failed to open camera device. *Hint*: Ensure that the camera is connected, powered "
                       "and that no other process uses the camera, e.g. the Joystick panel.")
            _logger.info(message)
            raise e from Exception(message)

    def __enter__(self):
        """
        On entering the ``with`` context manager, prepare the camera device for single frame acquisition.
        :return: this EmmiCamera instance
        """
        self._state["ExposureTime"] = self.get_exposure_time()
        self._set_single_frame_acquisition_mode(True)
        self._on_enter_strategy.on_enter(self._ia, self._state)
        self._ia.start_acquisition()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        On leaving the ``with`` context, disable single frame acquistion and release the camera device.
        """
        self.set_exposure_time(self._state["ExposureTime"])
        self._on_exit_strategy.on_exit(self._ia, self._state)
        self._set_single_frame_acquisition_mode(False)
        self._ia.destroy()
        self._h.reset()

    def _set_single_frame_acquisition_mode(self, is_enabled: bool):
        self._single_frame_acquisition_mode_strategy.set_single_frame_acquisition_mode(self._ia, is_enabled)

    def _set_feature_node_value(self, key, value):
        """
        Set a camera setting by writing to a genicam feature node.
        See Genicam Standard Features Naming Convention (SFNC) and/or the camera device
        manual for a full list of supported feature nodes.

        :param key: Name of feature node
        :param value: Value of feature node. Must have the right type.
        """
        try:
            node = self._ia.remote_device.node_map.get_node(key)
            node.value = value
        except LogicalErrorException as e:
            message = "Feature not supported by this camera."
            _logger.info(message)
            raise e from Exception(message)

    def _get_feature_node_value(self, key):
        """
        Get a camera setting by reading from a genicam feature node.
        See Genicam Standard Features Naming Convention (SFNC) and/or the camera device
        manual for a full list of supported feature nodes.

        :param key: Name of feature node
        """
        node = self._ia.remote_device.node_map.get_node(key)
        return node.value

    def set_exposure_time(self, seconds: float):
        """
        Set sensor exposure time.
        :param seconds: exposure time in seconds
        """
        self._set_feature_node_value('ExposureTime', seconds * 1e6)  # internally the camera uses microseconds.

    def get_exposure_time(self) -> float:
        """
        Get sensor exposure time.
        """
        return float(self._get_feature_node_value('ExposureTime')) / 1.e6  # internally the camera uses microseconds.

    def acquire_image(self):
        """
        Acquire an image.
        This is a blocking call and will only return after acquisition is complete,
        so it takes at least as long as the configured exposure time.
        :return: image data as numpy array.
        """
        self._software_trigger_strategy.trigger_execute(self._ia)
        with self._ia.fetch_buffer(timeout=10.0) as b:
            image_data: Component2DImage = b.payload.components[0]
            image_data_reshaped = image_data.data.reshape((image_data.height, image_data.width), order='C')
            return image_data_reshaped.copy()

    @staticmethod
    def create(camera_type: str = "AlliedVision"):
        """
        Creates a camera type specific instance of an EmmiCamera

        :param camera_type: One of ``"AlliedVision"`` or ``"Xenics"``
        :return: An EmmiCamera instance configured for the specified camera type
        """
        if camera_type.casefold() == "AlliedVision".casefold():
            return EmmiCamera(
                single_frame_acquisition_mode_strategy=AlliedVisionSingleFrameAcquisitionModeStrategy(),
                software_trigger_strategy=AlliedVisionSoftwareTriggerStrategy(),
                on_enter_strategy=DefaultOnEnterStrategy(),
                on_exit_strategy=DefaultOnExitStrategy(),
                gentl_driver="AlliedVision",
            )
        elif camera_type.casefold() == "Xenics".casefold():
            return EmmiCamera(
                single_frame_acquisition_mode_strategy=XenicsSingleFrameAcquisitionModeStrategy(),
                software_trigger_strategy=XenicsSoftwareTriggerStrategy(),
                on_enter_strategy=XenicsOnEnterStrategy(),
                on_exit_strategy=XenicsOnExitStrategy(),
                gentl_driver="MatrixVision"
            )
        else:
            raise ValueError("camera_type should be one of 'AlliedVision' or 'Xenics'")
