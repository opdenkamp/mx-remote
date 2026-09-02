######################################################
##            MX Remote Python Interface            ##
##                                                  ##
## author: Lars Op den Kamp (lars@opdenkamp-it.nl)  ##
## copyright (c) 2021-2026 Op den Kamp IT Solutions ##
######################################################
'''Protocol frames for V2IP multiviewer configuration and control.'''

from enum import Enum
from functools import cached_property
from ..compat import override
from .FrameBase import FrameBase
from .Constants import decode_enum
from ..Interface import MxrDeviceUid, DeviceBase, DeviceRegistry
from .Multiviewer import *
import logging

_LOGGER = logging.getLogger(__name__)

class V2IPMultiviewerConfig(FrameBase, MultiviewerConfig):
    '''Parsed multiviewer configuration status with view mode, PIP, audio, and source settings.'''
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
        '''Content protection, including OFF - a mode, not the absence of one.'''
        pl = self.payload_u8(idx=173)
        if (pl is None) or (pl > int(MultiviewerHDCPMode.OFF)):
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
        return MultiviewerSource.from_wire(self.payload_u8(idx=179))

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
        '''Source shown on one screen.

        The report numbers its sources from zero, the same as the audio source
        beside it. Reading them one-based loses source 1 to UNKNOWN and reports
        every other one as its predecessor.
        '''
        if (screen < 0) or (screen >= MULTIVIEWER_MAX_SCREENS):
            return MultiviewerSource.UNKNOWN
        return MultiviewerSource.from_wire(self.payload_u8(idx=182 + screen))

    @property
    @override
    def remote_control(self) -> MultiviewerSource:
        return MultiviewerSource.from_wire(self.payload_u8(idx=186))

    def __eq__(self, value: object) -> bool:
        if not isinstance(value, V2IPMultiviewerConfig):
            return False
        return self.payload == value.payload

    def __str__(self) -> str:
        return f"multiviewer config: {self.uid}/{self.device} - mappings: {self.mappings}, mcu={self.mcu_version}, scaler={self.scaler_version}, view mode={self.view_mode}, pip={self.pip_position}/{self.pip_size}, output={self.output_mode}/{self.hdcp_mode}/{self.output_itc_mode}/{self.aspect_ratio}, edid={self.edid_template}, auto switch={self.auto_switch}, audio={self.audio_source} volume={self.audio_volume}% muted={self.audio_muted}, remote={self.remote_control}"

# Every 0x42 sub-command shares one envelope, as the constructors below build it:
#   0..16    mxr_uid target
#   16..17   u8 sub-opcode (MultiviewerOpcode)
#   17..24   padding
#   24..     sub-command parameters
_PARAMS_OFFSET = 24

# The module's own version is not on the mesh at all. MXR_OP_FIRMWARE_VERSION
# reports the MCU, the FPGA and the Linux image, never a loaded module, so a
# client speaking only this protocol cannot tell which multiviewer build it is
# talking to - and several of its behaviours changed between builds. Where a
# behaviour depends on the module version, say so rather than assuming either
# side of it. The version is readable over HTTP from the device, which is a
# different transport and a different decision.

# One past the last byte a status report is read at, which is the remote-control
# source. The module refuses a report shorter than its settings struct; this is
# the same refusal expressed in terms of what we read.
_STATUS_MIN_SIZE = 187

class FrameV2IPMultiviewer(FrameBase):
    '''V2IP multiviewer command and status frame.'''
    @property
    def target_uid(self) -> MxrDeviceUid|None:
        '''UID of the target multiviewer device.'''
        return self.payload_uuid(idx=0)

    @property
    def target(self) -> DeviceBase|None:
        '''Target multiviewer device.'''
        return self.payload_device(idx=0)

    @property
    def opcode(self) -> MultiviewerOpcode:
        '''Multiviewer sub-command opcode.'''
        pl = self.payload_u8(idx=16)
        if (pl is None) or (pl > 15):
            return MultiviewerOpcode.UNKNOWN
        # `or` would be wrong here: STATUS is zero, so the only sub-opcode
        # that carries device state is the one an `or` discards.
        op = decode_enum(MultiviewerOpcode, pl)
        return op if (op is not None) else MultiviewerOpcode.UNKNOWN

    @cached_property
    def target_uid(self) -> MxrDeviceUid|None:
        '''Multiviewer this frame addresses.'''
        return self.payload_uuid(0)

    @cached_property
    def params(self) -> bytes:
        '''Sub-command parameters.

        Every sub-command shares the same envelope - target uid at 0, the
        sub-opcode at 16, seven pad bytes, parameters from 24 - so the params
        can be exposed without knowing each sub-command's fields. Only STATUS
        carries device state; the other fifteen are commands to a multiviewer,
        and what they change comes back on the next STATUS.
        '''
        if ((pl := self.payload_idx(_PARAMS_OFFSET)) is None):
            return bytes()
        return pl

    @override
    def process(self) -> None:
        '''Update the local device cache with multiviewer configuration.

        Only STATUS is folded into the cache. The rest are requests, and the
        multiviewer reports what it actually did on the STATUS that follows -
        acting on the request as well would report the change twice, and would
        report it even when the multiviewer refused.
        '''
        # A short report is refused rather than decoded. Every field below reads
        # with a fallback, so a truncated one decodes as "the device reported
        # nothing" and replaces a good cached status with that. Length is the
        # only thing separating it from a device genuinely reporting nothing,
        # and the module itself refuses the same frame.
        if (self.opcode != MultiviewerOpcode.STATUS) or (self.payload is None):
            return
        if (len(self.payload) < _STATUS_MIN_SIZE):
            _LOGGER.debug("multiviewer status is %d bytes, need %d", len(self.payload), _STATUS_MIN_SIZE)
            return
        settings = V2IPMultiviewerConfig(header=self.header)
        if ((dev := self.remote_device) is not None):
            dev.on_mxr_update(settings)


    @staticmethod
    def construct_set_view_mode(mxr:DeviceRegistry, target:DeviceBase, view_mode:MultiviewerViewMode) -> FrameBase|None:
        '''Build a frame to set the multiviewer view mode.'''
        payload = bytearray()
        payload += target.remote_id.byte_value
        payload.append(MultiviewerOpcode.VIEW_MODE.value)
        payload += bytes([0 for _ in range(7)])
        payload.append(view_mode.value)
        return FrameBase.construct_base(target=target, mxr=mxr, opcode=0x42, payload=payload)

    @staticmethod
    def construct_set_video_source(mxr:DeviceRegistry, target:DeviceBase, screen:int, source:MultiviewerSource,
                                   screens:int=MULTIVIEWER_MAX_SCREENS) -> FrameBase|None:
        '''Build a frame to set the video source for a screen.

        Both bytes are numbered from zero on the wire. Sending them one-based
        addresses the screen after the one meant and the source before it, and
        leaves the last source unreachable.

        Pass screens when the layout in the last status report shows fewer than
        MULTIVIEWER_MAX_SCREENS: an index the layout does not have is refused
        here, because a multiviewer indexes its window array by whatever it is
        sent and reports nothing when the index is past the end. A caller that
        does not know the layout passes nothing and gets the array width, which
        still bounds the index to a window that exists in every layout.
        '''
        wire_source = source.wire_value
        if (wire_source is None):
            return None
        limit = screens if (0 < screens < MULTIVIEWER_MAX_SCREENS) else MULTIVIEWER_MAX_SCREENS
        if (screen < 0) or (screen >= limit):
            return None
        payload = bytearray()
        payload += target.remote_id.byte_value
        payload.append(MultiviewerOpcode.VIDEO_SOURCE.value)
        payload += bytes([0 for _ in range(7)])
        payload.append(screen)
        payload.append(wire_source)
        return FrameBase.construct_base(target=target, mxr=mxr, opcode=0x42, payload=payload)

    @staticmethod
    def construct_set_audio_source(mxr:DeviceRegistry, target:DeviceBase, source:MultiviewerSource) -> FrameBase|None:
        '''Build a frame to set the audio source.'''
        payload = bytearray()
        payload += target.remote_id.byte_value
        payload.append(MultiviewerOpcode.AUDIO_SOURCE.value)
        payload += bytes([0 for _ in range(7)])
        if ((wire_source := source.wire_value) is None):
            return None
        payload.append(wire_source)
        return FrameBase.construct_base(target=target, mxr=mxr, opcode=0x42, payload=payload)

    @staticmethod
    def construct_set_audio_volume(mxr:DeviceRegistry, target:DeviceBase, volume:int, muted:bool) -> FrameBase|None:
        '''Build a frame to set the audio volume and mute state.'''
        payload = bytearray()
        payload += target.remote_id.byte_value
        payload.append(MultiviewerOpcode.AUDIO_VOLUME.value)
        payload += bytes([0 for _ in range(7)])
        # A volume the module refuses is dropped without a reply, and on some
        # module builds the mute byte beside it is applied anyway - so an
        # out-of-range volume changes the mute and nothing else. Refuse it here.
        if not (0 <= volume <= 100):
            return None
        payload.append(volume)
        payload.append(1 if muted else 0)
        return FrameBase.construct_base(target=target, mxr=mxr, opcode=0x42, payload=payload)

    @staticmethod
    def construct_set_edid_template(mxr:DeviceRegistry, target:DeviceBase, edid:MultiviewerEDIDTemplate) -> FrameBase|None:
        '''Build a frame to set the EDID template.'''
        payload = bytearray()
        payload += target.remote_id.byte_value
        payload.append(MultiviewerOpcode.EDID_TEMPLATE.value)
        payload += bytes([0 for _ in range(7)])
        payload.append(edid.value)
        return FrameBase.construct_base(target=target, mxr=mxr, opcode=0x42, payload=payload)

    @staticmethod
    def construct_set_remote_control(mxr:DeviceRegistry, target:DeviceBase, source:MultiviewerSource) -> FrameBase|None:
        '''Build a frame to set the remote control target source.'''
        payload = bytearray()
        payload += target.remote_id.byte_value
        payload.append(MultiviewerOpcode.ROUTE_RC.value)
        payload += bytes([0 for _ in range(7)])
        if ((wire_source := source.wire_value) is None):
            return None
        payload.append(wire_source)
        return FrameBase.construct_base(target=target, mxr=mxr, opcode=0x42, payload=payload)

    @staticmethod
    def construct_set_pip_size(mxr:DeviceRegistry, target:DeviceBase, size:MultiviewerPipSize) -> FrameBase|None:
        '''Build a frame to set the PIP window size.'''
        payload = bytearray()
        payload += target.remote_id.byte_value
        payload.append(MultiviewerOpcode.PIP_SIZE.value)
        payload += bytes([0 for _ in range(7)])
        payload.append(size.value)
        return FrameBase.construct_base(target=target, mxr=mxr, opcode=0x42, payload=payload)

    @staticmethod
    def construct_set_pip_position(mxr:DeviceRegistry, target:DeviceBase, position:MultiviewerPipPosition) -> FrameBase|None:
        '''Build a frame to set the PIP window position.'''
        payload = bytearray()
        payload += target.remote_id.byte_value
        payload.append(MultiviewerOpcode.PIP_POSITION.value)
        payload += bytes([0 for _ in range(7)])
        payload.append(position.value)
        return FrameBase.construct_base(target=target, mxr=mxr, opcode=0x42, payload=payload)

    @staticmethod
    def construct_set_screen_aspect(mxr:DeviceRegistry, target:DeviceBase, aspect:MultiviewerAspectRatio) -> FrameBase|None:
        '''Build a frame to set the screen aspect ratio.'''
        payload = bytearray()
        payload += target.remote_id.byte_value
        payload.append(MultiviewerOpcode.ASPECT.value)
        payload += bytes([0 for _ in range(7)])
        payload.append(aspect.value)
        return FrameBase.construct_base(target=target, mxr=mxr, opcode=0x42, payload=payload)

    @staticmethod
    def construct_set_auto_switch(mxr:DeviceRegistry, target:DeviceBase, enable:bool) -> FrameBase|None:
        '''Build a frame to enable or disable auto-switch.'''
        payload = bytearray()
        payload += target.remote_id.byte_value
        payload.append(MultiviewerOpcode.AUTO_SWITCH.value)
        payload += bytes([0 for _ in range(7)])
        payload.append(1 if enable else 0)
        return FrameBase.construct_base(target=target, mxr=mxr, opcode=0x42, payload=payload)

    @staticmethod
    def construct_set_output_mode(mxr:DeviceRegistry, target:DeviceBase, mode:MultiviewerOutputMode) -> FrameBase|None:
        '''Build a frame to set the output resolution mode.'''
        payload = bytearray()
        payload += target.remote_id.byte_value
        payload.append(MultiviewerOpcode.OUTPUT_MODE.value)
        payload += bytes([0 for _ in range(7)])
        payload.append(mode.value)
        return FrameBase.construct_base(target=target, mxr=mxr, opcode=0x42, payload=payload)

    @staticmethod
    def construct_set_output_itc_mode(mxr:DeviceRegistry, target:DeviceBase, mode:MultiviewerITCMode) -> FrameBase|None:
        '''Build a frame to set the output ITC mode.'''
        payload = bytearray()
        payload += target.remote_id.byte_value
        payload.append(MultiviewerOpcode.OUTPUT_ITC_MODE.value)
        payload += bytes([0 for _ in range(7)])
        payload.append(mode.value)
        return FrameBase.construct_base(target=target, mxr=mxr, opcode=0x42, payload=payload)

    @staticmethod
    def construct_set_hdcp_mode(mxr:DeviceRegistry, target:DeviceBase, mode:MultiviewerHDCPMode) -> FrameBase|None:
        '''Build a frame to set the HDCP mode.

        UNKNOWN is not a mode a multiviewer can be put into - it is what this
        client calls a value it did not recognise - so it is refused here.
        '''
        if (mode == MultiviewerHDCPMode.UNKNOWN):
            return None
        payload = bytearray()
        payload += target.remote_id.byte_value
        payload.append(MultiviewerOpcode.HDCP_MODE.value)
        payload += bytes([0 for _ in range(7)])
        payload.append(mode.value)
        return FrameBase.construct_base(target=target, mxr=mxr, opcode=0x42, payload=payload)

    @staticmethod
    def construct_set_connected_source(mxr:DeviceRegistry, target:DeviceBase, input:int, source:MxrDeviceUid|None) -> FrameBase|None:
        '''Build a frame to assign a source device to a multiviewer input.'''
        payload = bytearray()
        payload += target.remote_id.byte_value
        payload.append(MultiviewerOpcode.CONFIG_SOURCE.value)
        payload += bytes([0 for _ in range(7)])
        if (source is None):
            payload += bytes([0 for _ in range(16)])
        else:
            payload += source.byte_value
        payload.append(input)
        payload += bytes([0 for _ in range(7)])
        return FrameBase.construct_base(target=target, mxr=mxr, opcode=0x42, payload=payload)

    @staticmethod
    def construct_auto_route(mxr:DeviceRegistry, target:DeviceBase) -> FrameBase|None:
        '''Build a frame to trigger automatic source routing.'''
        payload = bytearray()
        payload += target.remote_id.byte_value
        payload.append(MultiviewerOpcode.AUTO_ROUTE.value)
        payload += bytes([0 for _ in range(7)])
        return FrameBase.construct_base(target=target, mxr=mxr, opcode=0x42, payload=payload)

    @staticmethod
    def construct_status(
        mxr:DeviceRegistry,
        *,
        own_uid:MxrDeviceUid,
        mappings:list[MxrDeviceUid|None]|tuple[MxrDeviceUid|None, ...] = (None, None, None, None),
        fw_mcu:str = "",
        fw_scaler:str = "",
        config:MultiviewerConfigData|None = None,
    ) -> FrameBase|None:
        '''Build a STATUS broadcast frame advertising this MV's configuration.'''
        if len(mappings) != 4:
            raise ValueError("mappings must have exactly 4 entries")
        mapping_bytes:list[bytes] = [
            (b"\x00" * 16) if m is None else m.byte_value for m in mappings
        ]
        payload = bytearray()
        payload += own_uid.byte_value
        payload.append(MultiviewerOpcode.STATUS.value)
        payload += bytes([0 for _ in range(7)])
        payload += pack_multiviewer_settings(
            uid=own_uid.byte_value,
            mappings=mapping_bytes,
            fw_mcu=fw_mcu,
            fw_scaler=fw_scaler,
            config=config,
        )
        return FrameBase.construct_base(mxr=mxr, opcode=0x42, payload=bytes(payload))

    def __str__(self) -> str:
        if (self.opcode == MultiviewerOpcode.STATUS):
            return f"{str(self.remote_device)} multiviewer status"
        target = self.mxr.get_by_uid(uid) if ((uid := self.target_uid) is not None) else None
        who = target if (target is not None) else self.target_uid
        params = self.params.hex(' ') if (len(self.params) > 0) else "none"
        return f"{who} multiviewer request: {self.opcode.name.lower()} params [{params}]"
