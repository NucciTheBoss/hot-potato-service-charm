#!/usr/bin/env python3
# Copyright 2022 Canonical
# See LICENSE file for licensing details.

"""My hot-potato charm!"""

import json
import logging
import random
import time
from typing import Any, List, Union

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
from ops.model import ActiveStatus, Unit


logger = logging.getLogger(__name__)


class Forward:
    @staticmethod
    def forward(
        token: Any, peers: List[str], unit: Unit, **kwargs
    ) -> Union[dict, None]:
        """Recursive function to proceed through hot potato forward table."""

        logger.info("Inside forward.")

        delay = kwargs.get("delay", 0)
        max_passes = kwargs.get("max_passes", None)

        if max_passes is not None:
            if token.times_passed == max_passes and token.holder == unit.name:
                logger.info("Max passes reached.")
                unit.status = ActiveStatus(
                    (
                        "Maximum passes reached. "
                        f"Time to completion is {token.time_elapsed:.2f} seconds."
                    )
                )
                return None

        if token.holder != unit.name:
            return None
        else:
            unit.status = ActiveStatus(
                (
                    f"M: {token.message}, "
                    f"H: {token.holder}, "
                    f"P: {token.times_passed}, "
                    f"T: {token.time_elapsed:.2f}"
                )
            )
            token.holder = peers[random.randint(0, len(peers) - 1)]
            token.times_passed += 1
            timestamp = time.time()
            token.time_elapsed += timestamp - token.timestamp
            token.timestamp = timestamp
            if delay > 0:
                time.sleep(delay)
            unit.status = ActiveStatus()
            # Check if the next destination is the same unit.
            if token.holder == unit.name:
                # If so, run forward again
                return Forward.forward(
                    token, peers, unit, delay=delay, max_passes=max_passes
                )
            else:
                # Return new token
                return


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
        self.framework.observe(self.on.start_action, self._on_start_action)
        self._stored.set_default(bucket={self._PASSES_KEY: None, self._DELAY_KEY: 0})

    def _service_install(self, event: InstallEvent) -> None:
        self.unit.status = ActiveStatus()

    def _service_on_config_changed(self, event: ConfigChangedEvent) -> None:
        max_passes = self.config.get("max-passes")
        delay = self.config.get("delay")
        storage = self._stored.bucket

        if max_passes != storage[self._PASSES_KEY]:
            logger.info(f"Updating max passes to {max_passes}.")
            storage.update({self._PASSES_KEY: max_passes})
        if delay != storage[self._DELAY_KEY]:
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
        if (
            "message" not in event.relation.data[event.unit]
            or event.relation.data[event.unit].get("message") == ""
        ):
            logger.info("Key 'message' is not present or is empty in message.")
            return
        else:
            si = HotPotatoSuperInterface(self, "players", "peer")
            token = si.select(self.unit)
            r = self.model.relations.get("players")[0]
            peers = [self.unit.name] + [u.name for u in r.units]
            delay = self._stored.bucket[self._DELAY_KEY]
            max_passes = self._stored.bucket[self._PASSES_KEY]
            return Forward.forward(token, peers, self.unit, delay=delay, max_passes=max_passes)

    def _on_start_action(self, event: ActionEvent) -> None:
        """Handler for when start action is invoked."""
        logger.info("Constructing message and mapping peer topology.")
        delay = self._stored.bucket[self._DELAY_KEY]
        max_passes = self._stored.bucket[self._PASSES_KEY]
        r = self.model.relations.get("players")[0]
        peers = [self.unit.name] + [u.name for u in r.units]
        si = HotPotatoSuperInterface(self, "players", role="peer")
        token = si.select(self.unit)
        token.message = event.params["token"]
        token.holder = peers[random.randint(0, len(peers) - 1)]
        token.times_passed = 0
        token.time_elapsed = 0.0
        token.timestamp = time.time()
        logger.info("Running forward action")
        # See if return helps fix the issue?
        return Forward.forward(token, peers, self.unit, delay=delay, max_passes=max_passes)


if __name__ == "__main__":
    main(HotPotatoCharm)
