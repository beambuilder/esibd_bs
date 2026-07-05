"""CGC devices module."""

from .cgc_device import CGCDevice, CGCStatusError
from .ampr import AMPR
from .ampr.ampr_base import AMPRBase
from .esi import ESI
from .esi.esi_base import ESIBase
from .pA import PA
from .pA.pA_base import PABase
from .psu import PSU
from .psu.psu_base import PSUBase
from .sw import SW
from .sw.sw_base import SWBase
from .sw_HR import SWHR
from .sw_HR.sw_HR_base import SWHRBase
from .campaign import (
    PSUWatchdog, WatchdogBreach, ramp_voltage_at_1khz, ramp_frequency,
    I_LIMIT_MA, P_LIMIT_W, RAMP_FREQ_KHZ, V_MAX,
)

__all__ = [
    'CGCDevice', 'CGCStatusError',
    'AMPR', 'AMPRBase',
    'ESI', 'ESIBase',
    'PA', 'PABase',
    'PSU', 'PSUBase',
    'SW', 'SWBase',
    'SWHR', 'SWHRBase',
    'PSUWatchdog', 'WatchdogBreach',
    'ramp_voltage_at_1khz', 'ramp_frequency',
    'I_LIMIT_MA', 'P_LIMIT_W', 'RAMP_FREQ_KHZ', 'V_MAX',
]
