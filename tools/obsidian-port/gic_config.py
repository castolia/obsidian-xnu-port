
#!/usr/bin/env python3
"""GICv3 configuration for Redmi Note 14 Pro 4G."""

import json
from pathlib import Path

GIC = {
    "compatible": "arm,gic-v3",
    "addressing": "physical",
    "distributor": {
        "base": 0x0C000000,
        "size": 0x40000,
    },
    "redistributor": {
        "base": 0x0C040000,
        "size": 0x200000,
        "regions": 1,
    },
    "interrupt_controller": True,
    "interrupt_cells": 4,
    "parent": 1,
    "maintenance_interrupt": {
        "type": 1,
        "number": 9,
        "flags": 4,
        "intid": 25,
    },
}

PLATFORM = "Redmi Note 14 Pro 4G"
SOC = "MediaTek MT6789"


def validate():
    d = GIC["distributor"]
    r = GIC["redistributor"]

    assert d["base"] > 0
    assert r["base"] > 0
    assert d["size"] > 0
    assert r["size"] > 0
    assert d["base"] + d["size"] <= r["base"]
    assert GIC["interrupt_cells"] == 4
    assert GIC["redistributor"]["regions"] == 1

    return True


def main():
    validate()

    report = {
        "platform": PLATFORM,
        "soc": SOC,
        "gic": GIC,
        "xnu_integration": {
            "status": "not_implemented",
            "requires": [
                "MTK-specific GIC physical mapping",
                "GICv3 initialization",
                "Redistributor discovery by MPIDR affinity",
                "Interrupt routing and CPU interface setup",
            ],
        },
    }

    output = Path(__file__).with_name("gic_config.json")
    output.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )

    print("OBSIDIAN GICv3 CONFIGURATION")
    print("===========================")
    print(f"SoC: {SOC}")
    print(f"GICD: 0x{GIC['distributor']['base']:08X}")
    print(f"GICR: 0x{GIC['redistributor']['base']:08X}")
    print("Validation: PASSED")
    print(f"Generated: {output}")
    print("XNU integration: NOT YET IMPLEMENTED")


if __name__ == "__main__":
    main()
