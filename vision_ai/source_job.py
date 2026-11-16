"""Independent per-race source job; numeric audit only, no forecast archive dependency."""
import argparse
import json
import os
import time
from pathlib import Path
from string import Formatter
from .analyzer import _valid_day
from .media import _check_url
from .pipeline import MANIFEST_SCHEMA, _numeric_hash, run
from .report_io import write_report

SCHEMA = 'boatlabs.vision_ai.source_job.v1'
FIELDS = {'date', 'yyyymmdd', 'venue', 'jcd', 'race', 'race2'}


def source_settings(environment):
    # Never mix a new provider's template with another provider's host list.
    prefix = 'VISION' if environment.get('VISION_VIDEO_SOURCE_TEMPLATE') else 'MIKUNI'
    template = environment.get(prefix + '_VIDEO_SOURCE_TEMPLATE', '').strip()
    hosts = {h.strip().lower() for h in environment.get(prefix + '_VIDEO_ALLOWED_HOSTS', '').split(',') if h.strip()}
    return template, hosts, prefix if template and hosts else 'MISSING'


def source_url(template, hosts, day, race):
    parts = list(Formatter().parse(template))
    names = {name for _, name, _, _ in parts if name is not None}
    if (names - FIELDS or not names.intersection({'race', 'race2'})
            or not names.intersection({'date', 'yyyymmdd'})
            or any(spec or conversion for _, _, spec, conversion in parts)):
        raise ValueError('explicit_date_and_race_template_required')
    url = template.format(date=day, yyyymmdd=day.replace('-', ''), venue='mikuni',
                          jcd='10', race=race, race2=f'{race:02d}')
    _check_url(url, hosts)
    return url


def collect(day, races, *, environment=None, attempts=2, processor=run, pause=time.sleep):
    if not _valid_day(day) or not isinstance(races, list) or not races or len(races) > 12:
        raise ValueError('invalid_day_or_races')
    if any(type(r) is not int or not 1 <= r <= 12 for r in races) or len(set(races)) != len(races):
        raise ValueError('invalid_or_duplicate_race')
    if type(attempts) is not int or not 1 <= attempts <= 3:
        raise ValueError('attempt_limit_required')
    template, hosts, mode = source_settings(os.environ if environment is None else environment)
    rows = []
    for race in races:
        manifest = {'schema': MANIFEST_SCHEMA, 'event_date': day, 'venue_code': '10', 'race': race,
                    'source_kind': 'real_exhibition',
                    'permission_reference': 'user-reported-venue-permission-personal-analysis-no-repost'}
        row = {'race': race, 'attempts': []}
        if mode == 'MISSING':
            row['status'] = 'SOURCE_CONFIGURATION_MISSING'
        else:
            try:
                url = source_url(template, hosts, day, race)
            except (ValueError, KeyError, IndexError, AttributeError):
                row['status'] = 'SOURCE_CONFIGURATION_INVALID'
            else:
                for _ in range(attempts):
                    observation = processor(manifest, video_url=url, allowed_hosts=hosts)
                    row['attempts'].append(observation)
                    row['status'] = observation['status']
                    # Access refusal, invalid media and decode/ID problems are not fixed by retrying.
                    retry = (observation['status'] == 'SOURCE_HTTP_ERROR'
                             and observation.get('http_status') in {404, 408, 502, 503, 504})
                    if not retry:
                        break
                    if len(row['attempts']) < attempts:
                        pause(2)
        rows.append(row)
    last = [r['attempts'][-1] for r in rows if r['attempts']]
    report = {'schema': SCHEMA, 'event_date': day, 'venue_code': '10', 'source_configuration': mode,
              'races': rows, 'summary': {key: sum(bool(r['stages'].get(key)) for r in last)
                  for key in ('media_received', 'frames_decoded', 'automatic_tracking_computed', 'six_candidates_simultaneous')},
              'confirmed_boat_tracks': 0, 'real_footage_independently_verified': False,
              'eligible_for_formal_forecast': False, 'eligible_for_shadow_forecast': False, 'bets_generated': 0}
    report['report_sha256'] = _numeric_hash(report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description='Independent authorized source job; no numerical AI inputs')
    parser.add_argument('--date', required=True)
    parser.add_argument('--races', required=True, help='Comma-separated explicit race numbers')
    parser.add_argument('--attempts', type=int, default=2)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = collect(args.date, [int(r) for r in args.races.split(',')], attempts=args.attempts)
        write_report(report, args.output)
    except (ValueError, TypeError, OSError):
        parser.exit(2, 'Invalid source job arguments; no source details logged\n')
    complete = report['summary']['automatic_tracking_computed'] == len(report['races'])
    print(json.dumps({'source_configuration': report['source_configuration'], 'summary': report['summary']}))
    return 0 if complete else 1


if __name__ == '__main__':
    raise SystemExit(main())
