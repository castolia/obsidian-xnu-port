
#!/usr/bin/env python3
"""
Redmi Note 14 Pro 4G (obsidian)
MediaTek MT6789 CPU topology description for the XNU port.
"""

import json
from pathlib import Path

PLATFORM = {
    "name": "Redmi Note 14 Pro 4G",
    "codename": "obsidian",
    "soc": "MediaTek MT6789",
    "architecture": "arm64",
    "cpu_count": 8,
}

CLUSTERS = [
    {
        "id": 0,
        "name": "efficiency",
        "cpu_model": "Cortex-A55",
        "midr": "0x412fd050",
        "linux_package_id": 0,
        "cpus": [0, 1, 2, 3, 4, 5],
    },
    {
        "id": 1,
        "name": "performance",
        "cpu_model": "Cortex-A76",
        "midr": "0x414fd0b0",
        "linux_package_id": 1,
        "cpus": [6, 7],
    },
]

# Values taken from the CPU nodes in the Linux Device Tree.
# These are MPIDR candidates, not yet independently verified MPIDRs.
DT_CPU_REG = {
    0: 0x00000000,
    1: 0x00000100,
    2: 0x00000200,
    3: 0x00000300,
    4: 0x00000400,
    5: 0x00000500,
    6: 0x00000600,
    7: 0x00000700,
}


def build_topology():
    cpus = []

    for cluster in CLUSTERS:
        for cpu_id in cluster["cpus"]:
            affinity = DT_CPU_REG[cpu_id]

            cpus.append({
                "linux_cpu_id": cpu_id,
                "cluster_id": cluster["id"],
                "cluster": cluster["name"],
                "model": cluster["cpu_model"],
                "midr": cluster["midr"],
                "linux_core_id": (
                    cpu_id if cluster["id"] == 0
                    else cpu_id - 6
                ),
                "linux_package_id": cluster["linux_package_id"],
                "device_tree_reg": f"0x{affinity:08x}",
                "mpidr_candidate": f"0x{affinity:08x}",
                "mpidr_verified": False,
                "enable_method": "psci",
            })

    return {
        "platform": PLATFORM,
        "clusters": CLUSTERS,
        "cpus": cpus,
        "boot_cpu": None,
        "boot_cpu_status": "not_yet_verified",
        "psci": {
            "compatible": "arm,psci-1.0",
            "method": "smc",
        },
        "warnings": [
            "Device Tree reg values are candidates; MPIDR mapping "
            "has not been independently verified.",
            "Boot CPU has not yet been identified.",
            "No XNU CPU startup code has been implemented yet.",
        ],
    }


def validate(data):
    cpus = data["cpus"]

    assert len(cpus) == 8, "Expected exactly 8 CPUs"
    assert len({cpu["linux_cpu_id"] for cpu in cpus}) == 8
    assert sum(len(c["cpus"]) for c in CLUSTERS) == 8

    for cpu in cpus:
        assert cpu["enable_method"] == "psci"
        assert cpu["device_tree_reg"].startswith("0x")

    return True


def main():
    output = Path(__file__).with_name("cpu_topology.json")

    topology = build_topology()
    validate(topology)

    output.write_text(
        json.dumps(topology, indent=2),
        encoding="utf-8",
    )

    print("OBSIDIAN CPU TOPOLOGY")
    print("=====================")
    print(f"Platform: {PLATFORM['name']}")
    print(f"SoC: {PLATFORM['soc']}")
    print(f"CPU cores: {PLATFORM['cpu_count']}")

    for cluster in CLUSTERS:
        print(
            f"Cluster {cluster['id']}: "
            f"{cluster['cpu_model']} x{len(cluster['cpus'])}"
        )

    print("\nValidation: PASSED")
    print(f"Generated: {output}")
    print("MPIDR mapping: NOT YET VERIFIED")


if __name__ == "__main__":
    main()
