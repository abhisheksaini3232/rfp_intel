"""Load a bid folder into Documents (Phase 2).

load_bid_folder(folder) -> list[Document]: hash each file, dispatch by extension,
skip unknown types with a warning; one bad file never fails the run.
"""
