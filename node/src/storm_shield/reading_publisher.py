import itertools
import logging
import threading
from collections.abc import Callable

from storm_shield.community_reading import CommunityReading, Position, Reading
from storm_shield.mesh import Mesh, MessageTooLarge

logger = logging.getLogger(__name__)


class ReadingPublisher:
    """Turns this Node's measurements into numbered Community Readings and shares them."""

    def __init__(
        self,
        mesh: Mesh,
        position: Callable[[], Position],
        river_km: Callable[[], float | None],
        measurements: Callable[[], list[Reading] | None],
        keep: Callable[[str, CommunityReading], None],
    ) -> None:
        self._mesh = mesh
        # Asked at each share, so a Node the Sandbox moves reads from its new spot.
        self._position = position
        self._river_km = river_km
        self._measurements = measurements
        self._keep = keep
        self._sequence = itertools.count()
        # Two shares on different threads must not swap their seqs, or the later reading would
        # carry the lower seq and the others would hide it.
        self._lock = threading.Lock()
        # What each reading that did not fit was made of, so one cause is logged once, not every tick.
        self._too_big_for: set[tuple[str, ...]] = set()

    def share(self) -> None:
        """Keep and publish one Community Reading; nothing once the measurements have ended."""
        with self._lock:
            measurements = self._measurements()
            if measurements is None:
                return
            reading = CommunityReading.from_measurements(
                node=self._mesh.identity,
                seq=next(self._sequence),
                position=self._position(),
                readings=measurements,
                river_km=self._river_km(),
            )
            self._keep(self._mesh.identity, reading)
            try:
                self._mesh.publish(reading)
            except MessageTooLarge as too_large:
                kinds = tuple(measurement.kind for measurement in reading.m)
                if kinds not in self._too_big_for:
                    self._too_big_for.add(kinds)
                    logger.error("this Node shared nothing: a reading of %s: %s", kinds, too_large)
            else:
                # A reading that fits again means the next oversized one is a new cause.
                self._too_big_for.clear()
