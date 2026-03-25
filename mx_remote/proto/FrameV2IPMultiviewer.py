##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2026 Op den Kamp IT Solutions  ##
##################################################

from enum import Enum
from typing import override
from .FrameBase import FrameBase
from ..Interface import MxrDeviceUid, DeviceBase, DeviceRegistry
from .Multiviewer import *

class V2IPMultiviewerConfig(FrameBase, MultiviewerConfig):
    @property
    @override
    def uid(self) -> MxrDeviceUid|None:
        return self.payload_uuid(idx=24)

    @property
    def device(self) -> DeviceBase|None:
        return self.payload_device(idx=24)

    @override
    def mapping(self, idx:int) -> MxrDeviceUid|None:
        return self.payload_uuid(idx=40 + (idx * 16))

    @property
    @override
    def mappings(self) -> list[MxrDeviceUid|None]:
        rv = []
        for idx in range(4):
            rv.append(self.mapping(idx=idx))
        return rv

    @property
    @override
    def mcu_version(self) -> str|None:
        return self.payload_str(idx=(40 + (4 * 16)), length=32)

    @property
    @override
    def scaler_version(self) -> str|None:
        return self.payload_str(idx=(40 + (6 * 16)), length=32)

    @property
    @override
    def hw_view_mode(self) -> int|None:
        return self.payload_u8(idx=168)

    @property
    @override
    def view_mode(self) -> MultiviewerViewMode:
        pl = self.payload_u8(idx=169)
        if (pl is None) or (pl > 8):
            return MultiviewerViewMode.UNKNOWN
        return MultiviewerViewMode(pl)

    @property
    @override
    def pip_position(self) -> MultiviewerPipPosition:
        pl = self.payload_u8(idx=170)
        if (pl is None) or (pl > 4):
            return MultiviewerPipPosition.UNKNOWN
        return MultiviewerPipPosition(pl)

    @property
    @override
    def pip_size(self) -> MultiviewerPipSize:
        pl = self.payload_u8(idx=171)
        if (pl is None) or (pl > 3):
            return MultiviewerPipSize.UNKNOWN
        return MultiviewerPipSize(pl)

    @property
    @override
    def output_mode(self) -> MultiviewerOutputMode:
        pl = self.payload_u8(idx=172)
        if (pl is None) or (pl > 14):
            return MultiviewerOutputMode.UNKNOWN
        return MultiviewerOutputMode(pl)

    @property
    @override
    def hdcp_mode(self) -> MultiviewerHDCPMode:
        pl = self.payload_u8(idx=173)
        if (pl is None) or (pl > 2):
            return MultiviewerHDCPMode.UNKNOWN
        return MultiviewerHDCPMode(pl)

    @property
    @override
    def output_itc_mode(self) -> MultiviewerITCMode:
        pl = self.payload_u8(idx=174)
        if (pl is None) or (pl > 2):
            return MultiviewerITCMode.UNKNOWN
        return MultiviewerITCMode(pl)

    @property
    @override
    def edid_template(self) -> MultiviewerEDIDTemplate:
        pl = self.payload_u8(idx=175)
        if (pl is None) or (pl > 19):
            return MultiviewerEDIDTemplate.UNKNOWN
        return MultiviewerEDIDTemplate(pl)

    @property
    @override
    def aspect_ratio(self) -> MultiviewerAspectRatio:
        pl = self.payload_u8(idx=177)
        if (pl is None) or (pl > 19):
            return MultiviewerAspectRatio.UNKNOWN
        return MultiviewerAspectRatio(pl)

    @property
    @override
    def auto_switch(self) -> MultiviewerBoolSetting:
        pl = self.payload_u8(idx=178)
        if (pl is None) or (pl > 1):
            return MultiviewerBoolSetting.UNKNOWN
        return MultiviewerBoolSetting(pl)

    @property
    @override
    def audio_source(self) -> MultiviewerSource:
        pl = self.payload_u8(idx=179)
        if (pl is None) or (pl > 3):
            return MultiviewerSource.UNKNOWN
        return MultiviewerSource(pl + 1)

    @property
    @override
    def audio_volume(self) -> int:
        pl = self.payload_u8(idx=180)
        if (pl is None) or (pl > 100):
            return 0
        return pl

    @property
    @override
    def audio_muted(self) -> MultiviewerBoolSetting:
        pl = self.payload_u8(idx=181)
        if (pl is None) or (pl > 1):
            return MultiviewerBoolSetting.UNKNOWN
        return MultiviewerBoolSetting(pl)

    @override
    def video_source(self, screen:int) -> MultiviewerSource:
        pl = self.payload_u8(idx=182 + screen)
        if (pl is None) or (pl > 4):
            return MultiviewerSource.UNKNOWN
        return MultiviewerSource(pl)

    @property
    @override
    def remote_control(self) -> MultiviewerSource:
        pl = self.payload_u8(idx=186)
        if (pl is None) or (pl > 3):
            return MultiviewerSource.UNKNOWN
        return MultiviewerSource(pl + 1)

    def __eq__(self, value: object) -> bool:
        if not isinstance(value, V2IPMultiviewerConfig):
            return False
        return self.payload == value.payload

    def __str__(self) -> str:
        return f"multiviewer config: {self.uid}/{self.device} - mappings: {self.mappings}, mcu={self.mcu_version}, scaler={self.scaler_version}, view mode={self.view_mode}, pip={self.pip_position}/{self.pip_size}, output={self.output_mode}/{self.hdcp_mode}/{self.output_itc_mode}/{self.aspect_ratio}, edid={self.edid_template}, auto switch={self.auto_switch}, audio={self.audio_source} volume={self.audio_volume}% muted={self.audio_muted}, remote={self.remote_control}"

class FrameV2IPMultiviewer(FrameBase):
    @property
    def target_uid(self) -> MxrDeviceUid|None:
        return self.payload_uuid(idx=0)

    @property
    def target(self) -> DeviceBase|None:
        return self.payload_device(idx=0)

    @property
    def opcode(self) -> MultiviewerOpcode:
        pl = self.payload_u8(idx=16)
        if (pl is None) or (pl > 15):
            return MultiviewerOpcode.UNKNOWN
        return MultiviewerOpcode(pl)

    @override
    def process(self) -> None:
        opcode = self.opcode
        if (opcode is None) or (self.payload is None):
            print("unknown multiviewer opcode")
            return
        if (opcode == MultiviewerOpcode.STATUS):
            settings = V2IPMultiviewerConfig(header=self.header)
            if ((dev := self.remote_device) is not None):
                dev.on_mxr_update(settings)
        elif (opcode == MultiviewerOpcode.VIEW_MODE):
            pl = self.payload_u8(idx=24)
            if (pl is not None) and (pl <= 8):
                mode = MultiviewerViewMode(pl)
                print(f"set view mode to {mode}")


    @staticmethod
    def construct_set_view_mode(mxr:DeviceRegistry, target:DeviceBase, view_mode:MultiviewerViewMode) -> FrameBase|None:
        payload = bytearray()
        payload += target.remote_id.byte_value
        payload.append(MultiviewerOpcode.VIEW_MODE.value)
        payload += bytes([0 for _ in range(7)])
        payload.append(view_mode.value)
        return FrameBase.construct_base(mxr=mxr, opcode=0x42, protocol=0x20, payload=payload)

    @staticmethod
    def construct_set_video_source(mxr:DeviceRegistry, target:DeviceBase, screen:int, source:MultiviewerSource) -> FrameBase|None:
        payload = bytearray()
        payload += target.remote_id.byte_value
        payload.append(MultiviewerOpcode.VIDEO_SOURCE.value)
        payload += bytes([0 for _ in range(7)])
        payload.append(screen)
        payload.append(source.value)
        return FrameBase.construct_base(mxr=mxr, opcode=0x42, protocol=0x20, payload=payload)

    @staticmethod
    def construct_set_audio_source(mxr:DeviceRegistry, target:DeviceBase, source:MultiviewerSource) -> FrameBase|None:
        payload = bytearray()
        payload += target.remote_id.byte_value
        payload.append(MultiviewerOpcode.AUDIO_SOURCE.value)
        payload += bytes([0 for _ in range(7)])
        payload.append(source.value - 1)
        return FrameBase.construct_base(mxr=mxr, opcode=0x42, protocol=0x20, payload=payload)

    @staticmethod
    def construct_set_audio_volume(mxr:DeviceRegistry, target:DeviceBase, volume:int, muted:bool) -> FrameBase|None:
        payload = bytearray()
        payload += target.remote_id.byte_value
        payload.append(MultiviewerOpcode.AUDIO_VOLUME.value)
        payload += bytes([0 for _ in range(7)])
        payload.append(volume)
        payload.append(1 if muted else 0)
        return FrameBase.construct_base(mxr=mxr, opcode=0x42, protocol=0x20, payload=payload)

    @staticmethod
    def construct_set_edid_template(mxr:DeviceRegistry, target:DeviceBase, edid:MultiviewerEDIDTemplate) -> FrameBase|None:
        payload = bytearray()
        payload += target.remote_id.byte_value
        payload.append(MultiviewerOpcode.EDID_TEMPLATE.value)
        payload += bytes([0 for _ in range(7)])
        payload.append(edid.value)
        return FrameBase.construct_base(mxr=mxr, opcode=0x42, protocol=0x20, payload=payload)

    @staticmethod
    def construct_set_remote_control(mxr:DeviceRegistry, target:DeviceBase, source:MultiviewerSource) -> FrameBase|None:
        payload = bytearray()
        payload += target.remote_id.byte_value
        payload.append(MultiviewerOpcode.ROUTE_RC.value)
        payload += bytes([0 for _ in range(7)])
        payload.append(source.value - 1)
        return FrameBase.construct_base(mxr=mxr, opcode=0x42, protocol=0x20, payload=payload)

    @staticmethod
    def construct_set_pip_size(mxr:DeviceRegistry, target:DeviceBase, size:MultiviewerPipSize) -> FrameBase|None:
        payload = bytearray()
        payload += target.remote_id.byte_value
        payload.append(MultiviewerOpcode.PIP_SIZE.value)
        payload += bytes([0 for _ in range(7)])
        payload.append(size.value)
        return FrameBase.construct_base(mxr=mxr, opcode=0x42, protocol=0x20, payload=payload)

    @staticmethod
    def construct_set_pip_position(mxr:DeviceRegistry, target:DeviceBase, position:MultiviewerPipPosition) -> FrameBase|None:
        payload = bytearray()
        payload += target.remote_id.byte_value
        payload.append(MultiviewerOpcode.PIP_POSITION.value)
        payload += bytes([0 for _ in range(7)])
        payload.append(position.value)
        return FrameBase.construct_base(mxr=mxr, opcode=0x42, protocol=0x20, payload=payload)

    @staticmethod
    def construct_set_screen_aspect(mxr:DeviceRegistry, target:DeviceBase, aspect:MultiviewerAspectRatio) -> FrameBase|None:
        payload = bytearray()
        payload += target.remote_id.byte_value
        payload.append(MultiviewerOpcode.ASPECT.value)
        payload += bytes([0 for _ in range(7)])
        payload.append(aspect.value)
        return FrameBase.construct_base(mxr=mxr, opcode=0x42, protocol=0x20, payload=payload)

    @staticmethod
    def construct_set_auto_switch(mxr:DeviceRegistry, target:DeviceBase, enable:bool) -> FrameBase|None:
        payload = bytearray()
        payload += target.remote_id.byte_value
        payload.append(MultiviewerOpcode.AUTO_SWITCH.value)
        payload += bytes([0 for _ in range(7)])
        payload.append(1 if enable else 0)
        return FrameBase.construct_base(mxr=mxr, opcode=0x42, protocol=0x20, payload=payload)

    @staticmethod
    def construct_set_output_mode(mxr:DeviceRegistry, target:DeviceBase, mode:MultiviewerOutputMode) -> FrameBase|None:
        payload = bytearray()
        payload += target.remote_id.byte_value
        payload.append(MultiviewerOpcode.OUTPUT_MODE.value)
        payload += bytes([0 for _ in range(7)])
        payload.append(mode.value)
        return FrameBase.construct_base(mxr=mxr, opcode=0x42, protocol=0x20, payload=payload)

    @staticmethod
    def construct_set_output_itc_mode(mxr:DeviceRegistry, target:DeviceBase, mode:MultiviewerITCMode) -> FrameBase|None:
        payload = bytearray()
        payload += target.remote_id.byte_value
        payload.append(MultiviewerOpcode.OUTPUT_ITC_MODE.value)
        payload += bytes([0 for _ in range(7)])
        payload.append(mode.value)
        return FrameBase.construct_base(mxr=mxr, opcode=0x42, protocol=0x20, payload=payload)

    @staticmethod
    def construct_set_hdcp_mode(mxr:DeviceRegistry, target:DeviceBase, mode:MultiviewerHDCPMode) -> FrameBase|None:
        payload = bytearray()
        payload += target.remote_id.byte_value
        payload.append(MultiviewerOpcode.HDCP_MODE.value)
        payload += bytes([0 for _ in range(7)])
        payload.append(mode.value)
        return FrameBase.construct_base(mxr=mxr, opcode=0x42, protocol=0x20, payload=payload)

    @staticmethod
    def construct_set_connected_source(mxr:DeviceRegistry, target:DeviceBase, input:int, source:MxrDeviceUid|None) -> FrameBase|None:
        payload = bytearray()
        payload += target.remote_id.byte_value
        payload.append(MultiviewerOpcode.CONFIG_SOURCE.value)
        payload += bytes([0 for _ in range(7)])
        payload.append(input)
        if (source is None):
            payload += bytes([0 for _ in range(16)])
        else:
            payload += source.byte_value
        return FrameBase.construct_base(mxr=mxr, opcode=0x42, protocol=0x20, payload=payload)

    @staticmethod
    def construct_auto_route(mxr:DeviceRegistry, target:DeviceBase) -> FrameBase|None:
        payload = bytearray()
        payload += target.remote_id.byte_value
        payload.append(MultiviewerOpcode.AUTO_ROUTE.value)
        payload += bytes([0 for _ in range(7)])
        return FrameBase.construct_base(mxr=mxr, opcode=0x42, protocol=0x20, payload=payload)

    def __str__(self) -> str:
        return f"{str(self.remote_device)} multiviewer configuration"
