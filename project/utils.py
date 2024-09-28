def format_seconds(seconds):
    # Calculate minutes, seconds, and tenths of seconds
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds_remainder = seconds % 60
    seconds_int = int(seconds_remainder)
    tenths = int((seconds_remainder - seconds_int) * 10)

    # Format the result as "minutes:seconds.tenths"
    if hours > 0:
        return f"{hours}:{minutes:02d}:{seconds_int:02d}.{tenths}"
    elif minutes > 0:
        return f"{minutes}:{seconds_int:02d}.{tenths}"
    else:
        return f'{seconds_int}.{tenths}'
