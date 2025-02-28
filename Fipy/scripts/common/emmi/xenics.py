from harvesters.core import ImageAcquirer

from ._api import (
    log_exception,
    SingleFrameAcquisitionModeStrategy,
    SoftwareTriggerStrategy,
    OnEnterStrategy,
    OnExitStrategy,
)


class XenicsSingleFrameAcquisitionModeStrategy(SingleFrameAcquisitionModeStrategy):
    def set_single_frame_acquisition_mode(self, ia: ImageAcquirer, is_enabled):
        single_frame_acquisition_settings = {'AcquisitionMode': 'Continuous',
                                             'TriggerInMode': "ExternalTriggered" if is_enabled else "FreeRunning",
                                             }
        for key, value in single_frame_acquisition_settings.items():
            with log_exception():
                ia.remote_device.node_map.get_node(key).value = value


class XenicsSoftwareTriggerStrategy(SoftwareTriggerStrategy):
    def trigger_execute(self, ia: ImageAcquirer):
        with log_exception():
            ia.remote_device.node_map.get_node('SoftwareTrigger').execute()


class XenicsOnEnterStrategy(OnEnterStrategy):
    AUTO_MODE_KEY = "AutoModeUpdate"
    AUTOMODE_STOPPED = "Stopped"

    def on_enter(self, ia: ImageAcquirer, state: dict):
        with log_exception():
            state[self.AUTO_MODE_KEY] = ia.remote_device.node_map.get_node(self.AUTO_MODE_KEY).value
            ia.remote_device.node_map.get_node(self.AUTO_MODE_KEY).value = self.AUTOMODE_STOPPED


class XenicsOnExitStrategy(OnExitStrategy):
    AUTO_MODE_KEY = "AutoModeUpdate"

    def on_exit(self, ia: ImageAcquirer, state: dict):
        with log_exception():
            ia.remote_device.node_map.get_node(self.AUTO_MODE_KEY).value = state[self.AUTO_MODE_KEY]
