from harvesters.core import ImageAcquirer

from ._api import log_exception, SingleFrameAcquisitionModeStrategy, SoftwareTriggerStrategy


class AlliedVisionSingleFrameAcquisitionModeStrategy(SingleFrameAcquisitionModeStrategy):
    def set_single_frame_acquisition_mode(self, ia: ImageAcquirer, is_enabled):
        single_frame_acquisition_settings = {'AcquisitionMode': 'Continuous',
                                             'TriggerMode': 'On' if is_enabled else 'Off',
                                             'TriggerSource': 'Software'
                                             }
        for key, value in single_frame_acquisition_settings.items():
            with log_exception():
                ia.remote_device.node_map.get_node(key).value = value


class AlliedVisionSoftwareTriggerStrategy(SoftwareTriggerStrategy):
    def trigger_execute(self, ia: ImageAcquirer):
        with log_exception():
            ia.remote_device.node_map.get_node('TriggerSoftware').execute()
