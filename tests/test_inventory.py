import json
from pathlib import Path
import unittest


FIXTURE = Path(__file__).with_name("fixtures") / "inventory-v1.json"


class InventoryTests(unittest.TestCase):
    def load_fixture(self):
        return json.loads(FIXTURE.read_text())

    def test_fixture_discovery_preserves_every_source_and_provenance(self):
        """Would fail if a source category is omitted or assigned the wrong provenance."""
        from runtime.inventory import discover

        inventory = discover(self.load_fixture())

        self.assertEqual(
            [(item.identifier, item.source, item.provenance) for item in inventory.capabilities],
            [
                ("app.terminal", "installed_apps", "fixture:installed_apps"),
                ("bind.launcher", "hyprland_bindings", "fixture:hyprland_bindings"),
                ("custom.capture", "custom_bindings", "fixture:custom_bindings"),
                ("menu.root", "menus", "fixture:menus"),
                ("omarchy.menu.root", "omarchy_commands", "fixture:omarchy_commands"),
            ],
        )
        self.assertEqual(inventory.state, {"focused_app": "foot", "workspace": "1"})
        self.assertEqual(inventory.state_provenance, "fixture:state")

    def test_duplicate_capability_ids_are_rejected_across_sources(self):
        """Would fail if one source can silently shadow another capability."""
        from runtime.inventory import InventoryError, discover

        fixture = self.load_fixture()
        fixture["menus"][0]["id"] = "omarchy.menu.root"

        with self.assertRaisesRegex(InventoryError, "duplicate capability id"):
            discover(fixture)

    def test_malformed_fixture_is_rejected_before_partial_inventory_is_returned(self):
        """Would fail if invalid source data enters the trusted catalog boundary."""
        from runtime.inventory import InventoryError, discover

        fixture = self.load_fixture()
        fixture["installed_apps"][0].pop("desktop_id")

        with self.assertRaisesRegex(InventoryError, "installed_apps"):
            discover(fixture)

    def test_discovered_data_and_state_are_immutable_snapshots(self):
        """Would fail if a caller can mutate inventory data after discovery."""
        from runtime.inventory import discover

        fixture = self.load_fixture()
        inventory = discover(fixture)

        with self.assertRaises((TypeError, AttributeError)):
            inventory.capabilities[-1].data["argv"].append("unexpected")
        with self.assertRaises(TypeError):
            inventory.state["workspace"] = "2"
        self.assertEqual(fixture["omarchy_commands"][0]["argv"], ["omarchy", "menu", "summon", "root"])

    def test_non_json_values_are_rejected_before_snapshotting(self):
        """Would fail if an unsupported mutable object survives the read-only boundary."""
        from runtime.inventory import InventoryError, discover

        fixture = self.load_fixture()
        fixture["state"]["mutable"] = {"unexpected"}

        with self.assertRaisesRegex(InventoryError, "JSON-compatible"):
            discover(fixture)


if __name__ == "__main__":
    unittest.main()
