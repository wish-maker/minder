#!/usr/bin/env python3
"""
Test sandbox subprocess isolation
"""

import multiprocessing as mp
import resource
import signal
import sys

sys.path.insert(0, "/root/minder")


def test_subprocess_isolation():
    """Test if subprocess isolation actually works"""
    print("=" * 60)
    print("TEST: Subprocess Isolation")
    print("=" * 60)

    # This simulates what SubprocessSandbox does
    def run_in_subprocess():
        try:
            # Set memory limit (256MB)
            max_memory = 256 * 1024 * 1024  # 256MB in bytes
            resource.setrlimit(resource.RLIMIT_AS, (max_memory, max_memory))
            print(f"[Child] Set memory limit: {max_memory} bytes")

            # Set CPU time limit (120 seconds)
            max_cpu = 120
            resource.setrlimit(resource.RLIMIT_CPU, (max_cpu, max_cpu))
            print(f"[Child] Set CPU time limit: {max_cpu} seconds")

            # Set alarm for timeout
            signal.alarm(10)  # 10 second timeout
            print("[Child] Set alarm: 10 seconds")

            # Try to consume memory (should fail)
            print("[Child] Attempting to consume 500MB...")
            data = []
            for i in range(500):  # Try to allocate 500MB
                data.append("x" * 1024 * 1024)  # 1MB per iteration
                if i % 50 == 0:
                    print(f"[Child] Allocated {i}MB...")

            print(f"[Child] SUCCESS? Allocated {len(data)}MB")
            sys.exit(1)  # Failed - allocated all memory

        except MemoryError as e:
            print(f"[Child] ✓ MemoryError caught (expected): {e}")
            sys.exit(0)  # Success - memory limit enforced

    # Start subprocess
    print("[Parent] Starting subprocess...")
    process = mp.Process(target=run_in_subprocess)
    process.start()
    print(f"[Parent] Subprocess PID: {process.pid}")

    # Wait for completion
    process.join(timeout=15)

    if process.exitcode is None:
        print("[Parent] Process still running, killing...")
        process.kill()
        process.join(timeout=5)

    exit_code = process.exitcode
    print(f"[Parent] Process exit code: {exit_code}")

    if exit_code == 0:
        print("✓ SUCCESS: Memory limit enforced (MemoryError caught)")
        return True
    else:
        print("❌ FAILED: Subprocess was able to allocate all memory")
        return False


if __name__ == "__main__":
    success = test_subprocess_isolation()

    if success:
        print("\n" + "=" * 60)
        print("SANDBOX TEST: ✓ PASSED")
        print("=" * 60)
    else:
        print("\n" + "=" * 60)
        print("SANDBOX TEST: ✗ FAILED")
        print("=" * 60)
