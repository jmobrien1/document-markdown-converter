from pydantic import BaseModel
from typing import List


class LedgerEntry(BaseModel):
    person: str
    r1: int
    r2: int
    r3: int
    r4: int
    total: int


class FinancialReport(BaseModel):
    entries: List[LedgerEntry]
    summary: str
    biggest_winner: str
    biggest_loser: str 