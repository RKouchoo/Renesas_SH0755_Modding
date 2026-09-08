#!/usr/bin/env python3
"""Build separate idle captures within D2WD610H's native SSM receive limit."""
from pathlib import Path
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
MAX_RECEIVE_INDEX = 0x89  # ROM 32D90; 32CA4 clamps C7A9 to this index.
MAX_ADDRESSES = (MAX_RECEIVE_INDEX - 6) // 3
IDLE_PROFILE = HERE / 'D2WD610H_idle_diagnostic_profile.xml'
AFTERSTART_PROFILE = HERE / 'D2WD610H_afterstart_diagnostic_profile.xml'
RECOVERY_PROFILE = HERE / 'D2WD610H_idle_recovery_profile.xml'
IDLE_AIR_PROFILE = HERE / 'D2WD610H_idle_air_diagnostic_profile.xml'
MAP_SOURCE_PROFILE = HERE / 'D2WD610H_map_source_diagnostic_profile.xml'
IDLE_PARAMETERS = {
    'P2', 'P3', 'P4', 'P5', 'P6', 'P8', 'P10', 'P11', 'P12', 'P13',
    'P17', 'P21', 'P24', 'P47', 'E32', 'E33', 'E50', 'E51', 'E60',
    'E500', 'E501', 'E502',
}
AFTERSTART_PARAMETERS = {
    'P2', 'P7', 'P8', 'P11', 'P17', 'P21', 'P47', 'E33', 'E123', 'E500',
    'E507', 'E508', 'E509', 'E510', 'E511', 'E512', 'E513',
}
RECOVERY_PARAMETERS = (IDLE_PARAMETERS - {'P3', 'P4', 'P5', 'P6', 'P24', 'E502'}) | {
    'E123', 'E511', 'E503',
}
IDLE_AIR_PARAMETERS = {
    'P2', 'P7', 'P8', 'P10', 'P11', 'P12', 'P13', 'P17', 'P30',
    'E32', 'E33', 'E60', 'E123', 'E500', 'E501', 'E511', 'E514', 'E515', 'E517',
}
MAP_SOURCE_PARAMETERS = {
    'P2', 'P8', 'P10', 'P11', 'P12', 'P13', 'E32', 'E33', 'E51', 'E60',
    'E500', 'E503', 'E511', 'E518', 'E519', 'E520', 'E521', 'E522', 'E523',
}
PROFILE_SELECTIONS = {
    IDLE_PROFILE: IDLE_PARAMETERS,
    AFTERSTART_PROFILE: AFTERSTART_PARAMETERS,
    RECOVERY_PROFILE: RECOVERY_PARAMETERS,
    IDLE_AIR_PROFILE: IDLE_AIR_PARAMETERS,
    MAP_SOURCE_PROFILE: MAP_SOURCE_PARAMETERS,
}
UNIT_OVERRIDES = {path: {'E123': 'fuel-air equivalence ratio'}
                  for path in (RECOVERY_PROFILE, IDLE_AIR_PROFILE)}
UNITS = {
    'P2': 'C', 'P3': '%', 'P4': '%', 'P5': '%', 'P6': '%', 'P7': 'kPa',
    'P8': 'rpm', 'P10': 'degrees', 'P11': 'C', 'P12': 'g/s', 'P13': '%',
    'P17': 'V', 'P21': 'ms', 'P24': 'mmHg', 'P30': '%', 'P38': '%', 'P47': '%', 'P92': '%',
    'E32': 'g/rev', 'E33': 'status', 'E50': 'ms', 'E51': 'kPa absolute',
    'E60': 'ms', 'E81': '%', 'E84': 'estimated AFR', 'E105': '%',
    'E123': 'estimated AFR', 'E500': 'estimated AFR (14.64 stoich)',
    'E501': 'ADC counts', 'E502': 'ready metric',
    'E503': 'AVLS mode (1 low; 3 high)',
    'E504': 'state (0 idle; 1 delay; 2 monitor; 3 cut)',
    'E505': 'task calls', 'E506': 'raw flags', 'E507': 'task calls',
    **{f'E{i}': 'raw additive factor' for i in range(508, 514)},
    'E514': 'rpm', 'E515': '%', 'E516': 'raw flags', 'E517': 'raw flags',
    'E518': 'kPa absolute', 'E519': 'Volts', 'E520': 'kPa absolute',
    'E521': 'raw flags', 'E522': 'raw flags', 'E523': 'raw flags',
}
SWITCHES = {'S4', 'S5', 'S11'}


def request_sizes(address_count):
    """Return payload/frame sizes, refusing unreachable native checksum offsets."""
    payload = 2 + 3 * address_count
    frame = payload + 5
    if not 1 <= address_count <= MAX_ADDRESSES:
        raise ValueError(
            f'{address_count} SSM addresses make a {frame}-byte request with '
            f'checksum at index {frame - 1}; native receive index stops at '
            f'{MAX_RECEIVE_INDEX} (maximum {MAX_ADDRESSES} addresses)')
    return payload, frame


def profile_bytes(selected, overrides=None):
    root = ET.Element('profile', protocol='SSM')
    root.append(ET.Comment(
        ' D2WD610H: at most 43 byte addresses per request. Load one capture '
        'at a time. Inactive entries clear the other capture and old selections. '))
    params = ET.SubElement(root, 'parameters')
    for parameter_id, units in UNITS.items():
        units = (overrides or {}).get(parameter_id, units)
        attrs = {'id': parameter_id}
        if parameter_id in selected:
            attrs.update(livedata='selected', dash='selected')
        attrs['units'] = units
        ET.SubElement(params, 'parameter', attrs)
    switches = ET.SubElement(root, 'switches')
    for switch_id in sorted(SWITCHES, key=lambda i: int(i[1:])):
        ET.SubElement(switches, 'switch', id=switch_id)
    ET.indent(root, space='    ')
    return ET.tostring(root, encoding='ISO-8859-1', xml_declaration=True) + b'\n'


if __name__ == '__main__':
    for path, selected in PROFILE_SELECTIONS.items():
        path.write_bytes(profile_bytes(selected, UNIT_OVERRIDES.get(path)))
        print(path)
