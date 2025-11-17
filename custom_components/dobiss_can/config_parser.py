"""
Parser for Dobiss Ambiance config.dobiss XML files.

Extracts module and output configuration data for Home Assistant integration.
"""
import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import List, Optional, Dict

_LOGGER = logging.getLogger(__name__)

# XML Namespaces used in config.dobiss files
NAMESPACES = {
    'dc': 'http://schemas.datacontract.org/2004/07/AmbianceUI.Data',
    'i': 'http://www.w3.org/2001/XMLSchema-instance',
    'z': 'http://schemas.microsoft.com/2003/10/Serialization/',
}

# Module type constants
MODULE_TYPE_RELAY = 8
MODULE_TYPE_DIMMER = 16
MODULE_TYPE_0_10V = 24

# Output type mappings
OUTPUT_TYPE_MAP = {
    'OutputRelais': ('relay', MODULE_TYPE_RELAY),
    'OutputDim': ('dimmer', MODULE_TYPE_DIMMER),
    'Output0To10V': ('0-10v', MODULE_TYPE_0_10V),
}


@dataclass
class DobissOutput:
    """Represents a single output from config.dobiss."""
    name: str
    module: int              # 1-indexed module address
    output_id: int          # 0-indexed output number
    module_type: int        # 8, 16, or 24
    output_type: str        # "relay", "dimmer", or "0-10v"
    area: Optional[str] = None
    max_dim: int = 100

    def __repr__(self):
        return f"DobissOutput(name={self.name!r}, module={self.module}, output={self.output_id}, type={self.output_type}, area={self.area!r})"


class ConfigParseError(Exception):
    """Raised when config.dobiss file cannot be parsed."""
    pass


def parse_config_file(file_path: str) -> List[DobissOutput]:
    """
    Parse a config.dobiss XML file and extract all output configurations.
    
    Args:
        file_path: Path to the config.dobiss file
        
    Returns:
        List of DobissOutput objects
        
    Raises:
        ConfigParseError: If file cannot be parsed or is invalid
    """
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
    except ET.ParseError as err:
        raise ConfigParseError(f"Invalid XML file: {err}")
    except FileNotFoundError:
        raise ConfigParseError(f"File not found: {file_path}")
    except Exception as err:
        raise ConfigParseError(f"Failed to read file: {err}")

    # Build ID map for resolving z:Ref cross-references
    id_map = _build_id_map(root)
    
    # Build name map for outputs defined in _subject elements
    name_map = _build_name_map(root)
    
    # Collect all output elements - both <Output> and those defined inline in <_subject>
    output_elements = []
    
    # Standard Output elements
    for output_elem in root.findall('.//{http://schemas.datacontract.org/2004/07/AmbianceUI.Data}Output'):
        output_elements.append(output_elem)
    
    # Also check _subject elements that define outputs inline (like Bureau werklamp)
    for subject_elem in root.findall('.//{http://schemas.datacontract.org/2004/07/AmbianceUI.Data}_subject'):
        # Check if this subject IS an output type
        output_type_attr = subject_elem.get('{http://www.w3.org/2001/XMLSchema-instance}type')
        if output_type_attr in OUTPUT_TYPE_MAP:
            output_elements.append(subject_elem)
    
    # Extract all outputs
    outputs = []
    skipped_count = 0
    skipped_types = {}
    
    for output_elem in output_elements:
        output_type_attr = output_elem.get('{http://www.w3.org/2001/XMLSchema-instance}type')
        output = _extract_output(output_elem, id_map, name_map)
        
        if output:
            outputs.append(output)
        else:
            skipped_count += 1
            if output_type_attr:
                skipped_types[output_type_attr] = skipped_types.get(output_type_attr, 0) + 1
            
            # Log the name of skipped outputs for debugging
            name_elem = output_elem.find('{http://schemas.datacontract.org/2004/07/AmbianceUI.Data}_displayName')
            if name_elem is not None and name_elem.text:
                _LOGGER.debug(f"Skipped output '{name_elem.text}' with type '{output_type_attr}'")
    
    _LOGGER.debug(f"Parsed {len(outputs)} outputs from config.dobiss, skipped {skipped_count}")
    if skipped_types:
        _LOGGER.debug(f"Skipped types: {skipped_types}")
    
    return outputs


def _build_id_map(root: ET.Element) -> Dict[str, ET.Element]:
    """Build a mapping of z:Id values to elements for resolving references."""
    id_map = {}
    for elem in root.iter():
        z_id = elem.get('{http://schemas.microsoft.com/2003/10/Serialization/}Id')
        if z_id:
            id_map[z_id] = elem
    return id_map


def _build_name_map(root: ET.Element) -> Dict[str, str]:
    """Build a mapping of z:Id to display names found in _subject elements.
    
    Some outputs are defined inline within button actions and have their
    _displayName there instead of in the main Output element.
    """
    name_map = {}
    
    # Find all _subject elements that contain Output definitions
    for subject in root.findall('.//{http://schemas.datacontract.org/2004/07/AmbianceUI.Data}_subject'):
        z_id = subject.get('{http://schemas.microsoft.com/2003/10/Serialization/}Id')
        if not z_id:
            continue
            
        # Check if this subject has a _displayName
        name_elem = subject.find('{http://schemas.datacontract.org/2004/07/AmbianceUI.Data}_displayName')
        if name_elem is not None and name_elem.text:
            name_map[z_id] = name_elem.text
            _LOGGER.debug(f"Found name '{name_elem.text}' for subject z:Id={z_id}")
    
    return name_map


def _extract_output(elem: ET.Element, id_map: Dict[str, ET.Element], name_map: Dict[str, str]) -> Optional[DobissOutput]:
    """
    Extract output information from an Output XML element.
    
    Args:
        elem: The Output XML element
        id_map: Map of z:Id to elements for resolving references
        name_map: Map of z:Id to display names from _subject elements
        
    Returns:
        DobissOutput object or None if element cannot be parsed
    """
    # Check output type (OutputRelais, OutputDim, Output0To10V)
    output_type_attr = elem.get('{http://www.w3.org/2001/XMLSchema-instance}type')
    if not output_type_attr or output_type_attr not in OUTPUT_TYPE_MAP:
        return None
    
    output_type, module_type = OUTPUT_TYPE_MAP[output_type_attr]
    
    # Extract output ID
    output_id_elem = elem.find('{http://schemas.datacontract.org/2004/07/AmbianceUI.Data}ID')
    if output_id_elem is None:
        _LOGGER.warning(f"Output element missing ID")
        return None
    
    try:
        output_id = int(output_id_elem.text)
    except (ValueError, TypeError):
        _LOGGER.warning(f"Invalid output ID: {output_id_elem.text}")
        return None
    
    # Extract name - first try _displayName, then fall back to name_map
    name = None
    name_elem = elem.find('{http://schemas.datacontract.org/2004/07/AmbianceUI.Data}_displayName')
    if name_elem is not None and name_elem.text:
        name = name_elem.text
    else:
        # Check if this element has a z:Id and try to find name in name_map
        z_id = elem.get('{http://schemas.microsoft.com/2003/10/Serialization/}Id')
        if z_id and z_id in name_map:
            name = name_map[z_id]
            _LOGGER.debug(f"Using name from subject map: '{name}' for z:Id={z_id}")
    
    if not name:
        _LOGGER.warning(f"Output {output_id} missing name")
        return None
    
    # Extract parent module information
    parent_elem = elem.find('{http://schemas.datacontract.org/2004/07/AmbianceUI.Data}Parent')
    if parent_elem is None:
        _LOGGER.warning(f"Output {name} missing Parent element")
        return None
    
    # Resolve reference if needed
    parent_ref = parent_elem.get('{http://schemas.microsoft.com/2003/10/Serialization/}Ref')
    if parent_ref and parent_ref in id_map:
        parent_elem = id_map[parent_ref]
    
    # Get module address
    address_elem = parent_elem.find('{http://schemas.datacontract.org/2004/07/AmbianceUI.Data}Address')
    if address_elem is None:
        _LOGGER.warning(f"Output {name} missing module Address")
        return None
    
    try:
        module = int(address_elem.text)
    except (ValueError, TypeError):
        _LOGGER.warning(f"Invalid module address: {address_elem.text}")
        return None
    
    # Extract area/group (optional)
    area = None
    group_elem = elem.find('{http://schemas.datacontract.org/2004/07/AmbianceUI.Data}_group')
    if group_elem is not None:
        # Resolve reference if needed
        group_ref = group_elem.get('{http://schemas.microsoft.com/2003/10/Serialization/}Ref')
        if group_ref and group_ref in id_map:
            group_elem = id_map[group_ref]
        
        area_elem = group_elem.find('{http://schemas.datacontract.org/2004/07/AmbianceUI.Data}DisplayName')
        if area_elem is not None and area_elem.text:
            area = area_elem.text
    
    # Extract max dim for dimmers (optional)
    max_dim = 100
    if output_type == 'dimmer':
        vmax_elem = elem.find('{http://schemas.datacontract.org/2004/07/AmbianceUI.Data}VMax')
        if vmax_elem is not None and vmax_elem.text:
            try:
                max_dim = int(vmax_elem.text)
            except (ValueError, TypeError):
                pass
    
    return DobissOutput(
        name=name,
        module=module,
        output_id=output_id,
        module_type=module_type,
        output_type=output_type,
        area=area,
        max_dim=max_dim,
    )


if __name__ == '__main__':
    # Test the parser
    import sys
    test_file = 'resources/config.dobiss' if len(sys.argv) < 2 else sys.argv[1]
    
    try:
        outputs = parse_config_file(test_file)
        print(f'Successfully parsed {len(outputs)} outputs:\n')
        
        for i, output in enumerate(outputs[:15], 1):
            area_str = f'[{output.area}]' if output.area else '[No area]'
            print(f'{i:2}. {output.name:30} M{output.module} O{output.output_id:2} {output.output_type:8} {area_str}')
        
        if len(outputs) > 15:
            print(f'\n... and {len(outputs) - 15} more outputs')
        
        # Show type distribution
        print(f'\n--- Type Distribution ---')
        from collections import Counter
        types = Counter(o.output_type for o in outputs)
        for otype, count in types.items():
            print(f'{otype}: {count}')
    
    except ConfigParseError as e:
        print(f'Parse error: {e}')
        sys.exit(1)
    except Exception as e:
        print(f'Unexpected error: {e}')
        import traceback
        traceback.print_exc()
        sys.exit(1)
