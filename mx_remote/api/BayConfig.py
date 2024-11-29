##################################################
##         MX Remote Python Interface           ##
##                                              ##
## author: Lars Op den Kamp (lars@opdenkamp.eu) ##
## copyright (c) 2024 Op den Kamp IT Solutions  ##
##################################################

class BayConfig:
    ''' Bay details from the api '''
    def __init__(self, bay):
        self.bay = bay
        self._data = None

    @property
    def name(self) -> str:
        if (self._data is None) or ('Name' not in self._data.keys()):
            return None
        return self._data['Name']

    @property
    def bay_type(self) -> str:
        if (self._data is None) or ('Name' not in self._data.keys()):
            return "Unknown"
        return self._data['Type']

    @property
    def status(self) -> int:
        if (self._data is None) or ('Status' not in self._data.keys()):
            return -1
        return int(self._data['Status'])

    @property
    def hidden(self) -> bool:
        return (self._data is not None) and ('Hidden' in self._data.keys()) and (self._data['Hidden'])

    @property
    def is_hdmi(self) -> bool:
        return (self.bay_type[0:4] == 'HDMI')

    @property
    def is_hdbt(self) -> bool:
        return (self.bay_type[0:4] == 'HDBT')

    @property
    def is_audio(self) -> bool:
        return (self.bay_type[0:5] == 'AUDIO')

    @property
    def cec_version(self) -> int:
        if (self._data is None) or ('CEC_version' not in self._data.keys()):
            return None
        return int(self._data['CEC_version'])

