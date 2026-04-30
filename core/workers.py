"""QThread workers that run async tasks without blocking the UI."""

from __future__ import annotations

import asyncio
import logging
from typing import Callable

from PyQt5.QtCore import QThread, pyqtSignal

from core.agents import rank_listings, summarize_listings
from core.models import CarListing, CarProfile
from core.search_engine import run_search

log = logging.getLogger(__name__)


def _run_coro(coro):
    """Run a coroutine in a fresh event loop (called from a QThread)."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class SearchWorker(QThread):
    """Runs search + rank + summarize pipeline off the main thread."""

    status_update = pyqtSignal(str)
    progress_update = pyqtSignal(int, int)  # current, total
    results_ready = pyqtSignal(list)        # list[CarListing]
    error_occurred = pyqtSignal(str)

    def __init__(self, profile: CarProfile, parent=None):
        super().__init__(parent)
        self.profile = profile

    def run(self):
        try:
            self.status_update.emit("Searching car listings…")
            listings = _run_coro(run_search(self.profile))
            if not listings:
                self.error_occurred.emit("No listings found. Try broadening your search.")
                return

            self.status_update.emit(f"Found {len(listings)} listings. Ranking with AI…")

            def rank_progress(done, total):
                self.progress_update.emit(done, total)
                self.status_update.emit(f"Ranking batch {done}/{total}…")

            ranked = _run_coro(rank_listings(listings, self.profile, progress_callback=rank_progress))

            self.status_update.emit("Generating summaries for top listings…")

            def sum_progress(idx):
                self.progress_update.emit(idx + 1, min(20, len(ranked)))

            final = _run_coro(
                summarize_listings(ranked, self.profile, top_n=20, progress_callback=sum_progress)
            )

            self.status_update.emit("Complete!")
            self.results_ready.emit(final)

        except Exception as exc:
            log.exception("SearchWorker failed")
            self.error_occurred.emit(str(exc))
