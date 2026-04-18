# Archived Plugin Versions

This directory contains legacy plugin versions that are no longer maintained.

## TEFAS Plugin Versions

### v1.0.0 (Current - Active)
- Location: `/root/minder/plugins/tefas/tefas_module.py`
- Status: **ACTIVE** - This is the production version
- Features: Basic fund data collection
- Dependencies: borsapy>=0.8.4, tefas-crawler>=0.5.0

### Legacy Versions (Archived)

#### tefas_module_old.py
- Archived: 2026-04-18
- Reason: Replaced by v1.0.0
- Features: Outdated implementation

#### tefas_module_v2.py
- Archived: 2026-04-18
- Reason: Experimental version, merged into v1.0.0
- Features: Beta features

#### tefas_module_v3.py
- Archived: 2026-04-18
- Reason: Too complex, split into separate collectors
- Features: Advanced analytics (will be added incrementally to v1.0.0)

## Version Policy

**Current Version**: 1.0.0 (Stable)

Version 1.0.0 means:
- ✅ Tested and verified
- ✅ Data collection works
- ✅ Database integration verified
- ✅ Production-ready

We will NOT increment to 1.0.1 or 1.1.0 until:
- All features are tested
- Data verification passes
- Documentation is complete
- Backup/restore scripts work

## Archive Date: 2026-04-18
