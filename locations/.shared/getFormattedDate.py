from datetime import datetime, timedelta

today = datetime.today()
weekStart = today - timedelta(days=today.weekday())
# if on weekend assume we are running for next week
if today.weekday()>4:
    weekStart = weekStart + timedelta(days=7)
print(weekStart.strftime('%G-W%V'), end='')
