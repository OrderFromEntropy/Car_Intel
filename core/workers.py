"""QThread workers — run the search/rank/summarize pipeline off the main thread."""

from __future__ import annotations

import asyncio
import logging

from PyQt5.QtCore import QThread, pyqtSignal

from core.agents import rank_listings, summarize_listings
from core.models import CarListing, CarProfile
from core.profile_manager import UserProfile
from core.search_engine import run_search

log = logging.getLogger(__name__)


def _run_coro(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class SearchWorker(QThread):
    """Runs search + rank + summarize pipeline off the main thread."""

    status_update = pyqtSignal(str)
    progress_update = pyqtSignal(int, int)
    results_ready = pyqtSignal(list)
    error_occurred = pyqtSignal(str)

    def __init__(self, car_profile: CarProfile, user_profile: UserProfile, parent=None):
        super().__init__(parent)
        self.car_profile = car_profile
        self.framework = user_profile.framework

    def run(self):
        try:
            self.status_update.emit("Connecting to DuckDuckGo…")

            def search_status(msg: str) -> None:
                self.status_update.emit(msg)

            listings = _run_coro(run_search(self.car_profile, status_cb=search_status))

            if not listings:
                self.error_occurred.emit(
                    "No listings found — DDG returned 0 results. "
                    "Check your internet connection or try a broader search (remove zip / trim)."
                )
                return

            self.status_update.emit(f"Found {len(listings)} listings. Ranking with AI…")

            def rank_progress(done, total):
                self.progress_update.emit(done, total)
                self.status_update.emit(f"Ranking batch {done}/{total}…")

            ranked = _run_coro(
                rank_listings(
                    listings,
                    self.car_profile,
                    framework=self.framework,
                    progress_callback=rank_progress,
                )
            )

            self.status_update.emit("Generating summaries for top listings…")

            def sum_progress(idx):
                self.progress_update.emit(idx + 1, min(20, len(ranked)))

            final = _run_coro(
                summarize_listings(
                    ranked,
                    self.car_profile,
                    framework=self.framework,
                    top_n=20,
                    progress_callback=sum_progress,
                )
            )

            self.status_update.emit(f"Complete — {len(final)} listings ranked.")
            self.results_ready.emit(final)

        except Exception as exc:
            log.exception("SearchWorker failed")
            self.error_occurred.emit(f"Search pipeline error: {exc}")
