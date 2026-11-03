"""Sequential official data acquisition into an independent local cache."""
import argparse
from datetime import date,timedelta
from pathlib import Path
from automation.v10.phase2_research import TwseDailyTableProvider

def main():
    p=argparse.ArgumentParser();p.add_argument('--cache',type=Path,required=True)
    p.add_argument('--start',type=date.fromisoformat,required=True);p.add_argument('--end',type=date.fromisoformat,required=True)
    a=p.parse_args()
    if a.start>a.end or a.end>date.today():raise ValueError('INVALID_OR_FUTURE_RANGE')
    if any(x in {'v10_forward_store','v10-original-readonly'} for x in a.cache.resolve().parts):
        raise ValueError('ORIGINAL_STORE_IS_READ_ONLY')
    provider=TwseDailyTableProvider(a.cache,delay_seconds=1)
    current=a.start;count=0
    while current<=a.end:
        if current.weekday()<5:
            day=provider.day(current)  # No retry/bypass on a provider rejection.
            count+=bool(day.get('bars') and day.get('benchmark'))
        current+=timedelta(days=1)
    print(f'Acquired {count} complete official sessions; no strategy or account modified.')

if __name__=='__main__':main()
