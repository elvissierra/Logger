from datetime import datetime

ALLOWED_INCREMENTS = {1, 5, 10, 15}

def round_datetime(dt: datetime, increment: int) -> datetime:
    if increment not in ALLOWED_INCREMENTS:
        increment = 5  # hard fallback for safety

    seconds = increment * 60
    epoch = dt.timestamp()
    rounded = round(epoch / seconds) * seconds

    return datetime.fromtimestamp(rounded, tz=dt.tzinfo)