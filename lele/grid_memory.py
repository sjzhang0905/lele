"""Memory-aware admission for scalar fields, including all their channels."""
import os
import sys
from pathlib import Path

AUTO = object()


def available_bytes():
    try:
        if sys.platform == 'win32':
            import ctypes
            class MemoryStatus(ctypes.Structure):
                _fields_ = [('length', ctypes.c_uint32), ('load', ctypes.c_uint32)] + [
                    (name, ctypes.c_uint64) for name in ('total', 'available', 'page_total',
                     'page_available', 'virtual_total', 'virtual_available', 'extended')]
            state = MemoryStatus()
            state.length = ctypes.sizeof(state)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(state)):
                return state.available
        elif sys.platform.startswith('linux'):
            for line in Path('/proc/meminfo').read_text().splitlines():
                if line.startswith('MemAvailable:'):
                    available = int(line.split()[1]) * 1024
                    # Linux may report host RAM inside a memory-limited container.
                    try:
                        cg = Path('/sys/fs/cgroup')
                        available = min(available, int((cg/'memory.max').read_text()) -
                                        int((cg/'memory.current').read_text()))
                    except (OSError, ValueError):
                        pass
                    return max(0, available)
        else:
            return os.sysconf('SC_AVPHYS_PAGES') * os.sysconf('SC_PAGE_SIZE')
    except (OSError, ValueError, AttributeError):
        pass
    return None


def scalar_limit(requested=AUTO):
    if requested is not AUTO:
        return requested
    available = available_bytes()
    # Allow four float32-sized buffers per scalar for source, VTK and workspace.
    return 64_000_000 if available is None else max(0, available // 16)
