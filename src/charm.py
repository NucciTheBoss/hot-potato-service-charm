#!/usr/bin/env python3
# Copyright 2022 Canonical
# See LICENSE file for licensing details.

"""My hot-potato charm!"""

import logging
import random
import time

from hpctlib.interface import checker
from hpctlib.interface import codec
from hpctlib.interface.base import Value
from hpctlib.interface.relation import RelationSuperInterface, UnitBucketInterface
from hpctlib.ops.charm.service import ServiceCharm
from ops.charm import (
    ActionEvent,
    ConfigChangedEvent,
    InstallEvent,
    RelationChangedEvent,
    RelationDepartedEvent,
    RelationJoinedEvent,
)
from ops.framework import StoredState
from ops.main import main
from ops.model import ActiveStatus


logger = logging.getLogger(__name__)


class HotPotatoSuperInterface(RelationSuperInterface):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self.interface_classes[("peer", "unit")] = self.HotPotatoUnitBucketInterface

    class HotPotatoUnitBucketInterface(UnitBucketInterface):
        message = Value(codec.String(), "")
        holder = Value(codec.String(), "")
        times_passed = Value(codec.Integer(), 0, checker.IntegerRange(0, None))
        time_elapsed = Value(codec.Float(), 0.0, checker.FloatRange(0.0, None))
        timestamp = Value(codec.Float(), 0.0, checker.FloatRange(0.0, None))


class HotPotatoCharm(ServiceCharm):

    _stored = StoredState()
    _PASSES_KEY = "passes"
    _DELAY_KEY = "delay"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.framework.observe(
            self.on.players_relation_joined, self._on_players_relation_join
        )
        self.framework.observe(
            self.on.players_relation_departed, self._on_players_relation_departed
        )
        self.framework.observe(
            self.on.players_relation_changed, self._on_players_relation_changed
        )
        self.framework.observe(self.on.ping_action, self._on_ping_action)
        self._stored.set_default(bucket={self._PASSES_KEY: None, self._DELAY_KEY: 0})

    def _service_install(self, event: InstallEvent) -> None:
        self.unit.status = ActiveStatus()

    def _service_on_config_changed(self, event: ConfigChangedEvent) -> None:
        """When the configuration of the service is updated."""
        storage = self._stored.bucket
        if (max_passes := self.config.get("max-passes")) != storage[self._PASSES_KEY]:
            logger.info(f"Updating max passes to {max_passes}.")
            storage.update({self._PASSES_KEY: max_passes})
        if (delay := self.config.get("delay")) != storage[self._DELAY_KEY]:
            logger.info(f"Updating total delay to {delay}.")
            storage.update({self._DELAY_KEY: delay})

    def _on_players_relation_join(self, event: RelationJoinedEvent) -> None:
        """When a new player enters the game."""
        logger.info(f"{self.unit.name}: Hello {event.unit.name}!")

    def _on_players_relation_departed(self, event: RelationDepartedEvent) -> None:
        """When a player leaves the game."""
        logger.info(f"{self.unit.name}: Goodbye {event.unit.name}!")

    def _on_players_relation_changed(self, event: RelationChangedEvent) -> None:
        """When data in players has changed."""
        logger.info("RelationChanged event detected.")
        if (
            "message" not in event.relation.data[event.unit]
            or event.relation.data[event.unit].get("message") == ""
        ):
            logger.info("Key 'message' is not present or is empty in message.")
            return
        else:
            i = HotPotatoSuperInterface(self, "players", role="peer")
            old_token = i.select(event.unit)
            new_token = i.select(self.unit)

            if (max_passes := self._stored.bucket[self._PASSES_KEY]) is not None:
                if old_token.times_passed == max_passes and old_token.holder == self.unit.name:
                    logger.info("Max passes reached.")
                    self.unit.status = ActiveStatus(
                        (
                            "Maximum passes reached. "
                            f"Time to completion is {old_token.time_elapsed:.2f} seconds."
                        )
                    )
                    return

            if old_token.holder != self.unit.name:
                if old_token.holder == event.unit.name:
                    logger.info(
                        f"Sending token back to {event.unit.name} for processing."
                    )
                    new_token.message = old_token.message
                    new_token.holder = old_token.holder
                    new_token.times_passed = old_token.times_passed
                    timestamp = time.time()
                    new_token.time_elapsed = timestamp - old_token.timestamp
                    new_token.timestamp = timestamp
                else:
                    return
            else:
                logger.info(f"Token being processed by unit {self.unit.name}")
                self.unit.status = ActiveStatus(
                    (
                        f"M: {old_token.message}, "
                        f"H: {old_token.holder}, "
                        f"P: {old_token.times_passed}, "
                        f"T: {old_token.time_elapsed:.2f}"
                    )
                )

                if (delay := self._stored.bucket[self._DELAY_KEY]) > 0:
                    time.sleep(delay)

                self.unit.status = ActiveStatus()
                r = self.model.get_relation("players")
                peers = [self.unit.name] + [u.name for u in r.units]
                new_token.message = old_token.message
                new_token.holder = peers[random.randint(0, len(peers) - 1)]
                new_token.times_passed = old_token.times_passed + 1
                timestamp = time.time()
                new_token.time_elapsed += timestamp - old_token.timestamp
                new_token.timestamp = timestamp

    def _on_ping_action(self, event: ActionEvent) -> None:
        """Handler for when start action is invoked."""
        logger.info("Received an action.")
        i = HotPotatoSuperInterface(self, "players", role="peer")
        r = self.model.get_relation("players")
        peers = [self.unit.name] + [u.name for u in r.units]
        token = i.select(self.unit)
        token.message = event.params["token"]
        token.holder = peers[random.randint(0, len(peers) - 1)]
        token.times_passed = 0
        token.time_elapsed = 0.0
        token.timestamp = time.time()


if __name__ == "__main__":
    main(HotPotatoCharm)
