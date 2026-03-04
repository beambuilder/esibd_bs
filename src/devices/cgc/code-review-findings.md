# CGC Code Review - Full Findings

## CROSS-DEVICE SYSTEMIC ISSUES (ALL 3 CLASSES)

### 1. `set_comspeed` vs `baudrate` naming
- PSU base (`psu_base.py:180`): method named `set_comspeed`, DLL is `SetBaudRate`, attribute is `self.baudrate`
- SW base (`sw_base.py:222`): same issue
- AMPR base already uses `set_baud_rate` (correct)
- Fix: rename `set_comspeed` to `set_baudrate` in PSU and SW

### 2. Dead `self.log` in base classes
- All bases accept `log` param, store `self.log`
- All subclasses pass `log=None`, use `self.logger` instead
- `self.log` never read in any base class
- Locations: `ampr_base.py:148`, `psu_base.py:145`, `sw_base.py:166`

### 3. Dead `self.idn` in base classes
- Bases store `self.idn`, subclasses store `self.device_id` (same value)
- `self.idn` never read in any base class
- Locations: `ampr_base.py:149`, `psu_base.py:146`, `sw_base.py:167`

### 4. `self.com` set twice
- Subclass sets `self.com = com`, then `super().__init__()` sets it again
- Locations: `ampr.py:52`, `psu.py:49`, `sw.py:52`

### 5. `self.port` vs `self.port_num` (PSU + SW)
- Base stores `self.port`, subclass stores `self.port_num` (same value)
- Fix: remove `self.port_num`, use `self.port` from base
- PSU refs: `psu.py:50,128,131,467`
- SW refs: `sw.py:53,132,136,492`

### 6. `err_dict` loaded but never used
- All bases load `error_codes.json` into `self.err_dict` at init
- No method ever reads `self.err_dict` in any file
- Locations: `ampr_base.py:143-145`, `psu_base.py:139-141`, `sw_base.py:160-162`

### 7. `__getattr__` conflicts + args bug
- All subclasses have `__getattr__` auto-logging AND explicit method overrides
- Pick one approach, not both
- Bug: `args[1:]` skips first real argument in log output (PSU `psu.py:644`, SW `sw.py:985`)
- AMPR `ampr.py:640`: infinite recursion risk on non-callable class attributes

### 8. `log_to_file` param unused
- `start_housekeeping(interval, log_to_file=True)` - param does nothing
- All 3 subclasses: `ampr.py:312`, `psu.py:336`, `sw.py:364`

### 9. JSON opened in binary mode
- `open(self.err_path, "rb")` should be `"r"` for JSON files
- All 3 base classes

---

## AMPR-SPECIFIC FINDINGS

### Critical
- **`__getattr__` infinite recursion** (`ampr.py:640`): Non-callable base class attributes cause `getattr(self, name)` to loop infinitely
- **Thread-safety gap** (`ampr.py:441,455,498`): Overridden methods (`enable_psu`, `get_state`, `set_module_voltage`) don't acquire `thread_lock`, but `hk_monitor` does. Concurrent DLL calls possible
- **Double-logging** (`ampr.py:459` + `ampr.py:197`): `get_state()` override and `_hk_main_state()` both emit identical debug message

### Duplicate Functions
| AMPR wrapper | Base method | Issue |
|---|---|---|
| `scan_modules()` (ampr.py:480) | `scan_all_modules()` (ampr_base.py:1085) | Same op, `_all` dropped |
| `get_module_voltages()` (ampr.py:512) | `get_all_module_voltages()` (ampr_base.py:1133) | Same op |
| `set_module_voltages()` (ampr.py:526) | `set_all_module_voltages()` (ampr_base.py:1174) | Same op |
| `get_module_info()` (ampr.py:543) | `scan_all_modules()` loop body | Core logic copy-pasted |

### Other
- 4 copy-pasted bitmask decoders in `ampr_base.py` (`get_device_state:496`, `get_voltage_state:540`, `get_temperature_state:565`, `get_interlock_state:590`) - should be one helper
- `import os` unused in `ampr.py:12`
- `self.baudrate` never updated after actual baud rate negotiation (`ampr.py:53`)

---

## PSU-SPECIFIC FINDINGS

### Critical
- **Unit mismatch mA vs A** (`psu_base.py:675` vs `psu.py:533`): Base current methods use Amperes, subclass uses milliAmperes. Same method name, completely different unit semantics. Safety hazard for power supply.

### Duplicate Functions
- **10 pairs of convenience wrappers** defined in BOTH `psu_base.py` AND `psu.py` (base versions completely shadowed):
  - `set_psu0_output_voltage` (base:608 vs sub:502)
  - `set_psu1_output_voltage` (base:612 vs sub:506)
  - `get_psu0_output_voltage` (base:636 vs sub:525)
  - `get_psu1_output_voltage` (base:640 vs sub:529)
  - `set_psu0_output_current` (base:702 vs sub:563)
  - `set_psu1_output_current` (base:706 vs sub:567)
  - `get_psu0_output_current` (base:730 vs sub:590)
  - `get_psu1_output_current` (base:734 vs sub:594)
  - `get_psu0_set_output_current` (base:761 vs sub:620)
  - `get_psu1_set_output_current` (base:765 vs sub:624)

- **6 copy-pasted housekeeping methods** in `psu.py` (only PSU number changes):
  - `_hk_psu0_adc_housekeeping` (242) / `_hk_psu1_adc_housekeeping` (255)
  - `_hk_psu0_housekeeping` (268) / `_hk_psu1_housekeeping` (279)
  - `_hk_psu0_data` (290) / `_hk_psu1_data` (300)
  - Should be 3 parameterized methods

### Other
- Magic numbers: `MAX_CONFIG=168`, `CONFIG_NAME_SIZE=75`, `SEN_COUNT=3`, `FAN_COUNT=3` defined but never used - hardcoded values used instead (`psu_base.py:1008,1029,1089,352,366`)
- `check_U_format` / `check_I_format` (`psu_base.py:507,544`) use physics abbreviations while everything else uses `voltage`/`current`
- `voltage_float` / `current_float` assigned but unused in validation methods (`psu_base.py:530,567`)
- `sys` import unused (`psu_base.py:6`)
- TOCTOU race in `stop_housekeeping` (`psu.py:404`) - `hk_running` checked outside lock
- Redundant `psu_name` computation pattern repeated 5 times (`psu.py:489,519,547,583,611`) - should be a helper

---

## SW-SPECIFIC FINDINGS

### High Priority
- **18 boilerplate logging overrides** (`sw.py:504-832`): ~330 lines of copy-pasted code, completely redundant with `__getattr__` at line 970. Pick one approach.
- **Duplicate constants** (`sw_base.py:122-125`): `CONFIG_INV`(32) / `CFG_INVERT`(32) and `SELECT_MASK`(31) / `CFG_MASK`(31) are identical pairs
- **`set_config_flags` may call nonexistent DLL function** (`sw_base.py:1280`): Knowledge file only lists `GetConfigFlags`, not `SetConfigFlags`

### Dead Code
- `PULSER_CFG` dictionary (sw_base.py:77-98) - 20 lines, never used
- `PULSER_CFG_NUM` (sw_base.py:126) - never referenced
- `DIO_INPUT_MAX` (sw_base.py:118) - never referenced
- `PULSER_INPUT_MAX` (sw_base.py:127) - never referenced
- `SWITCH_DELAY_SIZE/MAX/MASK` (sw_base.py:110-112) - never referenced
- `MAPPING_MAX/MASK/NUM` (sw_base.py:114-116) - never referenced in code
- `CONFIG_SIZE/CONFIG_MASK` (sw_base.py:119-121) - never referenced
- `MAPPING_SIZE` (sw_base.py:113) - duplicates `SWITCH_NUM`
- `PULSER_CFG_NUM` should be derived: `PULSER_NUM + PULSER_BURST_NUM`, not hardcoded

### Other
- `_hk_pulser_data` and `_hk_switch_data` (`sw.py:305,320`) always return `True` even on failure (other `_hk_*` methods return `status == NO_ERR`)
- Race condition: `self.connected` checked outside `hk_lock` in `start_housekeeping` (`sw.py:382`)
- Five `.parent` traversals for log directory (`sw.py:99-103`) - fragile path
