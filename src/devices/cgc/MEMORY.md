# CGC Device Classes - Code Review Summary

## Project Structure
- `cgc/ampr/` - Amplifier: `ampr.py` (subclass) + `ampr_base.py` (DLL wrapper)
- `cgc/psu/` - Power Supply: `psu.py` + `psu_base.py`
- `cgc/sw/` - Switch: `sw.py` + `sw_base.py`
- `cgc/esi/`, `cgc/pA/` - Not yet implemented

## Review Findings
Full details in [code-review-findings.md](code-review-findings.md)

### Cross-Device Systemic Issues (all 3 classes)
1. `set_comspeed` vs `self.baudrate` naming mismatch (PSU+SW)
2. Dead `self.log` in base (always None, never used)
3. Dead `self.idn` in base (duplicated by `self.device_id`)
4. `self.com` set twice (subclass + base)
5. `self.port` vs `self.port_num` mismatch (PSU+SW)
6. `err_dict` loaded but never used (wasted I/O)
7. `__getattr__` auto-logging conflicts with explicit overrides; `args[1:]` bug
8. `log_to_file` param in `start_housekeeping` is unused

### Critical Issues
- **PSU**: Unit mismatch mA vs A between base/subclass current methods
- **AMPR**: `__getattr__` infinite recursion risk; thread-safety gap
- **SW**: `set_config_flags` may call nonexistent DLL function
